"""Testes da Ata Guiada (issue #48, ADR 0005) — segundo modo de gerar a Ata.

Numa Reunião PROGRAMADA, o Facilitador conversa com um agente (texto) que monta
um `json_ata` enxuto (`resumo_executivo` + `quadro_atribuicoes`); ao concluir, a
Reunião vai a AGUARDANDO_VALIDACAO com `metodo_geracao=GUIADA` e o fluxo existente
(aprovar-sem-assinatura → liberar_pendencias) assume. Nesta fatia (F1) o agente é
MOCK — a IA real entra na F2.

Espelha o padrão de mock de `test_aprovar_sem_assinatura.py` (Supabase fake +
auth/papel plugados). LLM e ClickSign nunca são tocados de verdade.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import (  # noqa: E402
    get_current_user,
    get_supabase_client,
)
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    """Mock fluente: select/insert/update/delete + eq/in_/ilike/order/limit."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._ilike: tuple[str, str] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def in_(self, col, values):
        self._in_filters.append((col, list(values)))
        return self

    def ilike(self, col, pattern):
        self._ilike = (col, pattern)
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, r: dict) -> bool:
        for col, value in self._filters:
            if r.get(col) != value:
                return False
        for col, values in self._in_filters:
            if r.get(col) not in values:
                return False
        if self._ilike is not None:
            col, pattern = self._ilike
            needle = pattern.strip("%").lower()
            if needle not in str(r.get(col) or "").lower():
                return False
        return True

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for it in items:
                self._rows.append(dict(it))
            return _Result(data=[dict(it) for it in items])

        matched = [r for r in self._rows if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            matched.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]

        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))
        if self._op == "delete":
            for r in list(matched):
                self._rows.remove(r)
            return _Result(data=list(matched))
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        if name == "audit_log":
            return _TableQuery(self.audit_log)
        if name == "reuniao_participantes":
            return _TableQuery(self.reuniao_participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ──────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}
