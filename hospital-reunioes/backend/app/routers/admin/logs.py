"""Router /admin/logs — consulta do audit_log para super admins.

Endpoints:
- GET /admin/logs             lista linhas do audit_log com filtros e paginacao.
- GET /admin/logs/actions     retorna DISTINCT dos valores `action` (para filtros de UI).
- GET /admin/logs/export.csv  exporta TODAS as linhas que batem com os filtros
                              como CSV (streaming, com limite de seguranca).

Todos protegidos por `require_super_admin`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import Iterator
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import AuditLogPage, AuditLogRow
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/logs", tags=["admin", "logs"])


MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# Limite de seguranca do export CSV: mesmo que os filtros batam com muitas linhas,
# o endpoint para aqui e sinaliza overflow ao caller. Ajustavel conforme uso real.
EXPORT_CSV_MAX_ROWS = 50_000
EXPORT_CSV_BATCH_SIZE = 1_000
EXPORT_CSV_COLUMNS = [
    "timestamp",
    "actor_id",
    "actor_email",
    "action",
    "target_type",
    "target_id",
    "reason",
    "ip_address",
    "metadata",
]


def _csv_to_list(value: str | None) -> list[str] | None:
    """Aceita `"a,b,c"` ou `None` e retorna `["a","b","c"]` ou `None`.

    Strings vazias apos split sao descartadas. Usado para filtros multi-select
    enviados pelo frontend como CSV.
    """
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def _apply_in_or_eq(query, column: str, values: list[str] | None):
    """Aplica `.eq(column, v)` para 1 valor, `.in_(column, values)` para varios.

    Retorna o builder original se `values` for None/empty (sem filtro).
    """
    if not values:
        return query
    if len(values) == 1:
        return query.eq(column, values[0])
    return query.in_(column, values)


def _parse_iso_datetime(value: str, field_name: str) -> str:
    """Valida uma string ISO 8601 / date e retorna a string serializavel.

    Aceita tanto `YYYY-MM-DD` quanto ISO completo. Usa fromisoformat do Python.
    """
    try:
        # Python 3.11+: fromisoformat aceita 'Z' via replace abaixo para compat
        cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(cleaned)
        return dt.isoformat()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parametro '{field_name}' invalido (ISO 8601 esperado): {exc}",
        )


@router.get("", response_model=AuditLogPage)
async def list_logs(
    actor_id: str | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> AuditLogPage:
    """Lista linhas do audit_log aplicando filtros opcionais.

    Ordem: `timestamp DESC`. Paginacao via `limit`/`offset`.
    """
    # Query principal (linhas da pagina)
    query = supabase.table("audit_log").select("*", count="exact")

    if actor_id:
        query = query.eq("actor_id", actor_id)
    if actor_email:
        query = query.eq("actor_email", actor_email)
    query = _apply_in_or_eq(query, "action", _csv_to_list(action))
    query = _apply_in_or_eq(query, "target_type", _csv_to_list(target_type))
    if target_id:
        query = query.eq("target_id", target_id)
    if from_:
        query = query.gte("timestamp", _parse_iso_datetime(from_, "from"))
    if to:
        query = query.lte("timestamp", _parse_iso_datetime(to, "to"))

    query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)

    result = query.execute()
    rows = result.data or []
    total = getattr(result, "count", None)
    if total is None:
        # Fallback se o driver nao suportar count na mesma chamada
        total = len(rows) + offset

    return AuditLogPage(
        total=int(total),
        rows=[AuditLogRow(**row) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get("/actions", response_model=list[str])
async def list_distinct_actions(
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> list[str]:
    """Retorna a lista DISTINCT dos valores de `action` presentes no log.

    Usado pelo frontend para popular o filtro de acao sem hardcode.
    """
    result = supabase.table("audit_log").select("action").execute()
    actions = sorted({row["action"] for row in (result.data or []) if row.get("action")})
    return actions


# ─── Export CSV ──────────────────────────────────────────────────────────────


def _apply_export_filters(
    supabase: Client,
    *,
    actor_id: str | None,
    actor_email: str | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    from_iso: str | None,
    to_iso: str | None,
):
    """Monta a query base do audit_log aplicando os mesmos filtros de list_logs.

    Retorna o builder ja filtrado e ordenado (timestamp DESC), sem range.
    """
    query = supabase.table("audit_log").select("*")
    if actor_id:
        query = query.eq("actor_id", actor_id)
    if actor_email:
        query = query.eq("actor_email", actor_email)
    query = _apply_in_or_eq(query, "action", _csv_to_list(action))
    query = _apply_in_or_eq(query, "target_type", _csv_to_list(target_type))
    if target_id:
        query = query.eq("target_id", target_id)
    if from_iso:
        query = query.gte("timestamp", from_iso)
    if to_iso:
        query = query.lte("timestamp", to_iso)
    return query.order("timestamp", desc=True)


def _fetch_export_rows(
    supabase: Client,
    *,
    actor_id: str | None,
    actor_email: str | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    from_iso: str | None,
    to_iso: str | None,
    max_rows: int,
    batch_size: int,
) -> tuple[list[dict], bool]:
    """Pagina o audit_log em lotes e retorna ate `max_rows` linhas.

    Retorna (rows, overflow) — overflow=True se havia mais linhas que `max_rows`.
    """
    collected: list[dict] = []
    offset = 0
    overflow = False
    while True:
        remaining = max_rows - len(collected)
        if remaining <= 0:
            # Checa se ainda havia mais linhas apos o limite
            probe = (
                _apply_export_filters(
                    supabase,
                    actor_id=actor_id,
                    actor_email=actor_email,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    from_iso=from_iso,
                    to_iso=to_iso,
                )
                .range(offset, offset)
                .execute()
            )
            if probe.data:
                overflow = True
            break
        current_batch = min(batch_size, remaining)
        result = (
            _apply_export_filters(
                supabase,
                actor_id=actor_id,
                actor_email=actor_email,
                action=action,
                target_type=target_type,
                target_id=target_id,
                from_iso=from_iso,
                to_iso=to_iso,
            )
            .range(offset, offset + current_batch - 1)
            .execute()
        )
        batch = result.data or []
        if not batch:
            break
        collected.extend(batch)
        if len(batch) < current_batch:
            break
        offset += current_batch
    return collected, overflow


# Caracteres que, quando aparecem como primeiro caractere de uma celula CSV,
# podem ser interpretados como inicio de formula por Excel/LibreOffice/Google
# Sheets (CSV injection / formula injection — CWE-1236).
_DANGEROUS_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(v) -> str:
    """Sanitiza valor para CSV prefixando com `'` se comeca com caractere perigoso."""
    s = "" if v is None else str(v)
    if s and s[0] in _DANGEROUS_LEAD:
        return "'" + s
    return s


def _csv_row_for(row: dict) -> list[str]:
    """Converte uma linha do audit_log no formato CSV."""
    metadata = row.get("metadata")
    if metadata is None:
        metadata_str = ""
    else:
        try:
            metadata_str = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            metadata_str = str(metadata)

    ts = row.get("timestamp")
    if isinstance(ts, datetime):
        ts_str = ts.isoformat()
    else:
        ts_str = "" if ts is None else str(ts)

    return [
        _csv_safe(ts_str),
        _csv_safe(row.get("actor_id")),
        _csv_safe(row.get("actor_email")),
        _csv_safe(row.get("action")),
        _csv_safe(row.get("target_type")),
        _csv_safe(row.get("target_id")),
        _csv_safe(row.get("reason")),
        _csv_safe(row.get("ip_address")),
        _csv_safe(metadata_str),
    ]


def _stream_csv(rows: list[dict]) -> Iterator[bytes]:
    """Gera chunks CSV (bytes utf-8) a partir da lista de linhas."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(EXPORT_CSV_COLUMNS)
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow(_csv_row_for(row))
        chunk = buffer.getvalue()
        if chunk:
            yield chunk.encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)


