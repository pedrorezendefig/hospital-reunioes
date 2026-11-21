"""Impedimento, suplente convocado e Citado no Canal de Conduta (issue #1828).

Cada classe é um critério de aceite da issue. As pessoas e os casos são de
teste; o banco é o dublê de `conduta_apoio`, e o relato é cifrado de verdade,
com uma chave gerada na hora.
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
from app.routers import conduta_comite  # noqa: E402
from app.services.conduta import casos  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

BASE = "/api/comite-de-conduta"
RELATO = "A chefe do almoxarifado humilha a equipe na frente dos pacientes."
HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}
RECUSA = "Sem acesso a este conteúdo do Canal de Conduta"

COORDENACAO, SEGUNDO_LEITOR, MEMBRO, SUPLENTE, DE_FORA = "COORD", "LEITOR", "MEMB", "SUPL", "FORA"
DENTRO_RAPIDO = {"escopo": "dentro", "categoria": "A", "rito": "rapido"}


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())


def _pessoa(pid: str, nome: str | None = None) -> dict[str, Any]:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome or f"Pessoa {pid}",
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
    """Coordenação, segundo leitor, membro e um suplente, mais alguém de fora."""

    def __init__(self):
        self.banco = Banco(
            {
                "participantes": [
                    _pessoa(COORDENACAO),
                    _pessoa(SEGUNDO_LEITOR),
                    _pessoa(MEMBRO),
                    _pessoa(SUPLENTE),
                    _pessoa(DE_FORA, "Joana Almoxarifado Silva"),
                ],
                "colegiados": [dict(COMITE)],
                "participacoes": [
                    _participacao(COORDENACAO, "coordenacao"),
                    _participacao(SEGUNDO_LEITOR, "segundo_leitor"),
                    _participacao(MEMBRO, "membro"),
                    _participacao(SUPLENTE, "suplente"),
                ],
            }
        )

    def caso(self) -> str:
        novo = casos.registrar_caso(self.banco, relato=RELATO, categoria=None)
        linha = next(c for c in self.banco.tabelas["conduta_casos"] if c["id"] == novo["id"])
        linha["recebido_em"] = datetime.now().astimezone().isoformat()
        return novo["id"]

    def cliente(self, pid: str) -> TestClient:
        app = FastAPI()
        app.include_router(conduta_comite.router, prefix="/api")
        pessoa = next(p for p in self.banco.tabelas["participantes"] if p["id"] == pid)

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def agir(self, pid: str, caso_id: str, acao: str, corpo: dict | None = None):
        return self.cliente(pid).post(f"{BASE}/casos/{caso_id}/{acao}", json=corpo or {})

    def ok(self, pid: str, caso_id: str, acao: str, corpo: dict | None = None) -> dict:
        resposta = self.agir(pid, caso_id, acao, corpo)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def abrir(self, pid: str, caso_id: str):
        return self.cliente(pid).get(f"{BASE}/casos/{caso_id}")

    def lista(self, pid: str):
        return self.cliente(pid).get(f"{BASE}/casos")

    def trilha(self, caso_id: str) -> list[tuple[str | None, str, str]]:
        return [
            (linha["autor_id"], linha["acao"], linha["detalhe"])
            for linha in self.banco.tabelas["conduta_trilha"]
            if linha["caso_id"] == caso_id and linha["acao"] != "leitura"
        ]


def _recusado(resposta) -> bool:
    return resposta.status_code == 403 and resposta.json() == {"detail": RECUSA}


@pytest.fixture
def comite() -> Comite:
    return Comite()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Um membro declara impedimento e perde o acesso ao caso na hora
# ═══════════════════════════════════════════════════════════════════════════


class TestDeclararImpedimento:
    def test_o_membro_declara_impedimento_e_perde_o_acesso_na_hora(self, comite):
        caso = comite.caso()
        outro = comite.caso()
        assert comite.abrir(MEMBRO, caso).status_code == 200

        comite.ok(MEMBRO, caso, "impedimento", {"motivo": "parentesco"})

        assert _recusado(comite.abrir(MEMBRO, caso))
        assert [c["id"] for c in comite.lista(MEMBRO).json()["casos"]] == [outro]
        assert comite.abrir(MEMBRO, outro).status_code == 200
