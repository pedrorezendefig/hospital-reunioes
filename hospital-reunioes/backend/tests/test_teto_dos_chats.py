"""Os tetos do que os três chats de IA recebem (issue #893).

`chat-correcao`, `ata-guiada/chat` e `pops/{id}/elaboracao/chat` não limitavam
o corpo além dos 100 MB do app inteiro. Com a IA fora do loop (#773), até 16
montagens de prompt correm juntas, cada uma copiando o texto várias vezes, e
dez turnos de 100 MB num minuto derrubavam o processo único (e o `/health`).

Os tetos são iguais nas três rotas: 40 mensagens, 8.000 caracteres por
mensagem e 200.000 por campo de apoio. A recusa é 422 com frase de gente, e não
o `detail` em lista do pydantic, que a tela mostraria como JSON cru.

Cada teto é provado pela rota, no limite (200) e um caractere acima (422).
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ata_guiada import CURRENT_USER, FACILITADOR, _reuniao_programada, _SupabaseMock  # noqa: E402
from test_pops_elaboracao import ELABORADOR, _client_para, _sb  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import ai_processor  # noqa: E402

CORRECAO = "correcao"
GUIADA = "guiada"
POP = "pop"
ROTAS = (CORRECAO, GUIADA, POP)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _ia_em_mock(monkeypatch):
    """O pytest carrega o `.env` real: sem isso o 200 bateria no provedor de verdade."""
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")


def _cliente_de_reunioes(monkeypatch, reuniao: dict) -> TestClient:
    """O router de Reuniões com um Facilitador que enxerga a Reunião.

    Espelha `test_ia_fora_do_loop._cliente_de_reunioes` em vez de importá-la,
    pelo mesmo motivo de lá (fixture importada vira redefinição para o linter).
    """
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")
    sb = _SupabaseMock(reunioes=[reuniao])
    app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _facilitador(*_a, **_kw):
        return dict(FACILITADOR)

    async def _sem_restricao(*_a, **_kw):
        return None

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _facilitador)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _sem_restricao)
    return TestClient(app)


def _enviar(rota: str, monkeypatch, **corpo):
    """Manda um turno à rota pedida, com uma mensagem curta se o teste não deu outras."""
    corpo.setdefault("messages", [{"role": "user", "content": "Oi"}])
    if rota == CORRECAO:
        reuniao = _reuniao_programada(
            status_ata="AGUARDANDO_VALIDACAO",
            json_ata={"resumo_executivo": "Resumo", "quadro_atribuicoes": []},
        )
        return _cliente_de_reunioes(monkeypatch, reuniao).post("/api/reunioes/R1/chat-correcao", json=corpo)
    if rota == GUIADA:
        corpo.setdefault("rascunho", {})
        return _cliente_de_reunioes(monkeypatch, _reuniao_programada()).post(
            "/api/reunioes/R1/ata-guiada/chat", json=corpo
        )
    corpo.setdefault("rascunho", {})
    return _client_para(ELABORADOR, _sb()).post("/api/pops/pop-1/elaboracao/chat", json=corpo)


def _conversa(quantas: int) -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"fala {i}"} for i in range(quantas)]


def _recusa_legivel(resposta) -> str:
    assert resposta.status_code == 422, resposta.text
    detail = resposta.json()["detail"]
    assert isinstance(detail, str), f"a recusa veio no formato do pydantic: {detail!r}"
    return detail


class TestQuantidadeDeMensagens:
    @pytest.mark.parametrize("rota", ROTAS)
    def test_quarenta_mensagens_passam(self, rota, monkeypatch):
        resposta = _enviar(rota, monkeypatch, messages=_conversa(40))
        assert resposta.status_code == 200, resposta.text

    @pytest.mark.parametrize("rota", ROTAS)
    def test_quarenta_e_uma_mensagens_sao_recusadas_com_frase(self, rota, monkeypatch):
        detail = _recusa_legivel(_enviar(rota, monkeypatch, messages=_conversa(41)))
        assert "40 mensagens" in detail


class TestTamanhoDaMensagem:
    """O teto vale para cada fala do histórico, e não só para a última."""

    @pytest.mark.parametrize("rota", ROTAS)
    def test_mensagem_de_oito_mil_caracteres_passa(self, rota, monkeypatch):
        conversa = [{"role": "user", "content": "a" * 8000}]
        resposta = _enviar(rota, monkeypatch, messages=conversa)
        assert resposta.status_code == 200, resposta.text

    @pytest.mark.parametrize("rota", ROTAS)
    def test_mensagem_um_caractere_acima_e_recusada_com_frase(self, rota, monkeypatch):
        conversa = [*_conversa(2), {"role": "user", "content": "a" * 8001}]
        detail = _recusa_legivel(_enviar(rota, monkeypatch, messages=conversa))
        assert "8.000 caracteres" in detail
