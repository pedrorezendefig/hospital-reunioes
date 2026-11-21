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


# ═══════════════════════════════════════════════════════════════════════════
# 2. A contestação é decidida pelos demais membros, sem o contestado
# ═══════════════════════════════════════════════════════════════════════════

CONTESTACOES = "contestacoes-de-participacao"


class TestContestarParticipacao:
    def _contestar(self, comite, caso, autor=COORDENACAO, contestado=MEMBRO) -> str:
        return comite.ok(autor, caso, CONTESTACOES, {"contestado_id": contestado, "motivo": "interesse"})[
            "contestacao"
        ]["id"]

    def test_o_contestado_nao_decide(self, comite):
        caso = comite.caso()
        contestacao = self._contestar(comite, caso)

        resposta = comite.agir(MEMBRO, caso, f"{CONTESTACOES}/{contestacao}/decisao", {"escolha": "manter"})

        assert resposta.status_code == 403
        assert comite.abrir(MEMBRO, caso).status_code == 200

    def test_os_demais_confirmam_e_o_contestado_fica_impedido(self, comite):
        caso = comite.caso()
        contestacao = self._contestar(comite, caso)
        assert comite.abrir(MEMBRO, caso).status_code == 200

        comite.ok(SEGUNDO_LEITOR, caso, f"{CONTESTACOES}/{contestacao}/decisao", {"escolha": "confirmar"})

        assert _recusado(comite.abrir(MEMBRO, caso))
        assert [c["id"] for c in comite.lista(SUPLENTE).json()["casos"]] == [caso]

    def test_os_demais_mantem_e_o_contestado_segue_no_caso(self, comite):
        caso = comite.caso()
        contestacao = self._contestar(comite, caso)

        comite.ok(SEGUNDO_LEITOR, caso, f"{CONTESTACOES}/{contestacao}/decisao", {"escolha": "manter"})

        assert comite.abrir(MEMBRO, caso).status_code == 200
        tela = comite.abrir(COORDENACAO, caso).json()
        assert [c["resultado"] for c in tela["contestacoes_de_participacao"]] == ["rejeitada"]

    def test_ninguem_contesta_a_si_mesmo_nem_quem_nao_esta_no_caso(self, comite):
        caso = comite.caso()

        corpo = {"contestado_id": COORDENACAO, "motivo": "interesse"}
        assert comite.agir(COORDENACAO, caso, CONTESTACOES, corpo).status_code == 422
        corpo = {"contestado_id": SUPLENTE, "motivo": "interesse"}
        assert comite.agir(COORDENACAO, caso, CONTESTACOES, corpo).status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 5 e 6. Qualquer membro marca um Citado em qualquer etapa; o Citado ligado ao
# cadastro recebe 403 em qualquer perfil, e o membro Citado fica impedido
# ═══════════════════════════════════════════════════════════════════════════

FORA_DP = {"escopo": "fora", "categoria": "F", "rito": "encaminhamento", "destino": "dp"}


