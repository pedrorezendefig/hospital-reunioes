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


class TokenRevogadoError(Exception):
    """Token derrubado por um acionamento posterior do mesmo caso (ADR 0055):
    o link é da área que já não está com a manifestação."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def emitir(supabase, *, manifestacao_id: str, destinatario_nome: str, destinatario_email: str) -> str:
    """Emite o token que vai no email de acionamento e devolve o valor em claro.

    Cada emissão nasce ao lado das anteriores, sem apagar nada. O token em
    claro só existe dentro do email que já saiu, então apagar o antigo mataria
    um link que pode estar na caixa de entrada do titular: o despacho tenta de
    novo quando o provedor não confirma a entrega, e o email da tentativa
    anterior pode ter chegado mesmo assim. Vários links vivos não somam risco:
    cada um é de uso único, preso a esta manifestação e a este destinatário, e
    o primeiro que responder tira o caso de `aguardando_area`, o que faz os
    demais recusarem sozinhos."""
    token = secrets.token_urlsafe(32)
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


def revogar_os_vivos(supabase, manifestacao_id: str, agora: dt.datetime) -> int:
    """Derruba todo link vivo da manifestação e devolve quantos caíram.

    Chamada no acionamento que sai de `em_classificacao` (ADR 0055): a área
    nova recebe o caso, e o que sobrou da anterior (o link do acionamento dela
    e o de cada cobrança) não pode continuar abrindo uma porta de escrita sem
    login. Revogar zero links é no-op, que é o primeiro despacho de todo caso.

    `usado_em` não é tocado: link já consumido continua contando que alguém
    respondeu por ele, e link revogado continua contando que ninguém respondeu.
    As duas colunas são independentes, e carimbar a segunda não apaga a
    primeira. O filtro por `revogado_em` nulo guarda o instante da PRIMEIRA
    revogação, que é quando o caso de fato saiu da área.

    O UPDATE NÃO filtra por `usado_em` nulo, e isso é regra, não sobra: o token
    com claim EM VOO tem `usado_em` preenchido, e pular a linha dele deixaria
    uma porta aberta. Se aquele request falhar depois do claim, `devolver`
    solta o carimbo e o token voltaria vivo e sem revogação. Carimbando todos,
    a ordem de recusas do `carregar` (usado, vencido, revogado) continua
    entregando "já foi usado" a quem usou."""
    result = (
        supabase.table("ouvidoria_setor_tokens")
        .update({"revogado_em": agora.isoformat()})
        .eq("manifestacao_id", manifestacao_id)
        .is_("revogado_em", "null")
        .execute()
    )
    return len(result.data or [])


def carregar(supabase, token: str, agora: dt.datetime) -> dict:
    """Acha o vínculo do token e aplica as regras de recusa.

    Levanta `TokenInvalidoError` (sem linha), `TokenUsadoError` (resposta já
    entrou por ele), `TokenExpiradoError` (passou da validade) ou
    `TokenRevogadoError` (o caso foi acionado em outra área depois).

    A ordem das três recusas é regra: quem já usou o link lê que usou, quem
    perdeu o prazo do link lê que ele venceu, e só quem não caiu em nenhuma das
    duas lê que o caso mudou de área. A revogação não reescreve a história de
    ninguém."""
    result = (
        supabase.table("ouvidoria_setor_tokens")
        # `revogado_em` entra na MESMA tupla das outras marcas: a guarda abaixo
        # lê o que este `select` trouxer, e coluna de fora chega como None para
        # sempre, deixando passar em silêncio com a chamada no lugar certo.
        .select("id, manifestacao_id, destinatario_nome, destinatario_email, expira_em, usado_em, revogado_em")
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
    if vinculo.get("revogado_em"):
        raise TokenRevogadoError()
    return vinculo


def consumir(supabase, vinculo: dict, agora: dt.datetime) -> bool:
    """Claim atômico do uso único: só quem preencher `usado_em` primeiro leva.

    Devolve False quando outra requisição já consumiu o token (a idempotência
    do critério 6: responder duas vezes não duplica nada), e também quando a
    revogação passou entre o `carregar` e este UPDATE: sem `revogado_em` no
    filtro, a resposta em voo da área ANTIGA gravaria o T2 de um caso que o
    ouvidor acabou de mandar para outra área, com o link já derrubado."""
    result = (
        supabase.table("ouvidoria_setor_tokens")
        .update({"usado_em": agora.isoformat()})
        .eq("id", vinculo["id"])
        .is_("usado_em", "null")
        .is_("revogado_em", "null")
        .execute()
    )
    return bool(result.data)


def devolver(supabase, vinculo: dict, carimbo: str) -> None:
    """Solta o claim quando a resposta falhou depois dele: o titular pode
    tentar de novo pelo mesmo link, em vez de ficar trancado para fora.

    `carimbo` é obrigatório e restringe a devolução ao claim DESTE request
    (issue #509): sem ele a devolução seria cega, e cega é o bug. O
    timeout de leitura não prova que o UPDATE do `consumir` não commitou, e
    soltar às cegas atropelaria o claim de quem entrou primeiro. Filtrando pelo
    `usado_em` que este request gravou não há corrida: se o claim não entrou,
    casa zero linhas; se entrou por outra requisição, o instante é outro.

    O token revogado no meio do caminho não volta a valer: soltar o claim dele
    devolveria à área ANTIGA um link vivo, que é o contrário do que a revogação
    acabou de decidir. Ele fica com o carimbo de uso, e a área lê que o link já
    foi usado, o que é verdade: ela mesma o usou."""
    (
        supabase.table("ouvidoria_setor_tokens")
        .update({"usado_em": None})
        .eq("id", vinculo["id"])
        .eq("usado_em", carimbo)
        .is_("revogado_em", "null")
        .execute()
    )
