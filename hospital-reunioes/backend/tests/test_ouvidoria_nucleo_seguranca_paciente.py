"""O envio ao Núcleo de Segurança do Paciente (issue #1621, PRD #1527, ADR 0088).

O ouvidor manda ao Núcleo (NSP) o caso que fala de incidente com o paciente, e
o Núcleo confirma o recebimento por um link sem senha. Quando o agente de
triagem aponta o caso, "Validar e acionar" só conclui depois de o ouvidor
confirmar o envio ou descartar com motivo. O link do Núcleo mostra o relato
integral mesmo no caso sigiloso (a única exceção ao sigilo), o email só avisa e
traz o link, e sem o Recebido no prazo a cobrança sobe ao gestor e à Diretoria.
A ciência corre em paralelo: o caso com o selo responde e encerra normalmente.

Os dublês de banco são os da validação (`test_ouvidoria_validacao_acionamento`),
como no elogio: a ciência do Núcleo nasce pela mesma porta do acionamento.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_validacao_acionamento import (  # noqa: E402
    DENTRO_DO_EXPEDIENTE,
    OUVIDOR,
    VALIDACAO,
    _manifestacao,
    _responsavel,
    _SupabaseFake,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

NUCLEO = "Nucleo de Seguranca do Paciente"
PRESIDENTE = {"nome": "Dra. Helena Presidente", "email": "nsp@hsm.br"}

RELATO = "Minha mae caiu da cama no quarto 412 na madrugada e ninguem veio ajudar por meia hora."
JUSTIFICATIVA_SIMPLES = "O relato descreve uma queda de paciente internado, que e incidente de assistencia."
JUSTIFICATIVA_TECNICA = "Queda do leito, internacao, madrugada de 24/08. Dano relatado: escoriacao no braco."


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def emails(monkeypatch) -> list[dict]:
    """Toda saída de email do módulo passa por `_enviar_email`. Nenhum teste
    deste arquivo encosta no provedor de verdade."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html, texto=None, **_kwargs):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "html": html, "texto": texto})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _caso(**overrides) -> dict:
    """Um caso já com a área, com o relato da queda, o paciente e o quarto."""
    base = {
        "status": "aguardando_area",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "gravidade": "medio",
        "relato_integral": RELATO,
        "extrato_para_o_setor": "Apurar o atendimento da equipe no plantao noturno.",
        "paciente_nome": "Ana Maria Souza",
        "paciente_nascimento": "1948-03-02",
        "profissionais": "Enfermeiro do plantao noturno",
        "quarto": "412",
        "nsp_sugerido": False,
        "nsp_justificativa_simples": None,
        "nsp_justificativa_tecnica": None,
        "nsp_decisao": None,
        "nsp_decisao_motivo": None,
    }
    return _manifestacao(**(base | overrides))


def _banco(caso: dict | None = None) -> _SupabaseFake:
    """O banco com o Núcleo configurado e com titular e gestor cadastrados."""
    supabase = _SupabaseFake(
        [caso if caso is not None else _caso()],
        responsaveis=[
            _responsavel(),
            _responsavel("titular", id="resp-nsp", setor=NUCLEO, **PRESIDENTE),
            _responsavel("gestor", id="resp-nsp-gestor", setor=NUCLEO, nome="Gestor do Nucleo", email="g@hsm.br"),
        ],
    )
    supabase.tabelas["setores"].append({"id": "s2", "nome": NUCLEO, "ativo": True})
    supabase.tabelas["ouvidoria_config"] = [{"id": True, "nsp_setor": NUCLEO}]
    return supabase