class TestCitado:
    def test_qualquer_membro_marca_um_citado_na_triagem_e_depois_de_encerrado(self, comite):
        caso = comite.caso()
        comite.ok(MEMBRO, caso, "citados", {"nome": "Carlos da Portaria"})

        comite.ok(COORDENACAO, caso, "triagem", FORA_DP)
        comite.ok(SEGUNDO_LEITOR, caso, "conferencia")
        comite.ok(COORDENACAO, caso, "encaminhamento")
        comite.ok(SEGUNDO_LEITOR, caso, "citados", {"nome": "Bia do Raio X"})

        tela = comite.abrir(MEMBRO, caso).json()
        assert tela["situacao"] == "encerrado"
        assert [(c["nome"], c["ligado"]) for c in tela["citados"]] == [
            ("Carlos da Portaria", False),
            ("Bia do Raio X", False),
        ]
        assert not any("Carlos" in linha["detalhe"] for linha in comite.banco.tabelas["conduta_trilha"])
        assert all(c["nome_cifrado"].startswith("v1:") for c in comite.banco.tabelas["conduta_citados"])

    def test_sem_nome_e_sem_cadastro_nao_marca(self, comite):
        caso = comite.caso()
        assert comite.agir(MEMBRO, caso, "citados", {"nome": "  "}).status_code == 422

    def test_a_busca_no_cadastro_acha_a_pessoa_e_a_marcacao_se_liga_a_ela(self, comite):
        caso = comite.caso()

        achados = comite.cliente(MEMBRO).get(f"{BASE}/casos/{caso}/cadastro", params={"busca": "almox"}).json()
        assert achados == {"pessoas": [{"id": DE_FORA, "nome": "Joana Almoxarifado Silva"}]}

        comite.ok(MEMBRO, caso, "citados", {"participante_id": DE_FORA})
        (citado,) = comite.abrir(MEMBRO, caso).json()["citados"]
        assert (citado["nome"], citado["ligado"]) == ("Joana Almoxarifado Silva", True)

    def test_citado_ligado_ao_cadastro_recebe_403_naquele_caso_mesmo_designado(self, comite):
        caso = comite.caso()
        outro = comite.caso()
        for caso_id in (caso, outro):
            comite.banco.tabelas.setdefault("conduta_atribuicoes", []).append(
                {
                    "caso_id": caso_id,
                    "participante_id": DE_FORA,
                    "motivo": "apurador",
                    "termo_assinado_em": "2026-11-01T10:00:00+00:00",
                    "impedido_em": None,
                    "revogada_em": None,
                }
            )
        assert comite.abrir(DE_FORA, caso).status_code == 200

        comite.ok(MEMBRO, caso, "citados", {"participante_id": DE_FORA})

        assert _recusado(comite.abrir(DE_FORA, caso))
        assert comite.abrir(DE_FORA, outro).status_code == 200

    def test_membro_citado_fica_impedido_sem_ato_de_ninguem(self, comite):
        caso = comite.caso()

        comite.ok(COORDENACAO, caso, "citados", {"participante_id": MEMBRO})

        assert _recusado(comite.abrir(MEMBRO, caso))
        (impedimento,) = [
            a for a in comite.banco.tabelas["conduta_atribuicoes"] if a["participante_id"] == MEMBRO
        ]
        assert impedimento["impedido_em"] and impedimento["impedimento_motivo"] == "citado"
        assert (None, "impedimento") in [(autor, acao) for autor, acao, _ in comite.trilha(caso)]
        assert [c["id"] for c in comite.lista(SUPLENTE).json()["casos"]] == [caso]


# ═══════════════════════════════════════════════════════════════════════════
# 3 e 4. O suplente convocado abre só o caso da convocação; sem convocação,
# nenhum caso
# ═══════════════════════════════════════════════════════════════════════════


class TestSuplente:
    def test_suplente_sem_convocacao_nao_ve_caso_nenhum(self, comite):
        caso = comite.caso()

        assert _recusado(comite.lista(SUPLENTE))
        assert _recusado(comite.abrir(SUPLENTE, caso))

    def test_o_suplente_convocado_abre_so_o_caso_da_convocacao(self, comite):
        caso = comite.caso()
        outro = comite.caso()

        comite.ok(MEMBRO, caso, "impedimento", {"motivo": "relacao_pessoal"})

        assert [c["id"] for c in comite.lista(SUPLENTE).json()["casos"]] == [caso]
        assert comite.abrir(SUPLENTE, caso).status_code == 200
        assert _recusado(comite.abrir(SUPLENTE, outro))

    def test_o_suplente_faz_o_que_a_coordenacao_impedida_fazia(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "impedimento", {"motivo": "chefia_direta"})

        aberto = comite.abrir(SUPLENTE, caso).json()
        assert aberto["papel"] == "coordenacao"
        assert aberto["o_que_fazer_agora"]["bloqueio"] is None
        vez = comite.cliente(SUPLENTE).get(f"{BASE}/minha-vez").json()["itens"]
        assert [(i["id"], i["acao"]) for i in vez] == [(caso, "Confirmar a triagem")]
        comite.ok(SUPLENTE, caso, "triagem", DENTRO_RAPIDO)

    def test_sem_suplente_livre_o_impedimento_vale_e_ninguem_mais_e_convocado(self, comite):
        caso = comite.caso()
        comite.ok(MEMBRO, caso, "impedimento", {"motivo": "parte"})

        comite.ok(SEGUNDO_LEITOR, caso, "impedimento", {"motivo": "parte"})

        assert _recusado(comite.abrir(SEGUNDO_LEITOR, caso))
        convocados = [a for a in comite.banco.tabelas["conduta_atribuicoes"] if a["motivo"] == "suplente_convocado"]
        assert [(a["participante_id"], a["substitui_id"]) for a in convocados] == [(SUPLENTE, MEMBRO)]
