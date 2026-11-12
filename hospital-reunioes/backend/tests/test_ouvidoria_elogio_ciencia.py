"""O elogio como acionamento de ciência (issue #1618, PRD #1527, ADR 0088).

O elogio vai ao setor só para ele confirmar que recebeu: sem prazo de resposta,
sem cobrança e fora dos vencidos. O responsável clica em "Elogio recebido" no
email, sem senha, e o caso volta ao ouvidor como Pronto para encerrar. Sem o
clique em 5 dias úteis o email sai de novo, uma vez só. No encerramento, quem
elogiou e deixou um email recebe "Seu elogio foi entregue à equipe."

Os dublês de banco são os da validação (`test_ouvidoria_validacao_acionamento`):
o acionamento de ciência nasce pela MESMA porta, e um segundo fake com regras
próprias deixaria os dois caminhos divergirem sem ninguém notar.
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
    _manifestacao,
    _SupabaseFake,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

NOTA_DO_OUVIDOR = "A familia agradece a equipe da Recepcao pelo acolhimento no plantao de domingo."

ELOGIO = {
    "tipo_manifestacao": "elogio",
    "categoria": "Acolhimento",
    "setor": "Recepcao",
    "gravidade": "baixo",
    "extrato_para_o_setor": NOTA_DO_OUVIDOR,
}


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


def _client(monkeypatch, supabase: _SupabaseFake | None = None, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
    """O painel do ouvidor e o link do email no mesmo app, sobre o mesmo banco:
    o elogio nasce numa porta e é confirmado na outra."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _validar_o_elogio(monkeypatch, supabase: _SupabaseFake | None = None):
    client, supabase = _client(monkeypatch, supabase)
    r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=ELOGIO)
    assert r.status_code == 200, r.text
    return client, supabase


# =====================================================================
# 1. Validar um elogio cria a ciência, sem vencimento de área
# =====================================================================


class TestValidarOElogio:
    def test_validar_um_elogio_cria_uma_ciencia_com_motivo_elogio(self, monkeypatch):
        _client_, supabase = _validar_o_elogio(monkeypatch)

        acionamentos = supabase.tabelas["ouvidoria_acionamentos"]
        assert len(acionamentos) == 1
        ciencia = acionamentos[0]
        assert ciencia["manifestacao_id"] == "uuid-7"
        assert ciencia["tipo"] == "ciencia"
        assert ciencia["motivo_ciencia"] == "elogio"
        assert ciencia["status"] == "pendente"
        assert ciencia["setor"] == "Recepcao"
        assert ciencia["responsavel_email"] == "carlos@hsm.br"
        assert ciencia["prazo"] is None

    def test_o_elogio_validado_nao_grava_vencimento_de_area(self, monkeypatch):
        """A gravidade baixa não tem prazo de área na tabela, então o teste
        valida o elogio como MÉDIO, que tem: o vencimento não pode nascer nem
        quando a tabela teria um para dar."""
        client, supabase = _client(monkeypatch)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**ELOGIO, "gravidade": "medio"})

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == "Recepcao"
        assert caso["validada_em"]
        assert caso["prazo_area_em"] is None, "elogio não tem prazo de resposta da área"
        assert r.json()["prazo_area_em"] is None

    def test_o_responsavel_recebe_o_email_com_o_botao_elogio_recebido(self, monkeypatch, emails):
        _validar_o_elogio(monkeypatch)

        assert [e["destinatario"] for e in emails] == ["carlos@hsm.br"]
        email = emails[0]
        assert "Elogio recebido" in email["html"]
        assert NOTA_DO_OUVIDOR in email["html"] and NOTA_DO_OUVIDOR in email["texto"]
        assert re.search(r"/ouvidoria-setor/elogio/[A-Za-z0-9_-]{20,}", email["html"])
        assert "Prazo" not in email["texto"], "o elogio não cobra prazo de ninguém"

    def test_o_elogio_nao_abre_o_portal_de_resposta(self, monkeypatch):
        """O setor só confirma que recebeu: nenhum link do portal de resposta
        nasce, e nenhuma linha de acionamento de resposta vai para a fila."""
        _client_, supabase = _validar_o_elogio(monkeypatch)

        assert supabase.tabelas.get("ouvidoria_setor_tokens", []) == []
        gatilhos = [n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]]
        assert gatilhos == [ouvidoria_notificacoes.GATILHO_CIENCIA_ELOGIO]

    def test_reclamacao_continua_com_o_acionamento_de_resposta(self, monkeypatch):
        """O tipo decide o acionamento, e só o elogio vira ciência (ADR 0088,
        decisão 1)."""
        client, supabase = _client(monkeypatch)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**ELOGIO, "tipo_manifestacao": "reclamacao", "gravidade": "medio"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas.get("ouvidoria_acionamentos", []) == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"]
        gatilhos = [n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]]
        assert gatilhos == [ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA]
