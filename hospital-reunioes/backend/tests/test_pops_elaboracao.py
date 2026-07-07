"""Testes da elaboração de POP — tela POP vivo + chat do agente (issue #83).

A Elaboração (docs/pops/CONTEXT.md): o Elaborador designado conversa com o
agente e as seções do template institucional tomam forma ao vivo. Diferença
deliberada da Ata Guiada (PRD #76): o rascunho PERSISTE na Versão a cada
interação (elaboração dura dias); o histórico do chat é efêmero. O agente
sugere a Periodicidade de revisão e o Elaborador escolhe a final. "Aprovar
versão final" → EM_REVISAO + auditoria + email ao Revisor.

LLM SEMPRE mockado (padrão test_ata_guiada): testa o contrato (shape,
persistência, seção apontada no prompt), nunca a qualidade do texto.
Supabase mock no padrão de test_pops_criar.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import elaboracao as elaboracao_router  # noqa: E402
from app.services import pops_email_service  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_criar) ────────────────────────────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def execute(self):
        if self._insert_payload is not None:
            inserted = []
            for row in self._insert_payload:
                row = dict(row)
                row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
                self._rows.append(row)
                inserted.append(dict(row))
            return _Result(data=inserted)

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
        ]

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(pid: str, perfil_pop: str | None = None) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": perfil_pop,
    }


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
        "setor_id": "s-cti",
        "numero": 1,
        "codigo": "HSM_CTI-001",
        "nome": "Higienização das Mãos",
        "criticidade": "CRITICA",
        "base_normativa": "RDC 63/2011",
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P4",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


def _versao(**over) -> dict:
    base = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "A_ELABORAR",
        "rascunho": None,
        "periodicidade_sugerida": None,
    }
    base.update(over)
    return base


# Elaborador designado do pop-1 (default de quem loga nos testes).
ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR = _pessoa("P2", perfil_pop="gestor_qualidade")
VALIDADOR = _pessoa("P3", perfil_pop="gerente")
INTRUSO = _pessoa("P4", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("P5", perfil_pop=None)


def _sb(versao: dict | None = None, pop: dict | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [ELABORADOR, REVISOR, VALIDADOR, INTRUSO, SEM_PERFIL],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
            # O reenvio consulta as Devoluções para decidir o destino (#85).
            "pops_devolucoes": [],
            "pops_materiais_referencia": [],
            "audit_log": [],
        }
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O limiter do slowapi acumula hits por IP entre arquivos da suíte (storage
    global); zera antes de cada teste pra cada um partir limpo."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def _mock_llm_by_default(monkeypatch):
    """O pytest carrega o `.env` real (chave OpenRouter de PROD); força o caminho
    MOCK por padrão — os testes da IA real sobrescrevem com `_stub_openrouter`."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    """Captura emails no boundary de IO — template e montagem rodam de verdade."""
    capturados: list[dict] = []

    def _fake_enviar(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
        capturados.append(
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return capturados


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(elaboracao_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ─── Fake LLM (nunca toca o OpenRouter real — padrão test_ata_guiada) ─────────


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
    def __init__(self, *, content: str | None = None, exc: Exception | None = None):
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content=content, exc=exc, calls=self.calls))


def _stub_openrouter(monkeypatch, *, content: str | None = None, exc: Exception | None = None) -> _FakeLLMClient:
    from app.services import ai_processor

    client = _FakeLLMClient(content=content, exc=exc)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (client, "modelo-teste", {}))
    return client


def _secao(titulo: str, conteudo: str = "Conteúdo.", tipo: str = "texto", sid: str | None = None) -> dict:
    s = {"titulo": titulo, "conteudo": conteudo, "tipo": tipo}
    if sid is not None:
        s["id"] = sid
    return s


def _resposta_ia(secoes: list[dict] | None = None, periodicidade: str | None = None, reply: str = "Anotei.") -> str:
    """Resposta do agente no shape novo (ADR 0016): lista de seções +
    periodicidade. Sem `id` nas seções = inéditas (o sistema atribui)."""
    return json.dumps(
        {
            "reply": reply,
            "secoes": secoes if secoes is not None else [_secao("Objetivo", "Padronizar a higienização das mãos.")],
            "periodicidade_sugerida": periodicidade,
        }
    )


def _chat(
    client: TestClient,
    *,
    rascunho: dict | None = None,
    mensagem: str = "Vamos começar pelo objetivo.",
    section_context: str | None = None,
):
    return client.post(
        "/api/pops/pop-1/elaboracao/chat",
        json={
            "rascunho": rascunho or {},
            "messages": [{"role": "user", "content": mensagem}],
            "section_context": section_context,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST /pops/{pop_id}/elaboracao/chat — contrato + rascunho persistente
# ═══════════════════════════════════════════════════════════════════════════


class TestChatElaboracao:
    def test_chat_devolve_reply_e_rascunho_e_persiste_na_versao(self, monkeypatch):
        """CA: o rascunho (lista de seções, ADR 0016) devolvido pelo agente
        persiste na Versão a cada interação — fechar a tela não perde a
        elaboração."""
        _stub_openrouter(
            monkeypatch,
            content=_resposta_ia([_secao("Objetivo", "Padronizar X."), _secao("Abrangência", "CTI.")]),
        )
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        body = res.json()
        assert body["reply"] == "Anotei."
        secoes = body["rascunho"]["secoes"]
        assert [s["titulo"] for s in secoes] == ["Objetivo", "Abrangência"]
        assert secoes[0]["conteudo"] == "Padronizar X."
        # Toda seção persistida ganha id estável e tipo.
        assert all(s["id"] for s in secoes)
        assert secoes[0]["tipo"] == "texto"
        persistido = sb.tables["pops_versoes"][0]["rascunho"]["secoes"]
        assert persistido[1]["titulo"] == "Abrangência"
        assert persistido[1]["conteudo"] == "CTI."

    def test_get_elaboracao_migra_rascunho_legado_para_secoes(self):
        """CA: rascunho legado (chaves fixas) é migrado para a lista de seções na
        leitura — POPs em andamento antes da mudança seguem funcionando. O
        Fluxograma legado vira seção de tipo `fluxograma`."""
        legado = {
            "objetivo": "Elaborado ontem.",
            "descricao_procedimento": "Passo 1.",
            "fluxograma": "1. Início\n2. Fim",
        }
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=legado, periodicidade_sugerida="6_meses"))
        client = _client_para(ELABORADOR, sb)

        res = client.get("/api/pops/pop-1/elaboracao")

        assert res.status_code == 200
        body = res.json()
        secoes = body["rascunho"]["secoes"]
        titulos = [s["titulo"] for s in secoes]
        assert titulos == ["Objetivo", "Descrição do procedimento", "Fluxograma"]
        assert secoes[0]["conteudo"] == "Elaborado ontem."
        flux = next(s for s in secoes if s["titulo"] == "Fluxograma")
        assert flux["tipo"] == "fluxograma"
        assert all(s["id"] for s in secoes)
        assert body["periodicidade_sugerida"] == "6_meses"
        assert body["versao"]["estado"] == "EM_ELABORACAO"
        assert body["pop"]["codigo"] == "HSM_CTI-001"
        # A Identificação (seção 1) renderiza dos dados do POP: nomes resolvidos.
        assert body["pop"]["elaborador_nome"] == "Pessoa P1"
        assert body["pop"]["revisor_nome"] == "Pessoa P2"
        assert body["pop"]["validador_nome"] == "Pessoa P3"

    def test_chat_primeira_interacao_move_a_elaborar_para_em_elaboracao(self, monkeypatch):
        """A_ELABORAR → EM_ELABORACAO na primeira interação, com auditoria
        (toda transição de estado é registrada — PRD #76)."""
        _stub_openrouter(monkeypatch, content=_resposta_ia())
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"
        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_INICIAR_ELABORACAO" in acoes

    def test_chat_interacao_seguinte_mantem_em_elaboracao_sem_reauditar(self, monkeypatch):
        _stub_openrouter(monkeypatch, content=_resposta_ia())
        rascunho = {"secoes": [{"id": "id-x", "titulo": "Objetivo", "conteudo": "Já existia.", "tipo": "texto"}]}
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=rascunho))
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"
        assert sb.tables["audit_log"] == []

    def test_chat_secao_apontada_presente_no_prompt(self, monkeypatch):
        """CA: o agente respeita a seção apontada (⌖) — ela chega no prompt
        para a correção dirigida."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        res = _chat(client, mensagem="[Seção: Objetivo]\nDeixa mais direto.", section_context="Objetivo")

        assert res.status_code == 200
        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "SEÇÃO APONTADA" in user_prompt
        assert "Objetivo" in user_prompt

    def test_chat_contexto_do_pop_no_prompt(self, monkeypatch):
        """O agente sabe O QUE está elaborando: código, nome, setor e base
        normativa do POP entram no prompt."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        _chat(client)

        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "HSM_CTI-001" in user_prompt
        assert "Higienização das Mãos" in user_prompt
        assert "Coordenação do CTI" in user_prompt
        assert "RDC 63/2011" in user_prompt

    def test_system_prompt_estrutura_dinamica_guiada_pelo_material(self, monkeypatch):
        """CA (ADR 0016): o prompt de sistema institui a estrutura DINÂMICA:
        espelha o modelo do Material de referência; sem modelo, propõe a
        estrutura institucional; sinaliza lacuna de acreditação sem travar."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        _chat(client)

        system_prompt = client_llm.calls[0]["messages"][0]["content"]
        prompt_lower = system_prompt.lower()
        # A estrutura espelha o modelo anexado e é dinâmica (cria/renomeia/reordena).
        assert "espelh" in prompt_lower or "modelo" in prompt_lower
        assert "secoes" in prompt_lower or "seções" in prompt_lower
        # Sem modelo, propõe a estrutura institucional de partida.
        for trecho in ("Objetivo", "Responsabilidades", "Descrição do procedimento", "Referências normativas"):
            assert trecho in system_prompt, f"Seção institucional ausente do prompt: {trecho}"
        # ONA/JCI de memória do modelo (sem RAG) + sinalização de lacuna sem travar.
        assert "ONA" in system_prompt
        assert "JCI" in system_prompt
        assert "sinaliz" in prompt_lower or "lacuna" in prompt_lower

    def test_system_prompt_e_o_arquivo_unico(self, monkeypatch):
        """CA (ADR 0021): o system prompt que chega à IA é o arquivo ÚNICO
        (a classificação por Natureza saiu do domínio na #189). A referência
        das três áreas viaja junta."""
        from app.services.prompt_loader import load_prompt

        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        _chat(client)

        system_prompt = client_llm.calls[0]["messages"][0]["content"]
        assert system_prompt == load_prompt("chat_elaboracao_pop_system")
        # As três áreas convivem no mesmo prompt (curadoria compacta).
        assert "CLT" in system_prompt
        assert "ANVISA" in system_prompt
        assert "ABNT" in system_prompt

    def test_contexto_do_pop_leva_o_nome_do_setor(self, monkeypatch):
        """CA (ADR 0021): a interpretação da área é da IA, pelo NOME do Setor
        que viaja no prompt (sem classificação persistida)."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        _chat(client)

        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "Coordenação do CTI" in user_prompt  # o nome do Setor segue no contexto

    def test_system_prompt_fluxograma_instrui_mermaid(self, monkeypatch):
        """CA (ADR 0017): a seção de tipo `fluxograma` carrega SINTAXE MERMAID
        emitida pelo agente (flowchart), não mais texto numerado parseado."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_ELABORACAO")))

        _chat(client)

        system_prompt = client_llm.calls[0]["messages"][0]["content"]
        assert "Mermaid" in system_prompt
        assert "flowchart" in system_prompt.lower()

    def test_chat_periodicidade_sugerida_persiste_na_versao(self, monkeypatch):
        """CA: a Periodicidade sugerida pelo agente fica gravada (na Versão) e
        volta na resposta para a UI exibir."""
        _stub_openrouter(monkeypatch, content=_resposta_ia(periodicidade="6_meses"))
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        assert res.json()["periodicidade_sugerida"] == "6_meses"
        assert sb.tables["pops_versoes"][0]["periodicidade_sugerida"] == "6_meses"

    def test_chat_sem_nova_sugestao_preserva_a_anterior(self, monkeypatch):
        """Turno sem sugestão (null) não apaga a sugestão já gravada."""
        _stub_openrouter(monkeypatch, content=_resposta_ia(periodicidade=None))
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", periodicidade_sugerida="1_ano"))
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["periodicidade_sugerida"] == "1_ano"

    def test_chat_nao_elaborador_403(self, monkeypatch):
        """CA: só o Elaborador designado elabora — até perfis de escopo total
        (Gestor de Qualidade) levam 403 no chat."""
        _stub_openrouter(monkeypatch, content=_resposta_ia())
        for pessoa in (INTRUSO, REVISOR):
            client = _client_para(pessoa, _sb())
            res = _chat(client)
            assert res.status_code == 403, f"{pessoa['id']} deveria levar 403"

    def test_chat_sem_perfil_pop_403(self):
        client = _client_para(SEM_PERFIL, _sb())
        res = _chat(client)
        assert res.status_code == 403

    def test_chat_estado_invalido_400(self, monkeypatch):
        """CA: transição/ação fora de estado válido → 400. Em EM_REVISAO a
        elaboração está fechada."""
        _stub_openrouter(monkeypatch, content=_resposta_ia())
        for estado in ("EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO"):
            client = _client_para(ELABORADOR, _sb(versao=_versao(estado=estado)))
            res = _chat(client)
            assert res.status_code == 400, f"estado {estado} deveria dar 400"

    def test_chat_pop_inexistente_404(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.post(
            "/api/pops/pop-999/elaboracao/chat",
            json={"rascunho": {}, "messages": [{"role": "user", "content": "oi"}]},
        )
        assert res.status_code == 404

    def test_chat_mensagens_vazias_422(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.post("/api/pops/pop-1/elaboracao/chat", json={"rascunho": {}, "messages": []})
        assert res.status_code == 422

    def test_chat_ia_indisponivel_preserva_rascunho_sem_persistir(self, monkeypatch):
        """IA fora do ar: resposta clara, rascunho do request preservado e NADA
        persiste/transiciona (a interação não aconteceu de fato)."""
        _stub_openrouter(monkeypatch, exc=RuntimeError("502 Bad Gateway"))
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(ELABORADOR, sb)
        rascunho_in = {"secoes": [{"id": "id-o", "titulo": "Objetivo", "conteudo": "Montado antes.", "tipo": "texto"}]}

        res = _chat(client, rascunho=rascunho_in)

        assert res.status_code == 200
        body = res.json()
        # O rascunho do request volta intacto (seções e ids preservados).
        assert body["rascunho"]["secoes"] == rascunho_in["secoes"]
        assert "erro" not in body
        assert sb.tables["pops_versoes"][0]["rascunho"] is None
        assert sb.tables["pops_versoes"][0]["estado"] == "A_ELABORAR"

    def test_chat_sem_chave_usa_mock_e_nao_quebra(self):
        """Sem chave LLM (provider mock, default da fixture), o endpoint
        responde com sinal de vida — não quebra a tela."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        assert "[MOCK]" in res.json()["reply"]


# ═══════════════════════════════════════════════════════════════════════════
# Estrutura dinâmica de seções (ADR 0016): reconciliação de IDs entre turnos
# ═══════════════════════════════════════════════════════════════════════════


class TestSecoesDinamicas:
    def test_ids_estaveis_entre_turnos_ao_renomear_e_reordenar(self, monkeypatch):
        """CA: renomear/reordenar entre turnos preserva os IDs — o agente ecoa
        os ids do turno anterior e o sistema os mantém (o ⌖ sobrevive)."""
        # Turno 1: duas seções inéditas (sem id) — o sistema atribui.
        _stub_openrouter(
            monkeypatch,
            content=_resposta_ia([_secao("Objetivo", "A."), _secao("Abrangência", "B.")]),
        )
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(ELABORADOR, sb)

        body1 = _chat(client).json()
        secoes1 = body1["rascunho"]["secoes"]
        id_obj, id_abr = secoes1[0]["id"], secoes1[1]["id"]

        # Turno 2: o agente devolve invertido, com a primeira renomeada,
        # ecoando os ids; e acrescenta uma seção inédita (sem id).
        _stub_openrouter(
            monkeypatch,
            content=_resposta_ia(
                [
                    _secao("Abrangência", "B.", sid=id_abr),
                    _secao("Objetivo geral", "A revisado.", sid=id_obj),
                    _secao("Responsabilidades", "C."),
                ]
            ),
        )
        body2 = _chat(client, rascunho=body1["rascunho"]).json()
        secoes2 = body2["rascunho"]["secoes"]

        assert [s["id"] for s in secoes2[:2]] == [id_abr, id_obj], "ids preservados em reordenar/renomear"
        assert secoes2[1]["titulo"] == "Objetivo geral"
        # A seção inédita ganha id novo e distinto.
        novo_id = secoes2[2]["id"]
        assert novo_id and novo_id not in (id_obj, id_abr)

    def test_secao_removida_some_entre_turnos(self, monkeypatch):
        """CA: seção que o agente não devolve no turno seguinte some da lista."""
        rascunho = {
            "secoes": [
                {"id": "id-a", "titulo": "Objetivo", "conteudo": "A", "tipo": "texto"},
                {"id": "id-b", "titulo": "Abrangência", "conteudo": "B", "tipo": "texto"},
            ]
        }
        _stub_openrouter(monkeypatch, content=_resposta_ia([_secao("Objetivo", "A", sid="id-a")]))
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=rascunho))
        client = _client_para(ELABORADOR, sb)

        body = _chat(client, rascunho=rascunho).json()
        secoes = body["rascunho"]["secoes"]

        assert [s["id"] for s in secoes] == ["id-a"]
        assert sb.tables["pops_versoes"][0]["rascunho"]["secoes"][0]["id"] == "id-a"

    def test_sinalizacao_de_lacuna_no_reply_nao_trava(self, monkeypatch):
        """CA: o agente sinaliza a ausência de uma seção esperada por ONA/JCI no
        `reply`, mas o turno avança normalmente (não bloqueia)."""
        _stub_openrouter(
            monkeypatch,
            content=_resposta_ia(
                [_secao("Objetivo", "Padronizar.")],
                reply="Faltam Responsabilidades e Referências normativas, que um auditor ONA esperaria.",
            ),
        )
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(ELABORADOR, sb)

        res = _chat(client)

        assert res.status_code == 200
        body = res.json()
        assert "Responsabilidades" in body["reply"]
        # Não travou: a seção devolvida persistiu e o estado segue EM_ELABORACAO.
        assert body["rascunho"]["secoes"][0]["titulo"] == "Objetivo"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"

    def test_periodicidade_preservada_com_secoes(self, monkeypatch):
        """CA: a sugestão de Periodicidade segue na resposta junto da lista de
        seções (não se perde na mudança de shape)."""
        _stub_openrouter(
            monkeypatch,
            content=_resposta_ia([_secao("Objetivo", "X.")], periodicidade="6_meses"),
        )
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(ELABORADOR, sb)

        body = _chat(client).json()

        assert body["periodicidade_sugerida"] == "6_meses"
        assert body["rascunho"]["secoes"][0]["titulo"] == "Objetivo"
        assert sb.tables["pops_versoes"][0]["periodicidade_sugerida"] == "6_meses"


