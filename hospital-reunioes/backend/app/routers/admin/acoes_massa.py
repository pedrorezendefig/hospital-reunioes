"""Router /admin/bulk — acoes em massa para super admins, executadas em background.

Endpoints:
- POST /admin/bulk/reenviar-clicksign  agenda reenvio ClickSign de reunioes
- POST /admin/bulk/reprocessar-ia      agenda re-execucao do pipeline de IA
- POST /admin/bulk/reenviar-email      agenda disparo de email a participantes
- GET  /admin/bulk/jobs                lista jobs recentes (paginado)
- GET  /admin/bulk/jobs/{job_id}       consulta status de um job

Fluxo:
  1. POST cria linha em `bulk_jobs` com status='pending', total=N e devolve 202 {job_id}.
  2. `BackgroundTasks` (FastAPI) dispara a execucao pos-resposta.
  3. Worker muda status pra 'running' (+ started_at), itera, atualiza
     sucessos/falhas incrementalmente e finaliza com 'completed' / 'failed'.
  4. Log `audit_log` no inicio (BULK_*_STARTED) e fim (BULK_*_COMPLETED),
     com `bulk_job_id` no metadata.

Concorrencia:
- Cada job roda num BackgroundTask independente, mas a escrita em bulk_jobs eh
  feita unicamente pelo worker daquele job (nunca disputa com outro worker),
  portanto nao ha race na mesma linha.
- Atualizacoes sao UPDATEs incrementais por linha (sucessos += 1 via leitura
  local do worker + escrita), sem lock porque o worker e o unico escritor.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from starlette.requests import Request
from supabase import Client

from app.config import settings
from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import (
    BulkEmailRequest,
    BulkFailure,
    BulkJobAccepted,
    BulkJobList,
    BulkJobStatus,
    BulkReuniaoRequest,
)
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bulk", tags=["admin", "bulk"])


# ─── Helpers internos ────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_job(
    supabase: Client,
    actor: dict,
    job_type: str,
    target_ids: list[str],
    reason: Optional[str],
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Insere linha em bulk_jobs com status='pending' e retorna job_id."""
    row = {
        "actor_id": actor.get("id"),
        "actor_email": actor.get("email") or "desconhecido",
        "job_type": job_type,
        "status": "pending",
        "target_ids": target_ids,
        "total": len(target_ids),
        "sucessos": 0,
        "falhas": [],
        "metadata": metadata or {},
    }
    if reason is not None:
        row["reason"] = reason
    result = supabase.table("bulk_jobs").insert(row).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao criar bulk_job",
        )
    return str(result.data[0]["id"])


def _update_job(supabase: Client, job_id: str, patch: dict[str, Any]) -> None:
    """Atualiza linha de bulk_jobs. Falhas sao logadas mas nao interrompem o worker."""
    try:
        patch = dict(patch)
        patch["updated_at"] = _now_iso()
        supabase.table("bulk_jobs").update(patch).eq("id", job_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bulk_jobs] Falha ao atualizar job {job_id}: {exc}")


def _finalize_job(
    supabase: Client,
    job_id: str,
    sucessos: int,
    falhas: list[BulkFailure],
    status_value: str = "completed",
) -> None:
    """Marca job como completed/failed com contadores finais."""
    _update_job(
        supabase,
        job_id,
        {
            "status": status_value,
            "sucessos": sucessos,
            "falhas": [f.model_dump() for f in falhas],
            "finished_at": _now_iso(),
        },
    )


def _log_started(
    supabase: Client,
    actor: dict,
    action: str,
    job_id: str,
    target_ids: list[str],
    reason: Optional[str],
    request: Optional[Request],
) -> None:
    audit.log_action(
        supabase,
        actor=actor,
        action=f"{action}_STARTED",
        target_type="bulk",
        target_id=job_id,
        metadata={
            "bulk_job_id": job_id,
            "total": len(target_ids),
            "target_ids": target_ids,
        },
        reason=reason,
        request=request,
    )


def _log_completed(
    supabase: Client,
    actor: dict,
    action: str,
    job_id: str,
    target_ids: list[str],
    sucessos: int,
    falhas: list[BulkFailure],
    reason: Optional[str],
    request: Optional[Request],
) -> None:
    audit.log_action(
        supabase,
        actor=actor,
        action=f"{action}_COMPLETED",
        target_type="bulk",
        target_id=job_id,
        metadata={
            "bulk_job_id": job_id,
            "target_ids": target_ids,
            "sucessos": sucessos,
            "falhas": [f.model_dump() for f in falhas],
        },
        reason=reason,
        request=request,
    )


# ─── Workers (executam em background) ───────────────────────────────────────


