"""Reconciliação com a ClickSign (issue #279, ADR 0030 decisão 4).

Job diário no scheduler varre as Reuniões em AGUARDANDO_ASSINATURA com
Envelope e consulta a ClickSign: documento fechado aplica o mesmo fluxo do
webhook de fechamento (Pendências restantes + registro de faltantes +
ASSINADA); documento cancelado abre o modo interno. Tudo idempotente. O botão
"Sincronizar" do card de Signatários reusa a mesma função com cooldown curto.

Padrão de teste dos jobs: chamar a função do job diretamente com a API
ClickSign SEMPRE mockada (o .env de teste carrega credenciais reais).
Harness de mock compartilhado com test_aceites_sign_incremental (issue #274).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_aceites_sign_incremental import (  # noqa: E402
    _sb,
    _SupabaseMock,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import clicksign_service, reconciliacao_service, storage  # noqa: E402

ENVELOPE_ID = "env-r1"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _bloquear_httpx(monkeypatch):
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


@pytest.fixture(autouse=True)
def _pdf_e_storage_mockados(monkeypatch):
    monkeypatch.setattr(clicksign_service, "get_signed_document", lambda _env: b"%PDF-signed")
    monkeypatch.setattr(storage, "upload_file", lambda *_a, **_kw: "http://storage/pdfs/ata_assinada.pdf")


@pytest.fixture(autouse=True)
def _reset_cooldown_e_limiter():
    from app.limiter import limiter

    reunioes_router._sync_recent.clear()
    limiter._storage.reset()
    yield
    reunioes_router._sync_recent.clear()
    limiter._storage.reset()


@pytest.fixture
def clicksign(monkeypatch):
    """ClickSign mockada por envelope: status do Envelope + signers.

    `status` mapeia envelope_id -> status oficial (running/closed/canceled).
    `consultas` registra os envelopes cujo status foi consultado.
    """

    class _Clicksign:
        def __init__(self):
            self.status: dict[str, str | None] = {}
            self.signers: dict[str, list[dict]] = {}
            self.consultas: list[str] = []

    cs = _Clicksign()

    def _get_status(envelope_id: str):
        cs.consultas.append(envelope_id)
        return cs.status.get(envelope_id)

    monkeypatch.setattr(clicksign_service, "get_envelope_status", _get_status)
    monkeypatch.setattr(clicksign_service, "list_signers", lambda env: cs.signers.get(env, []))
    return cs


def _signer(key: str, email: str, *, assinou: bool) -> dict:
    return {
        "signer_id": key,
        "nome": email.split("@")[0].title(),
        "email": email,
        "status": "signed" if assinou else "pending",
        "signed_at": "2026-08-10T09:00:00-03:00" if assinou else None,
    }


def _signers_padrao() -> list[dict]:
    return [
        _signer("sk-fac", "fabio@hsm.com", assinou=False),
        _signer("sk-ana", "ana@hsm.com", assinou=True),
        _signer("sk-bruno", "bruno@hsm.com", assinou=False),
    ]


def _reuniao(sb: _SupabaseMock, id_reuniao: str = "R1") -> dict:
    return next(r for r in sb.tables["reunioes"] if r["id_reuniao"] == id_reuniao)


def _pendencias(sb: _SupabaseMock) -> list[dict]:
    return sb.tables["pendencias"]


# ═══════════════════════════════════════════════════════════════════════════
# CA: documento fechado na ClickSign aplica o mesmo desfecho do webhook
# ═══════════════════════════════════════════════════════════════════════════


class TestJobDocumentoFechado:
    def test_documento_fechado_finaliza_como_o_webhook(self, clicksign):
        """Webhook de fechamento se perdeu: o job consulta a ClickSign, vê o
        Envelope closed e aplica o fluxo do webhook (Pendências + ASSINADA)."""
        clicksign.status[ENVELOPE_ID] = "closed"
        clicksign.signers[ENVELOPE_ID] = _signers_padrao()
        sb = _sb()

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["finalizada"] == 1
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        assert _reuniao(sb)["data_assinatura"]
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 1, 2, 3, 4]

    def test_fechado_registra_faltantes_e_aceites(self, clicksign):
        """Mesmo registro do webhook: contagem persistida para o selo e aceite
        `clicksign` para quem assinou (faltante fica sem aceite)."""
        clicksign.status[ENVELOPE_ID] = "closed"
        clicksign.signers[ENVELOPE_ID] = _signers_padrao()
        sb = _sb()

        reconciliacao_service.reconciliar_pendentes(sb)

        assert _reuniao(sb)["signatarios_total"] == 3
        assert _reuniao(sb)["signatarios_assinaram"] == 1
        aceites = sb.tables["reuniao_aceites"]
        assert {a.get("signer_key") for a in aceites} == {"sk-ana"}
        assert aceites[0]["origem"] == "clicksign"

    def test_envelope_ainda_running_nada_muda(self, clicksign):
        clicksign.status[ENVELOPE_ID] = "running"
        sb = _sb()

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["sem_mudanca"] == 1
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _pendencias(sb) == []


# ═══════════════════════════════════════════════════════════════════════════
# CA: documento cancelado abre o modo interno
# ═══════════════════════════════════════════════════════════════════════════


class TestJobDocumentoCancelado:
    def test_cancelado_abre_modo_interno(self, clicksign):
        clicksign.status[ENVELOPE_ID] = "canceled"
        sb = _sb()

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["modo_interno"] == 1
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _reuniao(sb)["modo_interno_desde"]

    def test_cancelado_mantem_pendencias_ja_nascidas(self, clicksign):
        clicksign.status[ENVELOPE_ID] = "canceled"
        sb = _sb()
        sb.tables["pendencias"].append({"id_acao": "A001", "id_reuniao": "R1", "status": "PENDENTE", "quadro_pos": 0})

        reconciliacao_service.reconciliar_pendentes(sb)

        assert len(_pendencias(sb)) == 1
        assert _reuniao(sb)["modo_interno_desde"]


# ═══════════════════════════════════════════════════════════════════════════
# CA: rodar o job duas vezes não duplica Pendência nem muda estado resolvido
# ═══════════════════════════════════════════════════════════════════════════


class TestJobIdempotente:
    def test_rodar_duas_vezes_nao_duplica_nem_reprocessa(self, clicksign):
        clicksign.status[ENVELOPE_ID] = "closed"
        clicksign.signers[ENVELOPE_ID] = _signers_padrao()
        sb = _sb()

        reconciliacao_service.reconciliar_pendentes(sb)
        pendencias_antes = len(_pendencias(sb))
        aceites_antes = len(sb.tables["reuniao_aceites"])
        data_antes = _reuniao(sb)["data_assinatura"]

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["finalizada"] == 0
        assert len(_pendencias(sb)) == pendencias_antes
        assert len(sb.tables["reuniao_aceites"]) == aceites_antes
        assert _reuniao(sb)["data_assinatura"] == data_antes

    def test_modo_interno_nao_reabre_na_segunda_rodada(self, clicksign):
        clicksign.status[ENVELOPE_ID] = "canceled"
        sb = _sb()

        reconciliacao_service.reconciliar_pendentes(sb)
        desde = _reuniao(sb)["modo_interno_desde"]

        reconciliacao_service.reconciliar_pendentes(sb)

        assert _reuniao(sb)["modo_interno_desde"] == desde


# ═══════════════════════════════════════════════════════════════════════════
# Varredura: só AGUARDANDO_ASSINATURA com Envelope e fora do modo interno
# ═══════════════════════════════════════════════════════════════════════════


class TestJobVarredura:
    def test_varre_somente_aguardando_assinatura_com_envelope(self, clicksign):
        clicksign.status["env-r1"] = "running"
        sb = _sb()
        sb.tables["reunioes"].extend(
            [
                # Já resolvida: fora da varredura
                {
                    "id_reuniao": "R2",
                    "status_ata": "ASSINADA",
                    "envelope_key_clicksign": "doc-r2",
                    "envelope_id_clicksign": "env-r2",
                },
                # Sem Envelope: nada a consultar
                {"id_reuniao": "R3", "status_ata": "AGUARDANDO_ASSINATURA", "envelope_key_clicksign": None},
                # Modo interno já aberto: Envelope morto, fora da varredura
                {
                    "id_reuniao": "R4",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-r4",
                    "envelope_id_clicksign": "env-r4",
                    "modo_interno_desde": "2026-08-01T10:00:00+00:00",
                },
            ]
        )

        reconciliacao_service.reconciliar_pendentes(sb)

        assert clicksign.consultas == ["env-r1"]

    def test_clicksign_indisponivel_nao_muda_nada(self, clicksign):
        # status None = consulta falhou (get_envelope_status devolve None)
        sb = _sb()

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["indisponivel"] == 1
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _pendencias(sb) == []

    def test_falha_numa_reuniao_nao_para_as_outras(self, clicksign, monkeypatch):
        clicksign.status["env-r2"] = "canceled"
        sb = _sb()
        sb.tables["reunioes"].append(
            {
                "id_reuniao": "R2",
                "status_ata": "AGUARDANDO_ASSINATURA",
                "envelope_key_clicksign": "doc-r2",
                "envelope_id_clicksign": "env-r2",
            }
        )

        original = clicksign_service.get_envelope_status

        def _explode_no_r1(envelope_id: str):
            if envelope_id == "env-r1":
                raise RuntimeError("boom")
            return original(envelope_id)

        monkeypatch.setattr(clicksign_service, "get_envelope_status", _explode_no_r1)

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["erro"] == 1
        assert contadores["modo_interno"] == 1
        assert _reuniao(sb, "R2")["modo_interno_desde"]

    def test_recupera_envelope_id_faltante_e_persiste(self, clicksign, monkeypatch):
        """Ata pré-039 sem envelope_id: o job recupera pelo nome determinístico
        (self-heal) e segue a reconciliação normalmente."""
        clicksign.status[ENVELOPE_ID] = "closed"
        clicksign.signers[ENVELOPE_ID] = _signers_padrao()
        monkeypatch.setattr(clicksign_service, "find_envelope_id", lambda _nome, _doc: ENVELOPE_ID)
        sb = _sb(envelope_id_clicksign=None)

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["finalizada"] == 1
        assert _reuniao(sb)["envelope_id_clicksign"] == ENVELOPE_ID
        assert _reuniao(sb)["status_ata"] == "ASSINADA"

    def test_envelope_id_irrecuperavel_conta_indisponivel(self, clicksign, monkeypatch):
        monkeypatch.setattr(clicksign_service, "find_envelope_id", lambda _nome, _doc: None)
        sb = _sb(envelope_id_clicksign=None)

        contadores = reconciliacao_service.reconciliar_pendentes(sb)

        assert contadores["indisponivel"] == 1
        assert clicksign.consultas == []
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"


# ═══════════════════════════════════════════════════════════════════════════
# CA: job diário registrado no scheduler
# ═══════════════════════════════════════════════════════════════════════════


class TestJobNoScheduler:
    def test_job_diario_registrado(self):
        from app.cron import scheduler as cron

        cron.start_scheduler()
        try:
            job = cron.scheduler.get_job("reconciliar_clicksign")
            assert job is not None
        finally:
            cron.stop_scheduler()


# ═══════════════════════════════════════════════════════════════════════════
# CA: botão "Sincronizar" reusa a mesma função, com cooldown curto
# ═══════════════════════════════════════════════════════════════════════════


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


@pytest.fixture
def make_client(monkeypatch):
    def _factory(
        supabase: _SupabaseMock,
        *,
        is_secretaria_override: bool = False,
        allowed_ids: set | None = None,
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
            return {"id": "P_FAC", "access_profile": "regular"}

        async def _fake_allowed(*_a, **_kw):
            return allowed_ids  # None = sem restrição

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        return TestClient(app)

    return _factory


class TestEndpointSincronizar:
    def test_sincronizar_finaliza_documento_fechado(self, clicksign, make_client):
        clicksign.status[ENVELOPE_ID] = "closed"
        clicksign.signers[ENVELOPE_ID] = _signers_padrao()
        sb = _sb()

        res = make_client(sb).post("/api/reunioes/R1/signatarios/sincronizar")

        assert res.status_code == 200
        assert res.json()["desfecho"] == "finalizada"
        assert _reuniao(sb)["status_ata"] == "ASSINADA"

    def test_sincronizar_cancelado_abre_modo_interno(self, clicksign, make_client):
        clicksign.status[ENVELOPE_ID] = "canceled"
        sb = _sb()

        res = make_client(sb).post("/api/reunioes/R1/signatarios/sincronizar")

        assert res.status_code == 200
        assert res.json()["desfecho"] == "modo_interno"
        assert _reuniao(sb)["modo_interno_desde"]

    def test_cooldown_curto_devolve_429(self, clicksign, make_client):
        clicksign.status[ENVELOPE_ID] = "running"
        sb = _sb()
        client = make_client(sb)

        assert client.post("/api/reunioes/R1/signatarios/sincronizar").status_code == 200
        res = client.post("/api/reunioes/R1/signatarios/sincronizar")

        assert res.status_code == 429
        assert clicksign.consultas == [ENVELOPE_ID]  # a segunda chamada nem consulta

    def test_reuniao_ja_assinada_sem_mudanca(self, clicksign, make_client):
        sb = _sb(status_ata="ASSINADA")

        res = make_client(sb).post("/api/reunioes/R1/signatarios/sincronizar")

        assert res.status_code == 200
        assert res.json()["desfecho"] == "sem_mudanca"
        assert clicksign.consultas == []

    def test_clicksign_indisponivel_devolve_503(self, clicksign, make_client):
        sb = _sb()

        res = make_client(sb).post("/api/reunioes/R1/signatarios/sincronizar")

        assert res.status_code == 503

    def test_secretaria_403(self, clicksign, make_client):
        sb = _sb()
        res = make_client(sb, is_secretaria_override=True).post("/api/reunioes/R1/signatarios/sincronizar")
        assert res.status_code == 403

    def test_reuniao_fora_da_visibilidade_404(self, clicksign, make_client):
        sb = _sb()
        res = make_client(sb, allowed_ids={"OUTRA"}).post("/api/reunioes/R1/signatarios/sincronizar")
        assert res.status_code == 404

    def test_sem_envelope_400(self, clicksign, make_client):
        sb = _sb(envelope_key_clicksign=None)
        res = make_client(sb).post("/api/reunioes/R1/signatarios/sincronizar")
        assert res.status_code == 400
