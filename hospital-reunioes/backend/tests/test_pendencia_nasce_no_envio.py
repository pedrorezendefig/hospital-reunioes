"""A Pendência nasce no envio da Ata para assinatura (ADR 0098, decisões 1 a 3; issue #1867).

No clique de enviar, a Reunião vai para AGUARDANDO_ASSINATURA e nascem todas
as Pendências do quadro. A ClickSign roda em seguida; se falhar, fica o
Reenviar, sem voltar o estado e sem criar dois Envelopes. Depois do envio,
reprocessar e corrigir a Ata ficam bloqueados. O Aceite interno é só ciência.
A reconciliação das 5h30 cria o que falta.

O evento de nascimento no Histórico vem do banco (trigger da migration 171),
provado em `test_pendencia_historico_banco.py`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _Not:
    def __init__(self, query: _TableQuery):
        self._q = query

    def is_(self, col, _value):
        self._q._filtros.append(lambda r, c=col: r.get(c) is not None)
        return self._q


class _TableQuery:
    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op = "select"
        self._payload: Any = None
        self._filtros: list = []
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
        self._filtros.append(lambda r, c=col, v=value: r.get(c) == v)
        return self

    def neq(self, col, value):
        self._filtros.append(lambda r, c=col, v=value: r.get(c) != v)
        return self

    def in_(self, col, values):
        vals = list(values)
        self._filtros.append(lambda r, c=col: r.get(c) in vals)
        return self

    def is_(self, col, _value):
        self._filtros.append(lambda r, c=col: r.get(c) is None)
        return self

    @property
    def not_(self):
        return _Not(self)

    def ilike(self, col, pattern):
        needle = pattern.strip("%").lower()
        self._filtros.append(lambda r, c=col: needle in str(r.get(c) or "").lower())
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for it in items:
                self._rows.append(dict(it))
            return _Result(data=[dict(it) for it in items])
        matched = [r for r in self._rows if all(f(r) for f in self._filtros)]
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
                if "updated_at" in r:
                    # O trigger da migration 002 grava now() em todo UPDATE.
                    r["updated_at"] = datetime.now(UTC).isoformat()
        if self._op == "delete":
            for r in list(matched):
                self._rows.remove(r)
        return _Result(data=[dict(r) for r in matched])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    # A linha de Processo entra na lista do setor no mesmo envio (issue #1875).
    definicoes_processo: list = field(default_factory=list)
    setores: list = field(default_factory=list)
    reuniao_aceites: list = field(default_factory=list)
    reuniao_aceite_tokens: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)
    colegiados: list = field(default_factory=list)
    # A Rotina nasce no mesmo envio (issue #1874).
    rotinas: list = field(default_factory=list)
    rotina_verificacoes: list = field(default_factory=list)

    def table(self, name: str):
        rows = getattr(self, name, None)
        if rows is None:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(rows)


def _acao(acao: str, responsavel: str, prazo: str | None = None) -> dict:
    return {"acao": acao, "responsavel": responsavel, "prazo": prazo}


def _sb(status: str = "AGUARDANDO_VALIDACAO", **reuniao) -> _SupabaseMock:
    return _SupabaseMock(
        participantes=[
            {"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor", "email": "pedro@hsm.com", "ativo": True},
            {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora", "email": "ana@hsm.com", "ativo": True},
        ],
        reuniao_participantes=[
            {"id_reuniao": "R1", "participante_id": "P1", "sequence_assinatura": 1},
            {"id_reuniao": "R1", "participante_id": "P2", "sequence_assinatura": 2},
        ],
        reunioes=[
            {
                "id_reuniao": "R1",
                "status_ata": status,
                "tipo": "Gerencial",
                "objetivo": "Acompanhamento",
                "data": "2026-11-10",
                "facilitador_id": "P1",
                "envelope_key_clicksign": None,
                "envelope_id_clicksign": None,
                "falha_envio_assinatura": None,
                "modo_interno_desde": None,
                "colegiado_id": None,
                "deleted_at": None,
                "json_ata": {
                    "quadro_atribuicoes": [
                        _acao("Comprar insumos", "Pedro Rezende", "2026-12-10"),
                        _acao("Revisar protocolo", "Ana Lima", "10/12/2026"),
                        _acao("Ligar para o fornecedor", "Fulano de Fora"),
                    ]
                },
                **reuniao,
            }
        ],
    )


CURRENT_USER = {"id": "auth-uid-1", "email": "pedro@hsm.com"}
FACILITADOR = {"id": "P1", "email": "pedro@hsm.com", "access_profile": "regular"}


@pytest.fixture
def make_client(monkeypatch):
    def _factory(supabase: _SupabaseMock) -> TestClient:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        from app.limiter import limiter

        limiter._storage.reset()
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(reunioes_router.router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return dict(FACILITADOR)

        async def _fake_allowed(*_a, **_kw):
            return None

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: False)
        return TestClient(app)

    return _factory


def _clicksign(monkeypatch, *, cria_envelope: bool = True) -> dict:
    """A ClickSign de mentira: conta Envelopes criados e anota o que tinha no
    banco quando o Envelope foi criado. Sem `cria_envelope`, a criação falha."""
    from app.services import clicksign_service, pdf_generator, storage

    estado: dict = {"envelopes": 0, "pdf_do_quadro": None}

    def _gerar_pdf(_reuniao, json_ata):
        estado["pdf_do_quadro"] = [a["acao"] for a in json_ata["quadro_atribuicoes"]]
        return b"PDF_DO_QUADRO_FINAL"

    def _criar(_nome):
        if not cria_envelope:
            return None
        estado["envelopes"] += 1
        return f"env-{estado['envelopes']}"

    monkeypatch.setattr(pdf_generator, "gerar_pdf_ata", _gerar_pdf)
    monkeypatch.setattr(storage, "upload_file", lambda *_a, **_kw: "https://x/ata_preliminar.pdf")
    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"PDF_ANTIGO")
    monkeypatch.setattr(clicksign_service, "create_envelope", _criar)
    monkeypatch.setattr(clicksign_service, "add_document", lambda *_a, **_kw: "doc-id")
    monkeypatch.setattr(clicksign_service, "add_signer", lambda *_a, **_kw: "signer-id")
    monkeypatch.setattr(clicksign_service, "create_qualification_requirement", lambda *_a, **_kw: "q")
    monkeypatch.setattr(clicksign_service, "create_auth_requirement", lambda *_a, **_kw: "a")
    monkeypatch.setattr(clicksign_service, "activate_envelope", lambda _e: True)
    monkeypatch.setattr(clicksign_service, "notify_signers", lambda _e: True)
    return estado


# ─── 1. Enviar cria todas as Pendências no mesmo ato ───────────────────────────


def test_enviar_para_assinatura_cria_todas_as_pendencias_no_mesmo_ato(make_client, monkeypatch):
    """Sem esperar ninguém assinar: as três ações do quadro viram Pendência no
    clique, inclusive a de quem está fora do Envelope, e a Reunião já está em
    AGUARDANDO_ASSINATURA quando a ClickSign começa."""
    from app.services import clicksign_service

    sb = _sb()
    visto_pela_clicksign: dict = {}

    def _fluxo(supabase, id_reuniao, _reuniao):
        visto_pela_clicksign["status"] = supabase.reunioes[0]["status_ata"]
        visto_pela_clicksign["pendencias"] = len(supabase.pendencias)

    monkeypatch.setattr(clicksign_service, "start_signature_flow", _fluxo)

    r = make_client(sb).post("/api/reunioes/R1/aprovar")

    assert r.status_code == 200, r.text
    assert r.json()["total_pendencias"] == 3
    assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert sorted(p["quadro_pos"] for p in sb.pendencias) == [0, 1, 2]
    assert {p["descricao_acao"] for p in sb.pendencias} == {
        "Comprar insumos",
        "Revisar protocolo",
        "Ligar para o fornecedor",
    }
    assert visto_pela_clicksign == {"status": "AGUARDANDO_ASSINATURA", "pendencias": 3}


# ─── 2. Falha da ClickSign e o Reenviar ────────────────────────────────────────


def test_falha_da_clicksign_deixa_aguardando_assinatura_com_o_reenviar(make_client, monkeypatch):
    estado = _clicksign(monkeypatch, cria_envelope=False)
    sb = _sb()

    r = make_client(sb).post("/api/reunioes/R1/aprovar")

    assert r.status_code == 200, r.text
    reuniao = sb.reunioes[0]
    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["falha_envio_assinatura"]["passo"] == "criar_envelope"
    assert reuniao["envelope_key_clicksign"] is None
    assert len(sb.pendencias) == 3
    assert estado["envelopes"] == 0


def test_reenviar_nao_duplica_pendencia_nem_envelope(make_client, monkeypatch):
    _clicksign(monkeypatch, cria_envelope=False)
    sb = _sb()
    client = make_client(sb)
    assert client.post("/api/reunioes/R1/aprovar").status_code == 200

    estado = _clicksign(monkeypatch, cria_envelope=True)
    reenvio = client.post("/api/reunioes/R1/aprovar")
    de_novo = client.post("/api/reunioes/R1/aprovar")

    assert reenvio.status_code == 200, reenvio.text
    assert reenvio.json()["total_pendencias"] == 0
    assert de_novo.status_code in (400, 409)
    assert len(sb.pendencias) == 3
    assert estado["envelopes"] == 1
    reuniao = sb.reunioes[0]
    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["envelope_id_clicksign"] == "env-1"
    assert reuniao["falha_envio_assinatura"] is None


def test_duplo_clique_no_enviar_dispara_a_clicksign_uma_vez(make_client, monkeypatch):
    """O segundo clique chega com a ClickSign ainda rodando (sem Envelope e
    sem falha): é recusado, e só um fluxo começa."""
    from app.services import clicksign_service

    fluxos: list[str] = []
    monkeypatch.setattr(clicksign_service, "start_signature_flow", lambda _sb, rid, _r: fluxos.append(rid))
    sb = _sb()
    client = make_client(sb)

    primeiro = client.post("/api/reunioes/R1/aprovar")
    segundo = client.post("/api/reunioes/R1/aprovar")

    assert primeiro.status_code == 200
    assert segundo.status_code == 409
    assert fluxos == ["R1"]
    assert len(sb.pendencias) == 3


def _envio_parado_ha(minutos: int) -> _SupabaseMock:
    """O processo morreu no meio da ClickSign (deploy ou restart) ou a falha
    não foi gravada: AGUARDANDO_ASSINATURA, sem Envelope e sem falha."""
    desde = (datetime.now(UTC) - timedelta(minutes=minutos)).isoformat()
    return _sb("AGUARDANDO_ASSINATURA", updated_at=desde)


@pytest.mark.parametrize(("minutos", "mostra"), [(31, True), (5, False)])
def test_envio_que_parou_no_meio_mostra_o_reenviar_na_tela(make_client, minutos, mostra):
    """Passados 30 minutos sem Envelope e sem falha, a tela recebe a falha de
    envio que o processo não chegou a gravar e mostra o Reenviar; com o envio
    ainda recente, nada muda (a ClickSign pode estar rodando)."""
    sb = _envio_parado_ha(minutos)

    r = make_client(sb).get("/api/reunioes/R1")

    assert r.status_code == 200, r.text
    falha = r.json()["falha_envio_assinatura"]
    assert (falha or {}).get("passo") == ("finalizar" if mostra else None)
    assert sb.reunioes[0]["falha_envio_assinatura"] is None


def test_reenviar_do_envio_que_parou_no_meio_dispara_a_clicksign_uma_vez(make_client, monkeypatch):
    from app.services import clicksign_service

    fluxos: list[str] = []
    monkeypatch.setattr(clicksign_service, "start_signature_flow", lambda _sb, rid, _r: fluxos.append(rid))
    sb = _envio_parado_ha(31)
    client = make_client(sb)

    reenvio = client.post("/api/reunioes/R1/aprovar")
    de_novo = client.post("/api/reunioes/R1/aprovar")

    assert reenvio.status_code == 200, reenvio.text
    assert de_novo.status_code == 409
    assert fluxos == ["R1"]
    assert len(sb.pendencias) == 3


def test_dois_reenviar_simultaneos_do_envio_parado_disparam_a_clicksign_uma_vez(make_client, monkeypatch):
    """Os dois cliques leem a linha antes de qualquer um gravar: o claim do
    segundo acha o `updated_at` já mudado pelo primeiro e não cria Envelope."""
    from app.services import clicksign_service

    fluxos: list[str] = []
    monkeypatch.setattr(clicksign_service, "start_signature_flow", lambda _sb, rid, _r: fluxos.append(rid))
    sb = _envio_parado_ha(31)
    original = reunioes_router._envio_interrompido

    def _outro_clique_grava_no_meio(reuniao):
        parado = original(reuniao)
        sb.reunioes[0]["updated_at"] = datetime.now(UTC).isoformat()
        return parado

    monkeypatch.setattr(reunioes_router, "_envio_interrompido", _outro_clique_grava_no_meio)

    r = make_client(sb).post("/api/reunioes/R1/aprovar")

    assert r.status_code == 409
    assert fluxos == []


def test_envio_recente_sem_falha_nao_aceita_o_reenviar(make_client, monkeypatch):
    from app.services import clicksign_service

    fluxos: list[str] = []
    monkeypatch.setattr(clicksign_service, "start_signature_flow", lambda _sb, rid, _r: fluxos.append(rid))

    r = make_client(_envio_parado_ha(5)).post("/api/reunioes/R1/aprovar")

    assert r.status_code == 409
    assert fluxos == []


def test_o_pdf_do_envelope_e_gerado_de_novo_a_partir_do_quadro_final(make_client, monkeypatch):
    from app.services import clicksign_service

    estado = _clicksign(monkeypatch)
    documentos: list[bytes] = []
    monkeypatch.setattr(clicksign_service, "add_document", lambda _env, pdf, _nome: documentos.append(pdf) or "doc")
    sb = _sb()

    assert make_client(sb).post("/api/reunioes/R1/aprovar").status_code == 200

    assert documentos == [b"PDF_DO_QUADRO_FINAL"]
    assert estado["pdf_do_quadro"] == ["Comprar insumos", "Revisar protocolo", "Ligar para o fornecedor"]


# ─── 3. Depois do envio, a Ata não se refaz nem se corrige ─────────────────────


@pytest.mark.parametrize("modo_interno_desde", [None, "2026-11-12T10:00:00+00:00"])
def test_reprocessar_responde_erro_depois_do_envio(make_client, monkeypatch, modo_interno_desde):
    from app.services import storage

    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"transcricao")
    sb = _sb("AGUARDANDO_ASSINATURA", modo_interno_desde=modo_interno_desde)

    r = make_client(sb).post("/api/reunioes/R1/reprocessar")

    assert r.status_code in (400, 409)
    assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"


def test_corrigir_responde_erro_depois_do_envio(make_client):
    sb = _sb("AGUARDANDO_ASSINATURA")

    r = make_client(sb).post("/api/reunioes/R1/corrigir", json={"texto": "Troque o prazo da compra"})

    assert r.status_code == 400
    assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"


@pytest.mark.parametrize("modo_interno_desde", [None, "2026-11-12T10:00:00+00:00"])
def test_editar_o_quadro_responde_erro_depois_do_envio(make_client, modo_interno_desde):
    """Nem com o Envelope morto (modo interno) o quadro muda: as ações já são
    Pendências desde o envio."""
    sb = _sb("AGUARDANDO_ASSINATURA", modo_interno_desde=modo_interno_desde)

    r = make_client(sb).patch("/api/reunioes/R1/quadro-atribuicoes/2", json={"responsavel": "Outra Pessoa"})

    assert r.status_code == 400
    assert sb.reunioes[0]["json_ata"]["quadro_atribuicoes"][2]["responsavel"] == "Fulano de Fora"


# ─── 6. A reconciliação das 5h30 cria o que falta ─────────────────────────────


@pytest.mark.parametrize(
    "reuniao",
    [
        {"envelope_key_clicksign": "doc", "envelope_id_clicksign": "env"},
        {"envelope_key_clicksign": None, "falha_envio_assinatura": {"passo": "criar_envelope"}},
        {"envelope_key_clicksign": "doc", "envelope_id_clicksign": "env", "modo_interno_desde": "2026-11-12T10:00:00"},
    ],
    ids=["envelope-rodando", "clicksign-falhou", "modo-interno"],
)
def test_reconciliacao_cria_as_pendencias_da_ata_em_assinatura_e_nao_duplica(monkeypatch, reuniao):
    """A carga das Atas que já estavam em assinatura antes da mudança, e a
    proteção contra o envio que falhou no meio (ADR 0098, decisão 3)."""
    from app.services import clicksign_service, reconciliacao_service, reuniao_email_service

    monkeypatch.setattr(clicksign_service, "get_envelope_status", lambda _env: "running")
    # No modo interno a reconciliação também refaz a coleta de Aceites internos.
    monkeypatch.setattr(reuniao_email_service, "_enviar_email", lambda *_a, **_kw: True)
    sb = _sb("AGUARDANDO_ASSINATURA", **reuniao)

    reconciliacao_service.reconciliar_pendentes(sb)
    assert sorted(p["quadro_pos"] for p in sb.pendencias) == [0, 1, 2]

    reconciliacao_service.reconciliar_pendentes(sb)
    assert sorted(p["quadro_pos"] for p in sb.pendencias) == [0, 1, 2]
    assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"


def test_o_texto_de_reunioes_no_kit_diz_que_a_pendencia_nasce_no_envio():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "reunioes.md").read_text(encoding="utf-8")
    assert "As pendências nascem todas no momento do envio" in texto
    assert "a assinatura vale como ciência da ata" in texto
    assert "aparece o botão de reenviar" in texto
    assert "não cria pendência" in texto
    assert "reprocessar e corrigir a ata ficam bloqueados" in texto
    # O comportamento antigo saiu do texto.
    assert "As pendências vão nascendo conforme as pessoas assinam" not in texto
    assert "faz nascer as pendências dele" not in texto
    assert "a pendência de cada pessoa nasce quando ela assina" not in texto


def test_reconciliacao_nao_toca_ata_fora_de_assinatura(monkeypatch):
    from app.services import reconciliacao_service

    sb = _sb("AGUARDANDO_VALIDACAO")

    reconciliacao_service.reconciliar_pendentes(sb)

    assert sb.pendencias == []
