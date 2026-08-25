"""Tokens do portal do setor (issue #326, ADR 0034 decisão 4).

Mesmo padrão do Aceite interno (`aceite_service`): o token em claro vive só no
link do email; o banco guarda o hash SHA-256. Cada token é restrito a uma
manifestação e um destinatário, expira, e é de uso único (claim atômico).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets


class TokenInvalidoError(Exception):
    """Token que não existe: link adulterado ou de outro sistema."""


class TokenUsadoError(Exception):
    """Token já consumido por uma resposta: a segunda tentativa não duplica."""


class TokenExpiradoError(Exception):
    """Token vencido, ou o caso já saiu do estado que aceita resposta."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def emitir(supabase, *, manifestacao_id: str, destinatario_nome: str, destinatario_email: str) -> str:
    """Emite o token que vai no email de acionamento e devolve o valor em claro.

    Reenvio emite token novo e apaga o antigo não usado: existe no máximo um
    link válido por destinatário, e o mais recente é o que vale. Token já usado
    fica na tabela, como rastro de quem respondeu."""
    token = secrets.token_urlsafe(32)
    (
        supabase.table("ouvidoria_setor_tokens")
        .delete()
        .eq("manifestacao_id", manifestacao_id)
        .eq("destinatario_email", destinatario_email)
        .is_("usado_em", "null")
        .execute()
    )
    (
        supabase.table("ouvidoria_setor_tokens")
        .insert(
            {
                "manifestacao_id": manifestacao_id,
                "destinatario_nome": destinatario_nome,
                "destinatario_email": destinatario_email,
                "token_hash": _hash_token(token),
            }
        )
        .execute()
    )
    return token


def carregar(supabase, token: str, agora: dt.datetime) -> dict:
    """Acha o vínculo do token e aplica as regras de recusa.

    Levanta `TokenInvalidoError` (sem linha), `TokenUsadoError` (resposta já
    entrou por ele) ou `TokenExpiradoError` (passou da validade)."""
    result = (
        supabase.table("ouvidoria_setor_tokens")
        .select("id, manifestacao_id, destinatario_nome, destinatario_email, expira_em, usado_em")
        .eq("token_hash", _hash_token(token))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise TokenInvalidoError()
    vinculo = result.data[0]
    if vinculo.get("usado_em"):
        raise TokenUsadoError()
    expira_em = vinculo.get("expira_em")
    if expira_em and dt.datetime.fromisoformat(str(expira_em)) < agora:
        raise TokenExpiradoError()
    return vinculo


def consumir(supabase, vinculo: dict, agora: dt.datetime) -> bool:
    """Claim atômico do uso único: só quem preencher `usado_em` primeiro leva.

    Devolve False quando outra requisição já consumiu o token (a idempotência
    do critério 6: responder duas vezes não duplica nada)."""
    result = (
        supabase.table("ouvidoria_setor_tokens")
        .update({"usado_em": agora.isoformat()})
        .eq("id", vinculo["id"])
        .is_("usado_em", "null")
        .execute()
    )
    return bool(result.data)


def devolver(supabase, vinculo: dict) -> None:
    """Solta o claim quando a resposta falhou depois dele: o titular pode
    tentar de novo pelo mesmo link, em vez de ficar trancado para fora."""
    (supabase.table("ouvidoria_setor_tokens").update({"usado_em": None}).eq("id", vinculo["id"]).execute())