@router.get("/export.csv")
async def export_logs_csv(
    request: Request,
    actor_id: str | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    reason: str | None = Query(default=None, max_length=1000),
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Exporta o audit_log como CSV aplicando os mesmos filtros do GET /admin/logs.

    - Sem paginacao: retorna tudo que bater com os filtros, ate `EXPORT_CSV_MAX_ROWS`.
    - `Content-Type: text/csv; charset=utf-8`.
    - Nome do arquivo: `audit_log_YYYY-MM-DD.csv` (data atual UTC).
    - Grava a propria chamada em audit_log como `EXPORT_LOGS` com os filtros usados
      e o numero de linhas exportadas.
    """
    from_iso = _parse_iso_datetime(from_, "from") if from_ else None
    to_iso = _parse_iso_datetime(to, "to") if to else None

    rows, overflow = _fetch_export_rows(
        supabase,
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        from_iso=from_iso,
        to_iso=to_iso,
        max_rows=EXPORT_CSV_MAX_ROWS,
        batch_size=EXPORT_CSV_BATCH_SIZE,
    )

    if overflow:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Resultado excede o limite de seguranca de {EXPORT_CSV_MAX_ROWS} "
                "linhas. Refine os filtros (ex: intervalo de datas) e tente novamente."
            ),
        )

    filename = f"audit_log_{date.today().isoformat()}.csv"

    filtros = {
        "actor_id": actor_id,
        "actor_email": actor_email,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "from": from_,
        "to": to,
    }
    filtros_ativos = {k: v for k, v in filtros.items() if v}

    audit.log_action(
        supabase,
        actor=actor,
        action="EXPORT_LOGS",
        target_type="audit_log",
        target_id="export",
        metadata={
            "filtros": filtros_ativos,
            "linhas_exportadas": len(rows),
            "limite_seguranca": EXPORT_CSV_MAX_ROWS,
        },
        reason=reason,
        request=request,
    )

    return StreamingResponse(
        _stream_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
