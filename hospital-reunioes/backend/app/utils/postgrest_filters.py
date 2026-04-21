"""Validadores para inputs interpolados em filtros PostgREST .or_().

Caracteres como ',', '(', ')', ':' tem significado especial em filtros
PostgREST. Inputs user-controlled devem passar por estas validacoes
antes da interpolacao em f-strings, prevenindo injecao de filtros.
"""
import re
import uuid

from fastapi import HTTPException

_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_ID_RE = re.compile(r"^[A-Z0-9_-]+$")


def validate_email_for_filter(email: str) -> str:
    """Valida email antes de interpolar em filtro PostgREST .or_()."""
    if not email or not _EMAIL_RE.match(email) or any(c in email for c in ",():"):
        raise HTTPException(status_code=400, detail="email invalido")
    return email


def validate_uuid_for_filter(value: str) -> str:
    """Valida UUID antes de interpolar em filtro PostgREST .or_()."""
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="uuid invalido")
    return value


def validate_pid_for_filter(pid: str) -> str:
    """Valida ID curto (VARCHAR custom) antes de interpolar em filtro PostgREST .or_()."""
    if not pid or not _ID_RE.match(pid):
        raise HTTPException(status_code=400, detail="id invalido")
    return pid