# ═══════════════════════════════════════════════════════════════════════════
# POST /pops/{pop_id}/elaboracao/fluxograma-svg — captura do SVG (ADR 0017)
# ═══════════════════════════════════════════════════════════════════════════


def _rascunho_com_fluxograma(svg: str | None = None) -> dict:
    flux = {
        "id": "id-flux",
        "titulo": "Fluxograma",
        "conteudo": "flowchart TD\n  A[Início] --> B[Fim]",
        "tipo": "fluxograma",
    }
    if svg is not None:
        flux["svg"] = svg
    return {
        "secoes": [
            {"id": "id-obj", "titulo": "Objetivo", "conteudo": "Padronizar.", "tipo": "texto"},
            flux,
        ]
    }


class TestCapturaSvgFluxograma:
    def test_svg_capturado_persiste_na_secao_de_fluxograma(self):
        """CA: o SVG renderizado no cliente é capturado e persistido com a
        Versão (no campo `svg` da seção de fluxograma)."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={
                "section_id": "id-flux",
                "svg": '<svg xmlns="http://www.w3.org/2000/svg"><text>diagrama</text></svg>',
            },
        )

        assert res.status_code == 200
        secoes = sb.tables["pops_versoes"][0]["rascunho"]["secoes"]
        flux = next(s for s in secoes if s["id"] == "id-flux")
        # O SVG persistido é o sanitizado (re-serializado); o conteúdo legítimo
        # sobrevive e é um <svg> bem-formado.
        assert flux["svg"].startswith("<svg")
        assert "diagrama" in flux["svg"]
        # A outra seção fica intacta.
        obj = next(s for s in secoes if s["id"] == "id-obj")
        assert obj["conteudo"] == "Padronizar." and "svg" not in obj

    def test_svg_substitui_o_anterior(self):
        """Re-render do mesmo fluxograma sobrescreve o SVG persistido."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma(svg="<svg>antigo</svg>")))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-flux", "svg": "<svg>novo</svg>"},
        )

        assert res.status_code == 200
        flux = next(s for s in sb.tables["pops_versoes"][0]["rascunho"]["secoes"] if s["id"] == "id-flux")
        assert flux["svg"] == "<svg>novo</svg>"

    def test_secao_inexistente_404(self):
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-nao-existe", "svg": "<svg/>"},
        )

        assert res.status_code == 404

    def test_secao_de_texto_nao_aceita_svg_404(self):
        """SVG só vale para a seção de fluxograma — apontar uma seção de texto
        é pedido inválido (não há diagrama a guardar)."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-obj", "svg": "<svg/>"},
        )

        assert res.status_code == 404

    def test_nao_elaborador_403(self):
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(INTRUSO, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-flux", "svg": "<svg/>"},
        )

        assert res.status_code == 403

    def test_estado_invalido_400(self):
        """Fora da elaboração (já em revisão) o rascunho não é mais editável."""
        sb = _sb(versao=_versao(estado="EM_REVISAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-flux", "svg": '<svg xmlns="http://www.w3.org/2000/svg"/>'},
        )

        assert res.status_code == 400

    def test_svg_persistido_e_sanitizado_nao_o_original(self):
        """Segurança (ADR 0017): o SVG vem do cliente e o PDF o embute cru. O
        endpoint persiste a VERSÃO SANITIZADA, elementos perigosos (que virariam
        leitura de arquivo local / SSRF no WeasyPrint) não chegam ao banco."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=_rascunho_com_fluxograma()))
        client = _client_para(ELABORADOR, sb)
        malicioso = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            '<image href="file:///app/.env" x="0" y="0" width="10" height="10"/>'
            '<script>fetch("http://169.254.169.254/")</script>'
            '<rect onload="x()" x="0" y="0" width="5" height="5"/>'
            "</svg>"
        )

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-flux", "svg": malicioso},
        )

        assert res.status_code == 200
        flux = next(s for s in sb.tables["pops_versoes"][0]["rascunho"]["secoes"] if s["id"] == "id-flux")
        svg = flux["svg"]
        # O vetor de ataque sumiu do que foi persistido.
        assert "file:///app/.env" not in svg
        assert "<image" not in svg
        assert "<script" not in svg
        assert "169.254.169.254" not in svg
        assert "onload" not in svg

    def test_svg_invalido_400_nada_persistido(self):
        """SVG que não parseia (ou cuja raiz não é <svg>) é rejeitado e o
        rascunho não é tocado."""
        rascunho = _rascunho_com_fluxograma(svg="<svg>ja-existia</svg>")
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho=rascunho))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/fluxograma-svg",
            json={"section_id": "id-flux", "svg": "<html>não é svg</html>"},
        )

        assert res.status_code == 400
        # Nada mudou: o svg anterior segue intacto.
        flux = next(s for s in sb.tables["pops_versoes"][0]["rascunho"]["secoes"] if s["id"] == "id-flux")
        assert flux["svg"] == "<svg>ja-existia</svg>"