def _client(monkeypatch, supabase: _SupabaseFake | None = None, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
    """O painel do ouvidor e o link do email no mesmo app, sobre o mesmo banco."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _banco()

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _enviar_ao_nucleo(client):
    return client.post("/api/ouvidoria/manifestacoes/uuid-7/nsp")


def _ciencias_do_nucleo(supabase: _SupabaseFake) -> list[dict]:
    return [a for a in supabase.tabelas.get("ouvidoria_acionamentos", []) if a.get("motivo_ciencia") == "nsp"]


# =====================================================================
# 1. Enviar ao NSP funciona sem sugestão
# =====================================================================


class TestEnviarAoNucleoSemSugestao:
    def test_enviar_ao_nsp_sem_sugestao_cria_a_ciencia_do_nucleo_e_marca_o_selo(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        r = _enviar_ao_nucleo(client)

        assert r.status_code == 200, r.text
        ciencias = _ciencias_do_nucleo(supabase)
        assert len(ciencias) == 1
        ciencia = ciencias[0]
        assert ciencia["tipo"] == "ciencia"
        assert ciencia["status"] == "pendente"
        assert ciencia["setor"] == NUCLEO
        assert ciencia["responsavel_email"] == "nsp@hsm.br"
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["nsp_decisao"] == "confirmado"
        assert caso["nsp_decidido_por"] == OUVIDOR["id"]
        assert r.json()["selo"] == "Em análise pelo NSP"


# =====================================================================
# 2. Com sugestão, a validação só conclui depois da decisão sobre o Núcleo
# =====================================================================


def _caso_apontado(**overrides) -> dict:
    """O caso que o agente de triagem apontou ao Núcleo, ainda em classificação."""
    return _caso(
        status="em_classificacao",
        setor="A definir",
        gravidade=None,
        nsp_sugerido=True,
        nsp_justificativa_simples=JUSTIFICATIVA_SIMPLES,
        nsp_justificativa_tecnica=JUSTIFICATIVA_TECNICA,
        **overrides,
    )


def _validar(client, **corpo):
    return client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO | corpo)


class TestDecisaoSobreONucleoNaValidacao:
    def test_com_sugestao_validar_sem_decidir_sobre_o_nucleo_e_recusado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client)

        assert r.status_code == 422, r.text
        assert "Núcleo de Segurança do Paciente" in r.json()["detail"]
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "em_classificacao", "a recusa vem antes de qualquer efeito"
        assert supabase.tabelas["ouvidoria_notificacoes"] == []
        assert emails == []

    def test_descartar_sem_motivo_e_recusado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="descartado", nsp_motivo="   ")

        assert r.status_code == 422, r.text
        assert "motivo" in r.json()["detail"]
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "em_classificacao"
        assert caso["nsp_decisao"] is None
        assert emails == []

    def test_descartar_com_motivo_grava_a_decisao_e_aciona_a_area(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="descartado", nsp_motivo="Queda sem dano, ja notificada pela enfermagem.")

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["nsp_decisao"] == "descartado"
        assert caso["nsp_decisao_motivo"] == "Queda sem dano, ja notificada pela enfermagem."
        assert caso["nsp_decidido_por"] == OUVIDOR["id"]
        assert _ciencias_do_nucleo(supabase) == []
        assert [e["destinatario"] for e in emails] == ["carlos@hsm.br"]

    def test_confirmar_na_validacao_envia_ao_nucleo_e_aciona_a_area(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="confirmado")

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["nsp_decisao"] == "confirmado"
        ciencias = _ciencias_do_nucleo(supabase)
        assert len(ciencias) == 1
        assert ciencias[0]["status"] == "pendente", "o acionamento da área não derruba a ciência do Núcleo"
        assert sorted(e["destinatario"] for e in emails) == ["carlos@hsm.br", "nsp@hsm.br"]

    def test_a_decisao_ja_tomada_nao_e_pedida_de_novo(self, monkeypatch):
        """O caso devolvido à Ouvidoria volta à validação: a decisão sobre o
        Núcleo já foi tomada e não trava o reacionamento."""
        client, _supabase = _client(monkeypatch, _banco(_caso_apontado(nsp_decisao="descartado")))

        r = _validar(client)

        assert r.status_code == 200, r.text