def _worker_reenviar_clicksign(
    supabase: Client,
    job_id: str,
    actor: dict,
    reuniao_ids: list[str],
    reason: Optional[str],
) -> None:
    """Reenvia ClickSign para cada reuniao. Escreve progresso em bulk_jobs."""
    from app.services import clicksign_service

    _log_started(supabase, actor, "BULK_REENVIAR_CLICKSIGN", job_id, reuniao_ids, reason, None)
    _update_job(supabase, job_id, {"status": "running", "started_at": _now_iso()})

    sucessos = 0
    falhas: list[BulkFailure] = []

    try:
        for reuniao_id in reuniao_ids:
            try:
                result = (
                    supabase.table("reunioes")
                    .select("id_reuniao, envelope_key_clicksign, status_ata, url_pdf_preliminar")
                    .eq("id_reuniao", reuniao_id)
                    .execute()
                )
                if not result.data:
                    falhas.append(BulkFailure(id=reuniao_id, erro="Reuniao nao encontrada"))
                    continue
                reuniao = result.data[0]
                envelope = reuniao.get("envelope_key_clicksign")
                if envelope:
                    ok = clicksign_service.notify_signers(envelope)
                    if not ok:
                        falhas.append(
                            BulkFailure(id=reuniao_id, erro="notify_signers retornou falso")
                        )
                        continue
                else:
                    clicksign_service.start_signature_flow(supabase, reuniao_id, reuniao)
                sucessos += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"[bulk/reenviar-clicksign] falha para {reuniao_id}: {exc}", exc_info=True
                )
                falhas.append(BulkFailure(id=reuniao_id, erro=str(exc)))

            # Incremental — write-through leve (tolera falha)
            _update_job(
                supabase,
                job_id,
                {"sucessos": sucessos, "falhas": [f.model_dump() for f in falhas]},
            )

        _finalize_job(supabase, job_id, sucessos, falhas, status_value="completed")
    except Exception as exc:  # noqa: BLE001 — falha catastrofica do worker
        logger.exception(f"[bulk/reenviar-clicksign] worker falhou: {exc}")
        _finalize_job(supabase, job_id, sucessos, falhas, status_value="failed")
    finally:
        _log_completed(
            supabase, actor, "BULK_REENVIAR_CLICKSIGN", job_id, reuniao_ids,
            sucessos, falhas, reason, None,
        )


def _worker_reprocessar_ia(
    supabase: Client,
    job_id: str,
    actor: dict,
    reuniao_ids: list[str],
    reason: Optional[str],
) -> None:
    """Re-executa o pipeline de IA para cada reuniao."""
    from app.pipeline import orchestrator
    from app.services import storage

    _log_started(supabase, actor, "BULK_REPROCESSAR_IA", job_id, reuniao_ids, reason, None)
    _update_job(supabase, job_id, {"status": "running", "started_at": _now_iso()})

    sucessos = 0
    falhas: list[BulkFailure] = []

    try:
        for reuniao_id in reuniao_ids:
            try:
                result = (
                    supabase.table("reunioes")
                    .select("id_reuniao, tipo")
                    .eq("id_reuniao", reuniao_id)
                    .execute()
                )
                if not result.data:
                    falhas.append(BulkFailure(id=reuniao_id, erro="Reuniao nao encontrada"))
                    continue
                reuniao = result.data[0]
                transcricao_bytes = storage.download_file(
                    supabase,
                    settings.supabase_storage_bucket_transcricoes,
                    f"{reuniao_id}/transcricao.txt",
                )
                if not transcricao_bytes:
                    falhas.append(
                        BulkFailure(id=reuniao_id, erro="Transcricao nao encontrada no storage")
                    )
                    continue
                tipo_reuniao = reuniao.get("tipo") or "Gerencial"
                orchestrator.run_pipeline(supabase, reuniao_id, transcricao_bytes, tipo_reuniao)
                sucessos += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"[bulk/reprocessar-ia] falha para {reuniao_id}: {exc}", exc_info=True
                )
                falhas.append(BulkFailure(id=reuniao_id, erro=str(exc)))

            _update_job(
                supabase,
                job_id,
                {"sucessos": sucessos, "falhas": [f.model_dump() for f in falhas]},
            )

        _finalize_job(supabase, job_id, sucessos, falhas, status_value="completed")
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[bulk/reprocessar-ia] worker falhou: {exc}")
        _finalize_job(supabase, job_id, sucessos, falhas, status_value="failed")
    finally:
        _log_completed(
            supabase, actor, "BULK_REPROCESSAR_IA", job_id, reuniao_ids,
            sucessos, falhas, reason, None,
        )