# ═══════════════════════════════════════════════════════════════════════════
# GET /pops/{pop_id}/elaboracao — guardas
# ═══════════════════════════════════════════════════════════════════════════


class TestGetElaboracao:
    def test_get_nao_elaborador_403(self):
        client = _client_para(INTRUSO, _sb())
        res = client.get("/api/pops/pop-1/elaboracao")
        assert res.status_code == 403

    def test_get_pop_inexistente_404(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.get("/api/pops/pop-999/elaboracao")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /pops/{pop_id}/elaboracao/periodicidade — escolha final do Elaborador
# ═══════════════════════════════════════════════════════════════════════════


class TestPeriodicidade:
    def test_escolha_final_gravada_no_pop_e_auditada(self):
        """CA: a escolha final do Elaborador fica gravada (no POP, que carrega
        a Periodicidade de revisão oficial) com auditoria."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", periodicidade_sugerida="6_meses"))
        client = _client_para(ELABORADOR, sb)

        res = client.patch(
            "/api/pops/pop-1/elaboracao/periodicidade",
            json={"periodicidade_revisao": "6_meses"},
        )

        assert res.status_code == 200
        assert res.json()["periodicidade_revisao"] == "6_meses"
        assert sb.tables["pops"][0]["periodicidade_revisao"] == "6_meses"
        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_ESCOLHER_PERIODICIDADE" in acoes

    def test_escolha_nao_elaborador_403(self):
        client = _client_para(INTRUSO, _sb())
        res = client.patch(
            "/api/pops/pop-1/elaboracao/periodicidade",
            json={"periodicidade_revisao": "6_meses"},
        )
        assert res.status_code == 403

    def test_escolha_estado_invalido_400(self):
        client = _client_para(ELABORADOR, _sb(versao=_versao(estado="EM_REVISAO")))
        res = client.patch(
            "/api/pops/pop-1/elaboracao/periodicidade",
            json={"periodicidade_revisao": "6_meses"},
        )
        assert res.status_code == 400

    def test_escolha_valor_invalido_422(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.patch(
            "/api/pops/pop-1/elaboracao/periodicidade",
            json={"periodicidade_revisao": "5_anos"},
        )
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# POST /pops/{pop_id}/elaboracao/aprovar — EM_ELABORACAO → EM_REVISAO
# ═══════════════════════════════════════════════════════════════════════════


class TestAprovarVersaoFinal:
    def test_aprovar_move_para_em_revisao_audita_e_notifica_revisor(self, emails_enviados):
        """CA: "Aprovar versão final" move para EM_REVISAO, registra auditoria
        e dispara email ao Revisor com link e prazo."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "Pronto."}))
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_REVISAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_REVISAO"

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_APROVAR_VERSAO_FINAL" in acoes

        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p2@hsm.com"  # Revisor designado
        assert "HSM_CTI-001" in email["assunto"]
        assert "/pops" in email["html"]  # link de acesso
        assert "30" in email["html"]  # prazo de revisão (dias)

    def test_aprovar_sem_conteudo_400(self):
        """A_ELABORAR sem rascunho persistido: não há o que enviar à Revisão."""
        sb = _sb(versao=_versao(estado="A_ELABORAR", rascunho=None))
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 400
        assert sb.tables["pops_versoes"][0]["estado"] == "A_ELABORAR"

    def test_aprovar_rascunho_so_com_secoes_em_branco_400(self):
        """Esqueleto vazio (todas as seções string em branco) também é "sem
        conteúdo" — dict truthy não engana a guarda."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "", "abrangencia": "  "}))
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 400
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"

    def test_aprovar_estado_invalido_400(self):
        """CA: transição fora de estado válido → 400 (já em EM_REVISAO não
        re-aprova; o enum à frente também não)."""
        for estado in ("EM_REVISAO", "EM_VALIDACAO", "PUBLICADO"):
            sb = _sb(versao=_versao(estado=estado, rascunho={"objetivo": "x"}))
            client = _client_para(ELABORADOR, sb)
            res = client.post("/api/pops/pop-1/elaboracao/aprovar")
            assert res.status_code == 400, f"estado {estado} deveria dar 400"

    def test_aprovar_nao_elaborador_403(self, emails_enviados):
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "x"}))
        client = _client_para(INTRUSO, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 403
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"
        assert emails_enviados == []

    def test_aprovar_email_falho_nao_desfaz_transicao(self, monkeypatch):
        """Email é best-effort (padrão pops_email_service): falha de envio não
        desfaz a transição nem vira 500."""

        def _explode(*_a, **_kw):
            raise RuntimeError("SMTP fora do ar")

        monkeypatch.setattr(pops_email_service, "_enviar_email", _explode)
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "x"}))
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_REVISAO"
