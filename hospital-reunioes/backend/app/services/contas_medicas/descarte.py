"""Descartar um envio em Contas médicas (issue #1338, PRD #1335).

A conta em Erro ou Aguardando arquivo que não vale mais sai da lista: a linha
sai do banco e os PDFs dela saem do bucket na hora, sem esperar os 7 dias da
retenção. O prontuário é do atendimento, e só sai quando nenhuma outra conta
do atendimento sobra para usar ele.

O custo da IA fica: a chamada em `cm_chamada_ia` perde a conta pelo
`ON DELETE SET NULL` da migration 117 e continua gravada.

Pode quem enviou a conta e quem tem o Painel completo. Conta processando, com
Guia ou concluída é recusada. Mandar o mesmo atendimento depois cria uma conta
nova, porque a antiga não existe mais.
"""

from __future__ import annotations

from app.services.contas_medicas.fila import quem_enviou, ve_todas
from app.services.contas_medicas_retencao import tirar_do_bucket

DESCARTAVEIS = ("ERRO", "AGUARDANDO_ARQUIVO")

MENSAGEM_SITUACAO = "Só a conta em Erro ou aguardando arquivo pode ser descartada."
MENSAGEM_COM_GUIA = "A conta já tem Guia e não pode ser descartada."


class ContaNaoEncontradaError(LookupError):
    """A conta não existe."""


class SemPermissaoDeDescartarError(PermissionError):
    """A pessoa não enviou a conta e não tem o Painel completo."""


class NaoDescartavelError(ValueError):
    """A conta não está numa situação que se descarta; `args[0]` é a frase."""


def pode_descartar(conta: dict, linhas_do_guia: list[dict]) -> bool:
    """A situação permite e o Guia ainda não existe. Quem pode é outra
    pergunta, que a lista já responde ao mostrar só os envios da pessoa."""
    return conta.get("situacao") in DESCARTAVEIS and not linhas_do_guia


def descartar(supabase, conta_id: str, me: dict) -> None:
    contas = supabase.table("cm_conta").select("*").eq("id", conta_id).limit(1).execute().data or []
    if not contas:
        raise ContaNaoEncontradaError(conta_id)
    conta = contas[0]
    if not ve_todas(me) and quem_enviou(supabase, [conta]).get(conta["id"]) != me.get("id"):
        raise SemPermissaoDeDescartarError(conta_id)
    if conta.get("situacao") not in DESCARTAVEIS:
        raise NaoDescartavelError(MENSAGEM_SITUACAO)
    linhas = supabase.table("cm_guia_linha").select("id").eq("conta_id", conta_id).limit(1).execute().data or []
    if linhas:
        raise NaoDescartavelError(MENSAGEM_COM_GUIA)

    # A mesma guarda da situação no DELETE: a conta que o Prontuário acabou de
    # liberar para a fila não é apagada no meio da análise.
    apagadas = (
        supabase.table("cm_conta").delete().eq("id", conta_id).in_("situacao", list(DESCARTAVEIS)).execute().data or []
    )
    if not apagadas:
        raise NaoDescartavelError(MENSAGEM_SITUACAO)

    _apagar_arquivos(supabase, _arquivos_que_saem(supabase, conta))


def _arquivos_que_saem(supabase, conta: dict) -> list[dict]:
    """O PDF da conta e, se nenhuma outra conta do atendimento sobrou, os
    prontuários do atendimento."""
    arquivos = []
    if conta.get("arquivo_id"):
        arquivos += supabase.table("cm_arquivo").select("*").eq("id", conta["arquivo_id"]).execute().data or []
    outras = (
        supabase.table("cm_conta").select("id").eq("atendimento_id", conta["atendimento_id"]).limit(1).execute().data
        or []
    )
    if not outras:
        arquivos += (
            supabase.table("cm_arquivo")
            .select("*")
            .eq("atendimento_id", conta["atendimento_id"])
            .eq("tipo", "PRONTUARIO")
            .execute()
            .data
            or []
        )
    return arquivos


def _apagar_arquivos(supabase, arquivos: list[dict]) -> None:
    """Tira do bucket o PDF e o texto ao lado, e a linha do banco. O que o
    Storage recusar fica com a linha, e a retenção dos 7 dias leva depois."""
    for arquivo in arquivos:
        if tirar_do_bucket(supabase, arquivo.get("chave_bucket")) is None:
            continue
        supabase.table("cm_arquivo").delete().eq("id", arquivo["id"]).execute()
