"""Helpers para parsing e sanitização de query params HTTP."""

import re

_ILIKE_INJECTION_CHARS = re.compile(r"[,:()\\/%_]")


def parse_csv_param(value: str | None) -> list[str] | None:
    """Converte parâmetro CSV (ex: 'TI,Cirurgia') em lista. Retorna None se vazio."""
    if not value or not value.strip():
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def sanitize_for_ilike(value: str) -> str:
    """Remove caracteres especiais que podem injetar em filtros PostgREST `.or_(f'...ilike.{value}...')`.

    PostgREST trata `,`, `:`, `(`, `)`, `\\`, `/` como separadores de filter; `%` e `_`
    são wildcards do LIKE (não queremos que o usuário controle isso). A função apenas
    remove esses caracteres — não tenta escapar (PostgREST não tem syntax pra escape).
    """
    return _ILIKE_INJECTION_CHARS.sub("", value).strip()
