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
from typing import Any

logger = logging.getLogger(__name__)


def _extract_ip(request: Any | None) -> str | None:
    """De onde a pessoa agiu, como o uvicorn traduziu.

    O `X-Forwarded-For` NÃO é lido aqui (issue #375, item 16). O uvicorn roda
    com `--proxy-headers` e uma lista fechada de proxies confiáveis (o Dockerfile
    e o compose, provados em `test_proxy_confiavel.py`), então
    `request.client.host` já é o IP do visitante quando quem conectou foi o
    proxy da casa, e é o IP de quem conectou quando não foi.

    Ler o cabeçalho por cima disso só devolvia a escolha do IP a quem batesse
    direto na API, no campo que existe justamente para dizer de onde a pessoa
    agiu. Sem conexão, o campo fica vazio: melhor nulo que mentiroso."""
    if request is None:
        return None
    try:
        client = getattr(request, "client", None)
        if client and getattr(client, "host", None):
            return client.host
    except Exception:
        return None
    return None


def log_action(
    supabase,
    actor: dict | None,
    action: str,
    target_type: str,
    target_id: str,
    metadata: dict | None = None,
    reason: str | None = None,
    request: Any | None = None,
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
        logger.warning(f"[audit] Falha ao gravar log (action={action}, target={target_type}:{target_id}): {e}")