FACILITADOR = {"id": "P_DIR", "email": "diretor@hospital.com", "access_profile": "regular"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda o contador de rate-limit num storage global (por IP) que
    persiste entre testes — os POSTs deste módulo (todos como 'testclient') somariam
    aos de outros arquivos no mesmo endpoint e estourariam o 10/min. Zera antes de cada
    teste pra cada um partir limpo, independente de ordem da suíte."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def _mock_llm_by_default(monkeypatch):
    """O pytest carrega o `.env` real (chave OpenRouter de PROD); sem isso, qualquer
    teste que chegue a `chat_ata_guiada` bateria no serviço real. Força o caminho
    MOCK por padrão — os testes da IA real sobrescrevem com `_stub_openrouter`."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture
def make_client(monkeypatch):
    """Factory que monta TestClient com supabase mock + auth/papel plugados.

    Por padrão o usuário é um Facilitador comum (não Secretária).
    """

    def _factory(
        supabase: _SupabaseMock,
        *,
        is_secretaria_override: bool = False,
        allowed_ids: list | None = None,
    ) -> TestClient:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        from app.limiter import limiter

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(reunioes_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return dict(FACILITADOR)

        async def _fake_allowed(*_a, **_kw):
            return allowed_ids  # None = sem restrição; lista = restrito a esses ids

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        return TestClient(app)

    return _factory


def _acao(acao: str, responsavel: str, prazo: str | None = None) -> dict:
    return {"acao": acao, "responsavel": responsavel, "prazo": prazo}


def _reuniao_programada(**over) -> dict:
    base = {
        "id_reuniao": "R1",
        "status_ata": "PROGRAMADA",
        "metodo_geracao": "TRANSCRICAO",
        "json_ata": None,
        "tipo": "Gerencial",
    }
    base.update(over)
    return base


# ─── Fake LLM (nunca toca o OpenRouter real) ─────────────────────────────────


class _FakeCompletions:
    def __init__(self, *, content: str | None, exc: Exception | None, calls: list):
        self._content = content
        self._exc = exc
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class _FakeLLMClient:
    """Cliente OpenAI-like (`.chat.completions.create`) que devolve um `content`
    canned ou levanta `exc`. `calls` acumula os kwargs de cada chamada — pra checar
    `temperature`/`response_format` e contar chamadas (sem failover)."""

    def __init__(self, *, content: str | None = None, exc: Exception | None = None):
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content=content, exc=exc, calls=self.calls))


def _stub_openrouter(monkeypatch, *, content: str | None = None, exc: Exception | None = None) -> _FakeLLMClient:
    """Força o provider 'openrouter' e injeta um cliente fake — sobrescreve o
    `_mock_llm_by_default`. Devolve o cliente pra inspecionar `client.calls`."""
    from app.services import ai_processor

    client = _FakeLLMClient(content=content, exc=exc)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (client, "modelo-teste", {}))
    return client


# ═══════════════════════════════════════════════════════════════════════════
# POST /reunioes/{id}/ata-guiada/concluir
# ═══════════════════════════════════════════════════════════════════════════


class TestConcluir:
    def test_concluir_persiste_ata_guiada_enxuta(self, make_client):
        """Concluir a partir de PROGRAMADA grava o json_ata enxuto (resumo +
        quadro), marca metodo_geracao=GUIADA e leva a Reunião a
        AGUARDANDO_VALIDACAO — daí o fluxo de validação existente assume."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb)
        rascunho = {
            "resumo_executivo": "1-a-1 sobre o plano do trimestre.",
            "quadro_atribuicoes": [
                _acao("Enviar orçamento", "Pedro Rezende", "2026-06-20"),
            ],
        }

        r = client.post("/api/reunioes/R1/ata-guiada/concluir", json={"rascunho": rascunho})

        assert r.status_code == 200
        assert r.json()["status"] == "AGUARDANDO_VALIDACAO"

        row = sb.reunioes[0]
        assert row["status_ata"] == "AGUARDANDO_VALIDACAO"
        assert row["metodo_geracao"] == "GUIADA"
        assert row["json_ata"]["resumo_executivo"] == "1-a-1 sobre o plano do trimestre."
        assert len(row["json_ata"]["quadro_atribuicoes"]) == 1
        # Shape enxuto: nada das seções da Ata por Transcrição.
        assert "discussao" not in row["json_ata"]
        assert "participantes" not in row["json_ata"]

    def test_fluxo_concluir_ate_pendencias(self, make_client):
        """Ponta-a-ponta: concluir uma Ata Guiada com N ações e finalizar sem
        assinatura cria N Pendências (origem Reunião — `id_reuniao` setado,
        `id_nota` nulo) e leva a Reunião a APROVADA, reusando o fluxo existente."""
        sb = _SupabaseMock(
            participantes=[
                {"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"},
                {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"},
            ],
            reunioes=[_reuniao_programada()],
        )
        client = make_client(sb)
        rascunho = {
            "resumo_executivo": "Alinhamento do trimestre.",
            "quadro_atribuicoes": [
                _acao("Comprar insumos", "Pedro Rezende", "2026-06-20"),
                _acao("Revisar protocolo", "Ana Lima", "25/06/2026"),
            ],
        }

        r1 = client.post("/api/reunioes/R1/ata-guiada/concluir", json={"rascunho": rascunho})
        assert r1.status_code == 200
        assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_VALIDACAO"

        # Mesmo endpoint de finalização sem assinatura da Ata por Transcrição.
        r2 = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r2.status_code == 200
        assert r2.json()["status"] == "APROVADA"
        assert r2.json()["total_pendencias"] == 2

        assert sb.reunioes[0]["status_ata"] == "APROVADA"
        assert len(sb.pendencias) == 2
        assert all(p["id_reuniao"] == "R1" for p in sb.pendencias)
        assert all(p.get("id_nota") is None for p in sb.pendencias)
        assert all(p["status"] == "PENDENTE" for p in sb.pendencias)

    def test_acao_sem_prazo_conclui_e_fica_a_definir(self, make_client):
        """Ação sem prazo não trava a conclusão: a Ata fecha e a Pendência nasce
        com prazo nulo (exibido como 'A definir' na UI)."""
        sb = _SupabaseMock(
            participantes=[{"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"}],
            reunioes=[_reuniao_programada()],
        )
        client = make_client(sb)
        rascunho = {
            "resumo_executivo": "Conversa rápida.",
            "quadro_atribuicoes": [_acao("Acompanhar caso", "Pedro Rezende", prazo=None)],
        }

        r1 = client.post("/api/reunioes/R1/ata-guiada/concluir", json={"rascunho": rascunho})
        assert r1.status_code == 200

        r2 = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r2.status_code == 200
        assert r2.json()["total_pendencias"] == 1
        assert sb.pendencias[0]["prazo"] is None

    def test_concluir_secretaria_bloqueada_403(self, make_client):
        """Secretária não cria/conclui Ata — mesmo controle da Ata por Transcrição."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb, is_secretaria_override=True)
        r = client.post(
            "/api/reunioes/R1/ata-guiada/concluir",
            json={"rascunho": {"resumo_executivo": "x", "quadro_atribuicoes": []}},
        )
        assert r.status_code == 403
        # Guard vem antes de tudo: a Reunião não é tocada.
        assert sb.reunioes[0]["status_ata"] == "PROGRAMADA"
        assert sb.reunioes[0]["metodo_geracao"] == "TRANSCRICAO"

    def test_concluir_so_a_partir_de_programada_400(self, make_client):
        """Concluir uma Ata Guiada só faz sentido a partir de PROGRAMADA."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada(status_ata="AGUARDANDO_VALIDACAO")])
        client = make_client(sb)
        r = client.post(
            "/api/reunioes/R1/ata-guiada/concluir",
            json={"rascunho": {"resumo_executivo": "x", "quadro_atribuicoes": []}},
        )
        assert r.status_code == 400
        assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_VALIDACAO"

    def test_concluir_reuniao_inexistente_404(self, make_client):
        sb = _SupabaseMock(reunioes=[])
        client = make_client(sb)
        r = client.post("/api/reunioes/NOPE/ata-guiada/concluir", json={"rascunho": {}})
        assert r.status_code == 404

    def test_concluir_fora_da_visibilidade_404(self, make_client):
        """Facilitador não conclui (nem enxerga) Reunião fora do seu escopo — 404, sem
        sobrescrever a Ata de uma Reunião alheia conhecendo só o id (IDOR de escrita)."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb, allowed_ids=["OUTRA"])  # R1 não está na lista permitida
        r = client.post(
            "/api/reunioes/R1/ata-guiada/concluir",
            json={"rascunho": {"resumo_executivo": "x", "quadro_atribuicoes": []}},
        )
        assert r.status_code == 404
        assert sb.reunioes[0]["status_ata"] == "PROGRAMADA"  # intacta

    def test_concluir_descarta_item_de_quadro_malformado(self, make_client):
        """Item não-dict no quadro é descartado na conclusão — não deixa
        liberar_pendencias (que faz acao.get(...)) quebrar com 500 depois."""
        sb = _SupabaseMock(
            participantes=[{"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"}],
            reunioes=[_reuniao_programada()],
        )
        client = make_client(sb)
        rascunho = {
            "resumo_executivo": "ok",
            "quadro_atribuicoes": [_acao("Comprar insumos", "Pedro Rezende"), "lixo", 123],
        }

        r1 = client.post("/api/reunioes/R1/ata-guiada/concluir", json={"rascunho": rascunho})
        assert r1.status_code == 200
        assert len(sb.reunioes[0]["json_ata"]["quadro_atribuicoes"]) == 1  # só o dict sobrou

        r2 = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r2.status_code == 200
        assert r2.json()["total_pendencias"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# POST /reunioes/{id}/ata-guiada/chat  (agente — MOCK na F1)
# ═══════════════════════════════════════════════════════════════════════════


class TestChat:
    def test_chat_devolve_reply_e_rascunho(self, make_client):
        """O chat (mock em F1) recebe rascunho + mensagens e devolve uma resposta
        e o rascunho atualizado no shape enxuto (resumo + quadro)."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb)
        r = client.post(
            "/api/reunioes/R1/ata-guiada/chat",
            json={
                "rascunho": {"resumo_executivo": "", "quadro_atribuicoes": []},
                "messages": [{"role": "user", "content": "Tivemos um 1-a-1 sobre o orçamento."}],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("reply"), str) and body["reply"]
        assert "resumo_executivo" in body["rascunho"]
        assert "quadro_atribuicoes" in body["rascunho"]

    def test_chat_secretaria_bloqueada_403(self, make_client):
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb, is_secretaria_override=True)
        r = client.post(
            "/api/reunioes/R1/ata-guiada/chat",
            json={"rascunho": {}, "messages": [{"role": "user", "content": "oi"}]},
        )
        assert r.status_code == 403

    def test_chat_so_em_programada_400(self, make_client):
        """O chat monta a Ata antes dela existir — não cabe depois de PROGRAMADA."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada(status_ata="AGUARDANDO_VALIDACAO")])
        client = make_client(sb)
        r = client.post(
            "/api/reunioes/R1/ata-guiada/chat",
            json={"rascunho": {}, "messages": [{"role": "user", "content": "oi"}]},
        )
        assert r.status_code == 400

    def test_chat_mensagens_vazias_422(self, make_client):
        sb = _SupabaseMock(reunioes=[_reuniao_programada()])
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/ata-guiada/chat", json={"rascunho": {}, "messages": []})
        assert r.status_code == 422


class TestServicoAgente:
    def test_mock_incorpora_relato_no_resumo(self):
        """MOCK (F1): sem IA, o agente joga o relato do Facilitador no resumo — dá
        sinal de vida e habilita o concluir. Shape enxuto preservado."""
        from app.services.ai_processor import chat_ata_guiada

        out = chat_ata_guiada(rascunho={}, messages=[{"role": "user", "content": "relato da reunião"}])
        assert isinstance(out["reply"], str) and out["reply"]
        assert out["rascunho"]["resumo_executivo"] == "relato da reunião"
        assert out["rascunho"]["quadro_atribuicoes"] == []

    def test_mock_preserva_quadro_existente(self):
        from app.services.ai_processor import chat_ata_guiada

        rascunho = {"resumo_executivo": "antigo", "quadro_atribuicoes": [{"acao": "X", "responsavel": "Y"}]}
        out = chat_ata_guiada(rascunho=rascunho, messages=[{"role": "user", "content": "novo relato"}])
        assert "novo relato" in out["rascunho"]["resumo_executivo"]
        assert len(out["rascunho"]["quadro_atribuicoes"]) == 1  # quadro não é apagado


# ═══════════════════════════════════════════════════════════════════════════
# Serviço chat_ata_guiada — IA real (F2, issue #49). LLM SEMPRE mockado: testa
# o contrato (shape, parâmetros, erro, mock-first), nunca a qualidade do texto.
# ═══════════════════════════════════════════════════════════════════════════


class TestServicoAgenteIA:
    def test_ia_real_devolve_rascunho_enxuto(self, monkeypatch):
        """Com chave, o agente chama a IA e devolve `{reply, rascunho}` no shape
        enxuto (resumo + quadro consumível por liberar_pendencias)."""
        from app.services import ai_processor

        ia_rascunho = {
            "resumo_executivo": "1-a-1 sobre o orçamento do trimestre.",
            "quadro_atribuicoes": [
                {
                    "acao": "Enviar a planilha de orçamento",
                    "responsavel": "Pedro Rezende",
                    "cargo": "Diretor",
                    "prazo": "2026-06-20",
                    "entregavel": "Planilha consolidada",
                }
            ],
        }
        _stub_openrouter(
            monkeypatch,
            content=json.dumps({"reply": "Combinado. Mais alguma ação?", "rascunho": ia_rascunho}),
        )

        out = ai_processor.chat_ata_guiada(
            rascunho={"resumo_executivo": "", "quadro_atribuicoes": []},
            messages=[{"role": "user", "content": "Tivemos um 1-a-1; o Pedro envia a planilha até dia 20."}],
        )

        assert isinstance(out["reply"], str) and out["reply"]
        # Shape enxuto preservado (só resumo + quadro, nada das 6 seções).
        assert set(out["rascunho"]) >= {"resumo_executivo", "quadro_atribuicoes"}
        assert isinstance(out["rascunho"]["resumo_executivo"], str)
        assert isinstance(out["rascunho"]["quadro_atribuicoes"], list)
        # A ação chega no shape que liberar_pendencias consome (acao/responsavel/prazo).
        acao = out["rascunho"]["quadro_atribuicoes"][0]
        assert acao["acao"] == "Enviar a planilha de orçamento"
        assert acao["responsavel"] == "Pedro Rezende"
        assert acao["prazo"] == "2026-06-20"

    def test_ia_real_usa_json_object_e_temperatura_sem_failover(self, monkeypatch):
        """A chamada usa `response_format=json_object` e `temperature≈0.3`, numa
        única requisição — OpenRouter-only, sem failover."""
        from app.services import ai_processor

        client = _stub_openrouter(
            monkeypatch,
            content=json.dumps({"reply": "ok", "rascunho": {"resumo_executivo": "r", "quadro_atribuicoes": []}}),
        )

        ai_processor.chat_ata_guiada(rascunho={}, messages=[{"role": "user", "content": "relato"}])

        assert len(client.calls) == 1  # sem failover: uma única chamada
        call = client.calls[0]
        assert call["response_format"] == {"type": "json_object"}
        assert call["temperature"] == 0.3

    def test_ia_indisponivel_devolve_mensagem_clara_e_preserva_rascunho(self, monkeypatch):
        """OpenRouter fora do ar não derruba o request (nada de 500 cru): devolve um
        reply claro e preserva o rascunho atual (o Facilitador não perde o trabalho)."""
        from app.services import ai_processor

        _stub_openrouter(monkeypatch, exc=RuntimeError("502 Bad Gateway"))
        rascunho_in = {
            "resumo_executivo": "Trabalho já em andamento.",
            "quadro_atribuicoes": [{"acao": "Comprar insumos", "responsavel": "Pedro"}],
        }

        out = ai_processor.chat_ata_guiada(rascunho=rascunho_in, messages=[{"role": "user", "content": "e agora?"}])

        assert isinstance(out["reply"], str) and out["reply"]  # mensagem clara, não exceção
        # Rascunho preservado — não devolve quadro vazio nem perde o resumo.
        assert out["rascunho"]["resumo_executivo"] == "Trabalho já em andamento."
        assert len(out["rascunho"]["quadro_atribuicoes"]) == 1

    def test_sem_chave_usa_mock_sem_instanciar_cliente(self, monkeypatch):
        """CA4: sem chave (`_llm_provider == 'mock'`), o agente nem instancia o
        cliente — cai no mock e não quebra o endpoint."""
        from app.services import ai_processor

        # provider 'mock' já é o default da fixture _mock_llm_by_default.
        def _boom():
            raise AssertionError("_get_llm não deve ser chamado no caminho mock")

        monkeypatch.setattr(ai_processor, "_get_llm", _boom)

        out = ai_processor.chat_ata_guiada(rascunho={}, messages=[{"role": "user", "content": "relato do 1-a-1"}])

        assert out["rascunho"]["resumo_executivo"] == "relato do 1-a-1"
        assert out["rascunho"]["quadro_atribuicoes"] == []

    def test_ia_que_omite_quadro_mantem_shape_enxuto(self, monkeypatch):
        """CA2: se a IA devolver rascunho sem `quadro_atribuicoes`, o serviço ainda
        garante o shape enxuto (quadro continua lista) — preserva o quadro atual."""
        from app.services import ai_processor

        _stub_openrouter(
            monkeypatch,
            content=json.dumps({"reply": "Anotado.", "rascunho": {"resumo_executivo": "novo resumo"}}),
        )
        rascunho_in = {"resumo_executivo": "antigo", "quadro_atribuicoes": [{"acao": "X", "responsavel": "Y"}]}

        out = ai_processor.chat_ata_guiada(rascunho=rascunho_in, messages=[{"role": "user", "content": "..."}])

        assert out["rascunho"]["resumo_executivo"] == "novo resumo"
        assert isinstance(out["rascunho"]["quadro_atribuicoes"], list)
        assert len(out["rascunho"]["quadro_atribuicoes"]) == 1  # quadro atual preservado
        assert out["rascunho"]["quadro_atribuicoes"][0]["acao"] == "X"  # mesmo item, não placeholder

    def test_ia_resposta_nao_objeto_nao_derruba(self, monkeypatch):
        """`json_object` é só um hint — se a IA devolver um JSON que não é objeto
        (lista, string, null), o serviço não derruba o request (nada de 500 cru):
        erro claro + rascunho preservado."""
        from app.services import ai_processor

        _stub_openrouter(monkeypatch, content="[1, 2, 3]")
        rascunho_in = {"resumo_executivo": "em andamento", "quadro_atribuicoes": [{"acao": "X", "responsavel": "Y"}]}

        out = ai_processor.chat_ata_guiada(rascunho=rascunho_in, messages=[{"role": "user", "content": "oi"}])

        assert isinstance(out["reply"], str) and out["reply"]
        assert out["rascunho"]["resumo_executivo"] == "em andamento"
        assert len(out["rascunho"]["quadro_atribuicoes"]) == 1

    def test_ia_rascunho_em_tipo_errado_cai_no_atual(self, monkeypatch):
        """Se a IA devolver um objeto válido mas com `rascunho` num tipo errado
        (string/lista), o normalizador cai no rascunho atual em vez de quebrar."""
        from app.services import ai_processor

        _stub_openrouter(monkeypatch, content=json.dumps({"reply": "ok", "rascunho": "pronto"}))
        rascunho_in = {"resumo_executivo": "preservar", "quadro_atribuicoes": [{"acao": "X", "responsavel": "Y"}]}

        out = ai_processor.chat_ata_guiada(rascunho=rascunho_in, messages=[{"role": "user", "content": "oi"}])

        assert out["rascunho"]["resumo_executivo"] == "preservar"
        assert len(out["rascunho"]["quadro_atribuicoes"]) == 1

    def test_prompts_da_ata_guiada_versionados(self):
        """CA6: os dois prompts (system + user) existem e carregam; o user renderiza
        as variáveis do template."""
        from app.services.prompt_loader import load_prompt, render_prompt

        assert load_prompt("chat_ata_guiada_system").strip()

        user = render_prompt(
            "chat_ata_guiada_user",
            rascunho_atual="{}",
            chat_history="Facilitador: oi",
            hoje_iso="2026-06-11",
        )
        assert "{{" not in user  # todas as variáveis substituídas
        assert "2026-06-11" in user


# ═══════════════════════════════════════════════════════════════════════════
# GET /reunioes/{id} — contrato do metodo_geracao no detalhe (issue #51)
# ═══════════════════════════════════════════════════════════════════════════


class TestDetalheExpoeMetodoGeracao:
    """A tela de detalhe usa `metodo_geracao` para o badge da Ata Guiada e para
    esconder as ações do fluxo por Transcrição (Solicitar Correção / Enviar para
    assinatura). O detalhe (`get_reuniao`) não tem `response_model` de propósito —
    estes testes travam que o campo continua chegando ao frontend (pegam regressão
    se alguém adicionar um schema que o filtre)."""

    def test_detalhe_guiada_expoe_metodo_geracao(self, make_client):
        sb = _SupabaseMock(
            reunioes=[
                _reuniao_programada(
                    status_ata="AGUARDANDO_VALIDACAO",
                    metodo_geracao="GUIADA",
                    json_ata={"resumo_executivo": "1-a-1", "quadro_atribuicoes": []},
                )
            ]
        )
        client = make_client(sb)

        r = client.get("/api/reunioes/R1")

        assert r.status_code == 200
        assert r.json()["metodo_geracao"] == "GUIADA"

    def test_detalhe_transcricao_expoe_metodo_geracao(self, make_client):
        """Ata por Transcrição (default) continua expondo metodo_geracao=TRANSCRICAO —
        o frontend trata como o fluxo normal: sem badge, ações presentes."""
        sb = _SupabaseMock(reunioes=[_reuniao_programada(status_ata="AGUARDANDO_VALIDACAO")])
        client = make_client(sb)

        r = client.get("/api/reunioes/R1")

        assert r.status_code == 200
        assert r.json()["metodo_geracao"] == "TRANSCRICAO"
