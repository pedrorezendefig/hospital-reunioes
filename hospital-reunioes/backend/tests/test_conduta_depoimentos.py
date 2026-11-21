"""O depoimento do Canal de Conduta (issue #1830; especificação, seções 7.1 e
7.2; ADR 0097, decisão 2).

Cada classe é um critério de aceite da issue. As pessoas e os casos são de
teste; o banco e o Storage são os dublês de `conduta_apoio`, e a cifra é de
verdade, com uma chave gerada na hora.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from datetime import datetime, timedelta
from typing import Any

import pytest
from conduta_apoio import Banco
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import conduta_comite, conduta_depoimentos  # noqa: E402
from app.services.conduta import casos, cifra  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

BASE = "/api/comite-de-conduta"
RELATO = "O supervisor grita com a equipe do almoxarifado e ameaça cortar as horas."
HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}
COORDENACAO, MEMBRO, DE_FORA = "COORD", "MEMB", "FORA"
NOMES = {COORDENACAO: "Ana Coordenadora", MEMBRO: "Bruno Membro", DE_FORA: "Carla de Fora"}

PESSOA_OUVIDA = {"nome": "Fulano de Tal", "cargo": "Supervisor do almoxarifado", "papel": "acusado"}
TRANSCRICAO = "Entrevistador: o senhor confirma? Fulano: confirmo que levantei a voz.".encode()
# O começo de um M4A de verdade (caixa ftyp), seguido de "som".
AUDIO_M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom" + b"som do depoimento" * 64
FOTO_DO_TERMO = b"\xff\xd8\xff\xe0" + b"pixels do termo assinado" * 32


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())


def _pessoa(pid: str) -> dict[str, Any]:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": NOMES[pid],
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
    }


def _participacao(pid: str, papel: str) -> dict:
    return {
        "id": f"part-{pid}",
        "colegiado_id": COMITE["id"],
        "participante_id": pid,
        "papel": papel,
        "vigencia_inicio": (HOJE - timedelta(days=30)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=600)).isoformat(),
        "termo_assinado_em": "2026-10-01T12:00:00+00:00",
    }


class Comite:
    """Coordenação e membro do Comitê, mais alguém de fora dele, e um caso já
    na etapa Apuração do rito Rápido."""

    def __init__(self):
        self.banco = Banco(
            {
                "participantes": [_pessoa(p) for p in (COORDENACAO, MEMBRO, DE_FORA)],
                "colegiados": [dict(COMITE)],
                "participacoes": [_participacao(COORDENACAO, "coordenacao"), _participacao(MEMBRO, "membro")],
            }
        )

    def caso(self, etapa: str = "apuracao") -> str:
        novo = casos.registrar_caso(self.banco, relato=RELATO, categoria=None)
        linha = next(c for c in self.banco.tabelas["conduta_casos"] if c["id"] == novo["id"])
        linha.update(
            {
                "recebido_em": datetime.now().astimezone().isoformat(),
                "etapa": etapa,
                "rito": "rapido" if etapa == "apuracao" else None,
                "escopo": "dentro" if etapa == "apuracao" else None,
            }
        )
        return novo["id"]

    def cliente(self, pid: str) -> TestClient:
        app = FastAPI()
        app.include_router(conduta_comite.router, prefix="/api")
        app.include_router(conduta_depoimentos.router, prefix="/api")
        pessoa = next(p for p in self.banco.tabelas["participantes"] if p["id"] == pid)

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def abrir(self, pid: str, caso_id: str) -> dict:
        resposta = self.cliente(pid).get(f"{BASE}/casos/{caso_id}")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def adicionar(self, pid: str, caso_id: str, pessoa: dict | None = None):
        return self.cliente(pid).post(f"{BASE}/casos/{caso_id}/depoimentos", json=pessoa or PESSOA_OUVIDA)

    def depoimento(self, caso_id: str, pid: str = MEMBRO) -> str:
        resposta = self.adicionar(pid, caso_id)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["depoimento"]["id"]

    def anexar(self, pid: str, caso_id: str, dep: str, botao: str, nome: str, conteudo: bytes):
        return self.cliente(pid).post(
            f"{BASE}/casos/{caso_id}/depoimentos/{dep}/{botao}",
            files={"arquivo": (nome, conteudo, "application/octet-stream")},
        )

    def cartao(self, pid: str, caso_id: str, dep: str) -> dict:
        return next(d for d in self.abrir(pid, caso_id)["depoimentos"] if d["id"] == dep)

    def trilha(self, caso_id: str) -> list[str]:
        return [linha["acao"] for linha in self.banco.tabelas["conduta_trilha"] if linha["caso_id"] == caso_id]


@pytest.fixture
def comite() -> Comite:
    return Comite()


# ═══════════════════════════════════════════════════════════════════════════
# O cartão do depoimento recebe transcrição, áudio e termo assinado, cada um
# no seu botão, sem seletor de tipo
# ═══════════════════════════════════════════════════════════════════════════


class TestCartaoDoDepoimento:
    def test_adicionar_pessoa_a_ouvir_cria_o_cartao_com_nome_cargo_e_papel(self, comite):
        caso = comite.caso()

        dep = comite.depoimento(caso)

        cartao = comite.cartao(COORDENACAO, caso, dep)
        assert (cartao["nome"], cartao["cargo"], cartao["papel"]) == (
            "Fulano de Tal",
            "Supervisor do almoxarifado",
            "acusado",
        )
        assert cartao["situacao"] == "Aguardando assinatura"
        assert "adicionou_pessoa_a_ouvir" in comite.trilha(caso)
