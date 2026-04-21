"""Audit log service — grava ações destrutivas/administrativas em audit_log.

Uso tipico:

    from app.services.audit import log_action

    log_action(
        supabase,
        actor=participante_dict,
        action="DELETE_ATA",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"status_before": "ASSINADA"},
        reason="motivo informado pelo super admin",
        request=request,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _extract_ip(request: Optional[Any]) -> Optional[str]:
    """Extrai IP do request FastAPI/Starlette, se disponivel."""
    if request is None:
        return None
    try:
        # Prioriza X-Forwarded-For (proxy/loadbalancer)
        fwd = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
        if fwd:
            return fwd.split(",")[0].strip()
        client = getattr(request, "client", None)
        if client and getattr(client, "host", None):
            return client.host
    except Exception:
        return None
    return None


def log_action(
    supabase,
    actor: Optional[dict],
    action: str,
    target_type: str,
    target_id: str,
    metadata: Optional[dict] = None,
    reason: Optional[str] = None,
    request: Optional[Any] = None,
) -> None:
    """Grava uma linha em audit_log.

    Nunca levanta excecao — falhas de audit NAO devem quebrar a acao do usuario;
    apenas logam em warning para investigacao.

    Args:
        supabase: client Supabase (ex: get_supabase_client()).
        actor: dict do participante autor (campos: id, email). Pode ser None
            se o actor nao tiver registro em participantes (edge case).
        action: codigo da acao (DELETE_ATA, RESET_PASSWORD, PROMOTE_SUPER_ADMIN...).
        target_type: tipo do alvo (reuniao, participante, ata, pendencia, super_admin).
        target_id: identificador do alvo.
        metadata: dict arbitrario (ex: valores antes/depois).
        reason: motivo informado pelo super admin em acoes criticas.
        request: objeto Request do FastAPI/Starlette (para capturar IP).
    """
    try:
        actor_id = (actor or {}).get("id")
        actor_email = (actor or {}).get("email") or "desconhecido"

        row: dict[str, Any] = {
            "actor_id": actor_id,
            "actor_email": actor_email,
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "metadata": metadata or {},
        }
        if reason is not None:
            row["reason"] = reason
        ip = _extract_ip(request)
        if ip is not None:
            row["ip_address"] = ip

        supabase.table("audit_log").insert(row).execute()
    except Exception as e:  # noqa: BLE001 — audit nunca deve quebrar o caller
        logger.warning(
            f"[audit] Falha ao gravar log (action={action}, target={target_type}:{target_id}): {e}"
        )