def _worker_reenviar_email(
    supabase: Client,
    job_id: str,
    actor: dict,
    participante_ids: list[str],
    assunto: str,
    corpo: str,
    reason: Optional[str],
) -> None:
    """Dispara email em lote para participantes."""
    from app.services import email_service

    _log_started(
        supabase, actor, "BULK_REENVIAR_EMAIL", job_id, participante_ids, reason, None
    )
    _update_job(supabase, job_id, {"status": "running", "started_at": _now_iso()})

    sucessos = 0
    falhas: list[BulkFailure] = []

    try:
        result = (
            supabase.table("participantes")
            .select("id, email, nome_completo")
            .in_("id", participante_ids)
            .execute()
        )
        by_id = {row["id"]: row for row in (result.data or [])}

        for pid in participante_ids:
            row = by_id.get(pid)
            if not row:
                falhas.append(BulkFailure(id=pid, erro="Participante nao encontrado"))
            else:
                email = (row.get("email") or "").strip()
                if not email:
                    falhas.append(BulkFailure(id=pid, erro="Participante sem email"))
                else:
                    try:
                        ok = email_service._enviar_email(email, assunto, corpo, corpo)
                        if ok:
                            sucessos += 1
                        else:
                            falhas.append(BulkFailure(id=pid, erro="Falha no envio do email"))
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            f"[bulk/reenviar-email] falha para {pid}: {exc}", exc_info=True
                        )
                        falhas.append(BulkFailure(id=pid, erro=str(exc)))

            _update_job(
                supabase,
                job_id,
                {"sucessos": sucessos, "falhas": [f.model_dump() for f in falhas]},
            )

        _finalize_job(supabase, job_id, sucessos, falhas, status_value="completed")
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[bulk/reenviar-email] worker falhou: {exc}")
        _finalize_job(supabase, job_id, sucessos, falhas, status_value="failed")
    finally:
        _log_completed(
            supabase, actor, "BULK_REENVIAR_EMAIL", job_id, participante_ids,
            sucessos, falhas, reason, None,
        )


# ─── Endpoints: disparo (202 Accepted) ───────────────────────────────────────


@router.post(
    "/reenviar-clicksign",
    response_model=BulkJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_reenviar_clicksign(
    body: BulkReuniaoRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> BulkJobAccepted:
    """Agenda reenvio ClickSign em background e retorna job_id."""
    job_id = _create_job(
        supabase,
        actor=actor,
        job_type="reenviar_clicksign",
        target_ids=body.reuniao_ids,
        reason=body.reason,
    )
    background_tasks.add_task(
        _worker_reenviar_clicksign,
        supabase,
        job_id,
        actor,
        list(body.reuniao_ids),
        body.reason,
    )
    return BulkJobAccepted(job_id=job_id, status="pending", total=len(body.reuniao_ids))


@router.post(
    "/reprocessar-ia",
    response_model=BulkJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_reprocessar_ia(
    body: BulkReuniaoRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> BulkJobAccepted:
    """Agenda reprocessamento IA em background e retorna job_id."""
    job_id = _create_job(
        supabase,
        actor=actor,
        job_type="reprocessar_ia",
        target_ids=body.reuniao_ids,
        reason=body.reason,
    )
    background_tasks.add_task(
        _worker_reprocessar_ia,
        supabase,
        job_id,
        actor,
        list(body.reuniao_ids),
        body.reason,
    )
    return BulkJobAccepted(job_id=job_id, status="pending", total=len(body.reuniao_ids))


@router.post(
    "/reenviar-email",
    response_model=BulkJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_reenviar_email(
    body: BulkEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> BulkJobAccepted:
    """Agenda disparo de email em massa em background e retorna job_id."""
    if not body.participante_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lista de participantes vazia",
        )
    job_id = _create_job(
        supabase,
        actor=actor,
        job_type="reenviar_email",
        target_ids=body.participante_ids,
        reason=body.reason,
        metadata={"assunto": body.assunto},
    )
    background_tasks.add_task(
        _worker_reenviar_email,
        supabase,
        job_id,
        actor,
        list(body.participante_ids),
        body.assunto,
        body.corpo,
        body.reason,
    )
    return BulkJobAccepted(
        job_id=job_id, status="pending", total=len(body.participante_ids)
    )


# ─── Endpoints: consulta de status ──────────────────────────────────────────


def _row_to_status(row: dict) -> BulkJobStatus:
    return BulkJobStatus(
        id=str(row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        actor_id=row.get("actor_id"),
        actor_email=row.get("actor_email") or "desconhecido",
        job_type=row["job_type"],
        status=row["status"],
        target_ids=list(row.get("target_ids") or []),
        total=row.get("total") or 0,
        sucessos=row.get("sucessos") or 0,
        falhas=[BulkFailure(**f) for f in (row.get("falhas") or [])],
        metadata=row.get("metadata") or {},
        reason=row.get("reason"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
    )


@router.get("/jobs/{job_id}", response_model=BulkJobStatus)
async def get_bulk_job(
    job_id: str,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> BulkJobStatus:
    """Consulta o status de um job de bulk (super admin only)."""
    result = supabase.table("bulk_jobs").select("*").eq("id", job_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job nao encontrado"
        )
    return _row_to_status(result.data[0])


@router.get("/jobs", response_model=BulkJobList)
async def list_bulk_jobs(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> BulkJobList:
    """Lista jobs recentes (todos — super admin enxerga tudo)."""
    query = supabase.table("bulk_jobs").select("*", count="exact")
    if status_filter:
        query = query.eq("status", status_filter)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    rows = [_row_to_status(r) for r in (result.data or [])]
    total = getattr(result, "count", None) or len(rows)
    return BulkJobList(total=total, rows=rows, limit=limit, offset=offset)
