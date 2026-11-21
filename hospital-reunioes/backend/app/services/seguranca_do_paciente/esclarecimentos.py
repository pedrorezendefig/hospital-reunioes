"""As perguntas de esclarecimento a quem notificou (issue #1991, PRD #1979).

O agente de triagem pode propor até duas perguntas curtas
(`perguntas_ao_notificante`, na linha de triagem dele). Quem notificou as vê
depois do registro, na confirmação, ou mais tarde, na página de
acompanhamento, e responde em poucas palavras. As perguntas a mostrar são as
da linha mais recente do agente que ainda não têm resposta.

Cada resposta fica gravada em `nsp_esclarecimentos` (migration 195). Enquanto
a triagem não foi confirmada, a resposta roda o agente de novo, com as
respostas na entrada; depois da confirmação, ela só fica gravada.
"""

from __future__ import annotations

from typing import Any

from postgrest.exceptions import APIError

# Os estados de antes da confirmação da triagem (migration 174): confirmar
# leva o caso a Classificada ou a Em análise agregada (issue #1992).
_ANTES_DA_CONFIRMACAO = ("recebida", "em_triagem")


class PerguntaSemVagaError(ValueError):
    """A resposta é de uma pergunta que não está mais esperando resposta."""


def triagem_confirmada(caso: dict[str, Any]) -> bool:
    return (caso.get("estado") or "recebida") not in _ANTES_DA_CONFIRMACAO


def _ultima_do_agente(supabase, notificacao_id: str) -> dict[str, Any] | None:
    linhas = (
        supabase.table("nsp_triagens")
        .select("id, versao, perguntas_ao_notificante")
        .eq("notificacao_id", notificacao_id)
        .eq("autor_tipo", "agente")
        .order("versao", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return linhas[0] if linhas else None


def respondidas(supabase, notificacao_id: str) -> list[dict[str, Any]]:
    """As perguntas já respondidas, na ordem em que foram respondidas."""
    return (
        supabase.table("nsp_esclarecimentos")
        .select("pergunta, resposta, criado_em")
        .eq("notificacao_id", notificacao_id)
        .order("criado_em")
        .execute()
        .data
    ) or []


def pendentes(supabase, notificacao_id: str) -> tuple[list[str], dict[str, Any] | None]:
    """As perguntas da linha mais recente do agente que ainda não têm
    resposta, e a linha. Pergunta repetida numa rodada nova não volta."""
    ultima = _ultima_do_agente(supabase, notificacao_id)
    if ultima is None:
        return [], None
    ja = {linha["pergunta"] for linha in respondidas(supabase, notificacao_id)}
    return [p for p in (ultima.get("perguntas_ao_notificante") or []) if p not in ja], ultima


def responder(supabase, caso: dict[str, Any], respostas: list[tuple[str, str]]) -> None:
    """Grava as respostas de quem notificou. A pergunta que não está
    esperando resposta recusa tudo, sem gravar nada. Se o agente lê de novo,
    quem decide é a nova leitura (`agente_de_triagem`), que confere a
    confirmação na hora em que roda."""
    abertas, ultima = pendentes(supabase, caso["id"])
    perguntas = [pergunta for pergunta, _ in respostas]
    if not respostas or len(set(perguntas)) != len(perguntas) or any(p not in abertas for p in perguntas):
        raise PerguntaSemVagaError("pergunta sem resposta esperada")
    try:
        supabase.table("nsp_esclarecimentos").insert(
            [
                {"notificacao_id": caso["id"], "triagem_id": ultima["id"], "pergunta": pergunta, "resposta": resposta}
                for pergunta, resposta in respostas
            ]
        ).execute()
    except APIError as erro:
        # Dois envios da mesma resposta ao mesmo tempo: o segundo bate no
        # índice único da migration 195.
        if erro.code == "23505":
            raise PerguntaSemVagaError("pergunta já respondida") from erro
        raise


def texto_para_o_agente(supabase, notificacao_id: str) -> str:
    """As perguntas e as respostas, uma depois da outra, para o campo
    `esclarecimentos` da entrada do agente (Anexo B)."""
    return "\n".join(
        f"Pergunta: {linha['pergunta']}\nResposta: {linha['resposta']}"
        for linha in respondidas(supabase, notificacao_id)
    )
