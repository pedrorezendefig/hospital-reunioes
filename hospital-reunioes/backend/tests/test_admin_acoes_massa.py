"""Testes do router /admin/bulk (Fase 02 — versao background).

Cobre:
- 403 quando nao super admin (via require_super_admin).
- POST bulk retorna 202 com job_id e cria linha em bulk_jobs (status=pending).
- Execucao do BackgroundTask marca job como completed, preenche sucessos/falhas.
- GET /admin/bulk/jobs/{id} retorna o status.
- audit_log recebe linhas _STARTED e _COMPLETED.
- BULK_REENVIAR_CLICKSIGN, BULK_REPROCESSAR_IA, BULK_REENVIAR_EMAIL.

Mocks:
- ClickSign: monkeypatch `clicksign_service.notify_signers/start_signature_flow`.
- IA pipeline: monkeypatch `orchestrator.run_pipeline` e `storage.download_file`.
- Email: monkeypatch `_enviar_email` interno do email_service.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import require_super_admin  # noqa: E402
from app.models.admin_schemas import (  # noqa: E402
    BulkEmailRequest,
    BulkReuniaoRequest,
)
from app.routers.admin import acoes_massa as bulk_router  # noqa: E402

# ─── Mocks ───────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int | None = None


class _ReunioesQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}
        self._select: str | None = None

    def select(self, fields, **_kw):
        self._select = fields
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        filtered = self._rows
        for col, value in self._filters.items():
            filtered = [r for r in filtered if r.get(col) == value]
        return _Result(data=filtered)


class _ParticipantesIn:
    def __init__(self, rows):
        self._rows = rows
        self._in_col: str | None = None
        self._in_values: list = []

    def select(self, *_a, **_kw):
        return self

    def in_(self, col, values):
        self._in_col = col
        self._in_values = list(values)
        return self

    def execute(self):
        filtered = [r for r in self._rows if r.get(self._in_col) in self._in_values]
        return _Result(data=filtered)


class _AuditInsert:
    def __init__(self, sink):
        self._sink = sink
        self._pending = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending is not None:
            self._sink.append(self._pending)
        return _Result(data=[self._pending] if self._pending else [])


class _ParticipantesAuth:
    def __init__(self, rows):
        self._rows = rows
        self._f: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._f[col] = value
        return self

    def execute(self):
        filtered = self._rows
        for col, value in self._f.items():
            filtered = [r for r in filtered if r.get(col) == value]
        return _Result(data=filtered)

    def update(self, *_a, **_kw):
        return self


class _BulkJobsQuery:
    """Mock da tabela bulk_jobs. Suporta insert/update/select/eq/order/range."""

    def __init__(self, store: dict[str, dict]):
        self._store = store
        self._op: str | None = None
        self._payload: Any = None
        self._filters: dict = {}
        self._order: tuple[str, bool] | None = None
        self._range: tuple[int, int] | None = None
        self._count_mode: str | None = None

    def insert(self, row):
        self._op = "insert"
        self._payload = dict(row)
        return self

    def update(self, row):
        self._op = "update"
        self._payload = dict(row)
        return self

    def select(self, *_a, **kw):
        self._op = self._op or "select"
        self._count_mode = kw.get("count")
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self._order = (col, bool(desc))
        return self

    def range(self, lo, hi):
        self._range = (lo, hi)
        return self

    def execute(self):
        if self._op == "insert":
            new_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            row = dict(self._payload)
            row.setdefault("id", new_id)
            row.setdefault("created_at", now)
            row.setdefault("updated_at", now)
            row.setdefault("sucessos", 0)
            row.setdefault("falhas", [])
            row.setdefault("metadata", {})
            row.setdefault("target_ids", [])
            row.setdefault("total", len(row.get("target_ids") or []))
            row.setdefault("started_at", None)
            row.setdefault("finished_at", None)
            row.setdefault("reason", None)
            self._store[row["id"]] = row
            return _Result(data=[dict(row)])
        if self._op == "update":
            ids = [rid for rid, r in self._store.items() if all(r.get(c) == v for c, v in self._filters.items())]
            for rid in ids:
                self._store[rid].update(self._payload)
            return _Result(data=[dict(self._store[rid]) for rid in ids])
        # select
        rows = list(self._store.values())
        for c, v in self._filters.items():
            rows = [r for r in rows if r.get(c) == v]
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        total = len(rows)
        if self._range is not None:
            lo, hi = self._range
            rows = rows[lo : hi + 1]
        return _Result(data=[dict(r) for r in rows], count=total)


@dataclass
class _SupabaseMock:
    reunioes: list = field(default_factory=list)
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    participantes_auth: list = field(default_factory=list)
    bulk_jobs: dict = field(default_factory=dict)

    def table(self, name):
        if name == "reunioes":
            return _ReunioesQuery(self.reunioes)
        if name == "participantes":
            return _ParticipantesIn(self.participantes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        if name == "bulk_jobs":
            return _BulkJobsQuery(self.bulk_jobs)
        raise AssertionError(f"Tabela inesperada: {name}")


class _Request:
    def __init__(self, ip: str = "10.0.0.1"):
        self.client = type("C", (), {"host": ip})()
        self.headers: dict[str, Any] = {}


_ACTOR = {"id": "P01", "email": "admin@ex.com", "nome_completo": "Super"}


# ─── Testes: autorizacao ────────────────────────────────────────────────────


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_403_quando_sem_flag(self):
        @dataclass
        class _Sb:
            def table(self, name):
                assert name == "participantes"
                return _ParticipantesAuth(
                    [
                        {
                            "id": "P10",
                            "auth_user_id": "auth-10",
                            "email": "x@y",
                            "role": "diretor",
                            "is_super_admin": False,
                        }
                    ]
                )

        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-10", "email": "x@y", "metadata": {}},
                supabase=_Sb(),
            )
        assert exc.value.status_code == 403


# ─── Testes: reenviar-clicksign ──────────────────────────────────────────────


class TestBulkReenviarClicksign:
    @pytest.mark.asyncio
    async def test_retorna_202_com_job_id_e_cria_pending(self, monkeypatch):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "envelope_key_clicksign": "env-1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "url_pdf_preliminar": "http://x/1.pdf",
                },
            ]
        )
        bg = BackgroundTasks()
        body = BulkReuniaoRequest(reuniao_ids=["R1"], reason="reenvio solicitado")

        resp = await bulk_router.bulk_reenviar_clicksign(
            body=body,
            request=_Request(),
            background_tasks=bg,
            actor=_ACTOR,
            supabase=sb,
        )
        assert resp.job_id
        assert resp.status == "pending"
        assert resp.total == 1

        # Linha criada em bulk_jobs com status pending
        job = sb.bulk_jobs[resp.job_id]
        assert job["status"] == "pending"
        assert job["job_type"] == "reenviar_clicksign"
        assert job["total"] == 1
        assert job["sucessos"] == 0
        assert job["falhas"] == []
        assert job["reason"] == "reenvio solicitado"

        # Task agendada (ainda nao executada)
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_completed_apos_background_task(self, monkeypatch):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "envelope_key_clicksign": "env-1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "url_pdf_preliminar": "http://x/1.pdf",
                },
                {
                    "id_reuniao": "R2",
                    "envelope_key_clicksign": None,
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "url_pdf_preliminar": "http://x/2.pdf",
                },
            ]
        )
        calls: list[tuple] = []

        def fake_notify(envelope_id: str) -> bool:
            calls.append(("notify", envelope_id))
            return True

        def fake_start(supabase, id_reuniao: str, reuniao: dict) -> None:
            calls.append(("start", id_reuniao))

        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "notify_signers", fake_notify)
        monkeypatch.setattr(clicksign_service, "start_signature_flow", fake_start)

        bg = BackgroundTasks()
        body = BulkReuniaoRequest(reuniao_ids=["R1", "R2", "R_INEXISTENTE"], reason="reenvio solicitado")
        resp = await bulk_router.bulk_reenviar_clicksign(
            body=body,
            request=_Request(),
            background_tasks=bg,
            actor=_ACTOR,
            supabase=sb,
        )

        # Executa a task em background manualmente
        await bg()

        job = sb.bulk_jobs[resp.job_id]
        assert job["status"] == "completed"
        assert job["sucessos"] == 2
        assert len(job["falhas"]) == 1
        assert job["falhas"][0]["id"] == "R_INEXISTENTE"
        assert job["finished_at"] is not None

        assert ("notify", "env-1") in calls
        assert ("start", "R2") in calls

        # Audit log: STARTED + COMPLETED
        actions = [r["action"] for r in sb.audit_rows]
        assert "BULK_REENVIAR_CLICKSIGN_STARTED" in actions
        assert "BULK_REENVIAR_CLICKSIGN_COMPLETED" in actions
        completed = next(r for r in sb.audit_rows if r["action"] == "BULK_REENVIAR_CLICKSIGN_COMPLETED")
        assert completed["metadata"]["sucessos"] == 2
        assert completed["metadata"]["bulk_job_id"] == resp.job_id


# ─── Testes: reprocessar-ia ──────────────────────────────────────────────────


class TestBulkReprocessarIA:
    @pytest.mark.asyncio
    async def test_completed_com_falha_parcial(self, monkeypatch):
        sb = _SupabaseMock(
            reunioes=[
                {"id_reuniao": "R1", "tipo": "Gerencial"},
                {"id_reuniao": "R2", "tipo": "Estrategica"},
            ]
        )

        def fake_download(supabase, bucket, path):
            if path.startswith("R1/"):
                return b"texto da transcricao"
            return None

        pipeline_calls: list[tuple] = []

        def fake_run(supabase, id_reuniao, bytes_, tipo):
            pipeline_calls.append((id_reuniao, tipo, bytes_))

        from app.pipeline import orchestrator
        from app.services import storage

        monkeypatch.setattr(storage, "download_file", fake_download)
        monkeypatch.setattr(orchestrator, "run_pipeline", fake_run)

        bg = BackgroundTasks()
        body = BulkReuniaoRequest(reuniao_ids=["R1", "R2"], reason="retry")
        resp = await bulk_router.bulk_reprocessar_ia(
            body=body,
            request=_Request(),
            background_tasks=bg,
            actor=_ACTOR,
            supabase=sb,
        )
        assert resp.total == 2
        await bg()

        job = sb.bulk_jobs[resp.job_id]
        assert job["status"] == "completed"
        assert job["sucessos"] == 1
        assert len(job["falhas"]) == 1
        assert job["falhas"][0]["id"] == "R2"

        assert pipeline_calls == [("R1", "Gerencial", b"texto da transcricao")]

        actions = [r["action"] for r in sb.audit_rows]
        assert "BULK_REPROCESSAR_IA_STARTED" in actions
        assert "BULK_REPROCESSAR_IA_COMPLETED" in actions


# ─── Testes: reenviar-email ──────────────────────────────────────────────────


class TestBulkReenviarEmail:
    @pytest.mark.asyncio
    async def test_completed_com_falha_sem_email(self, monkeypatch):
        sb = _SupabaseMock(
            participantes=[
                {"id": "P1", "email": "a@ex.com", "nome_completo": "Alice"},
                {"id": "P2", "email": "", "nome_completo": "Bob"},
            ]
        )

        sent: list[tuple] = []

        def fake_send(destinatario, assunto, html, texto):
            sent.append((destinatario, assunto))
            return True

        from app.services import email_service

        monkeypatch.setattr(email_service, "_enviar_email", fake_send)

        bg = BackgroundTasks()
        body = BulkEmailRequest(
            participante_ids=["P1", "P2", "P_INEXISTENTE"],
            assunto="Aviso importante",
            corpo="<p>mensagem</p>",
            reason="comunicado geral",
        )
        resp = await bulk_router.bulk_reenviar_email(
            body=body,
            request=_Request(),
            background_tasks=bg,
            actor=_ACTOR,
            supabase=sb,
        )
        assert resp.total == 3
        await bg()

        job = sb.bulk_jobs[resp.job_id]
        assert job["status"] == "completed"
        assert job["sucessos"] == 1
        assert len(job["falhas"]) == 2
        falha_ids = {f["id"] for f in job["falhas"]}
        assert falha_ids == {"P2", "P_INEXISTENTE"}

        assert sent == [("a@ex.com", "Aviso importante")]

        actions = [r["action"] for r in sb.audit_rows]
        assert "BULK_REENVIAR_EMAIL_STARTED" in actions
        assert "BULK_REENVIAR_EMAIL_COMPLETED" in actions


# ─── Testes: GET /jobs ───────────────────────────────────────────────────────


class TestGetBulkJob:
    @pytest.mark.asyncio
    async def test_get_job_status_retorna_campos(self):
        sb = _SupabaseMock()
        # Cria job manualmente
        now = datetime.now(UTC).isoformat()
        job_id = str(uuid.uuid4())
        sb.bulk_jobs[job_id] = {
            "id": job_id,
            "created_at": now,
            "updated_at": now,
            "actor_id": "P01",
            "actor_email": "admin@ex.com",
            "job_type": "reenviar_clicksign",
            "status": "completed",
            "target_ids": ["R1", "R2"],
            "total": 2,
            "sucessos": 2,
            "falhas": [],
            "metadata": {},
            "reason": "teste",
            "started_at": now,
            "finished_at": now,
        }

        resp = await bulk_router.get_bulk_job(job_id=job_id, actor=_ACTOR, supabase=sb)
        assert resp.id == job_id
        assert resp.status == "completed"
        assert resp.sucessos == 2
        assert resp.total == 2
        assert resp.target_ids == ["R1", "R2"]

    @pytest.mark.asyncio
    async def test_get_job_inexistente_404(self):
        sb = _SupabaseMock()
        with pytest.raises(HTTPException) as exc:
            await bulk_router.get_bulk_job(
                job_id="00000000-0000-0000-0000-000000000000",
                actor=_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_bulk_jobs(self):
        sb = _SupabaseMock()
        # Insere 2 jobs
        for i in range(2):
            now = datetime.now(UTC).isoformat()
            jid = str(uuid.uuid4())
            sb.bulk_jobs[jid] = {
                "id": jid,
                "created_at": now,
                "updated_at": now,
                "actor_id": "P01",
                "actor_email": "admin@ex.com",
                "job_type": "reenviar_clicksign",
                "status": "completed" if i == 0 else "running",
                "target_ids": ["R1"],
                "total": 1,
                "sucessos": 1 if i == 0 else 0,
                "falhas": [],
                "metadata": {},
                "reason": None,
                "started_at": now,
                "finished_at": now if i == 0 else None,
            }

        resp = await bulk_router.list_bulk_jobs(
            status_filter=None,
            limit=10,
            offset=0,
            actor=_ACTOR,
            supabase=sb,
        )
        assert resp.total == 2
        assert len(resp.rows) == 2

        # Filtro por status
        resp = await bulk_router.list_bulk_jobs(
            status_filter="running",
            limit=10,
            offset=0,
            actor=_ACTOR,
            supabase=sb,
        )
        assert resp.total == 1
        assert resp.rows[0].status == "running"
