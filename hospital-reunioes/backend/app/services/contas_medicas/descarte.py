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

from app.services.contas_medicas.fila import ve_todas
from app.services.contas_medicas_retencao import tirar_do_bucket

DESCARTAVEIS = ("ERRO", "AGUARDANDO_ARQUIVO")

MENSAGEM_SITUACAO = "Só a conta em Erro ou aguardando arquivo pode ser descartada."
MENSAGEM_COM_GUIA = "A conta já tem Guia e não pode ser descartada."
MENSAGEM_SEM_PERMISSAO = "Só quem enviou a conta ou a gestão pode descartar."
MENSAGEM_POSSE_AMBIGUA = "Mais de uma pessoa enviou o prontuário deste atendimento. Peça à gestão para descartar."


class ContaNaoEncontradaError(LookupError):
    """A conta não existe."""


class SemPermissaoDeDescartarError(PermissionError):
    """A pessoa não enviou a conta e não tem o Painel completo; `args[0]` é a frase."""


class NaoDescartavelError(ValueError):
    """A conta não está numa situação que se descarta; `args[0]` é a frase."""


def pode_descartar(conta: dict, linhas_do_guia: list[dict]) -> bool:
    """A situação permite, o Guia ainda não existe e a posse não é ambígua.
    A lista só mostra à pessoa os envios dela; a posse ambígua vem marcada em
    `so_a_gestao_descarta` por `envios_da_pessoa`, com a regra de `_conferir_posse`."""
    return conta.get("situacao") in DESCARTAVEIS and not linhas_do_guia and not conta.get("so_a_gestao_descarta")


def descartar(supabase, conta_id: str, me: dict) -> None:
    contas = supabase.table("cm_conta").select("*").eq("id", conta_id).limit(1).execute().data or []
    if not contas:
        raise ContaNaoEncontradaError(conta_id)
    conta = contas[0]
    gestao = ve_todas(me)
    da_conta = _arquivos(supabase, id=conta["arquivo_id"]) if conta.get("arquivo_id") else []
    prontuarios = _arquivos(supabase, atendimento_id=conta["atendimento_id"], tipo="PRONTUARIO")
    remetente = _remetentes(supabase, da_conta + prontuarios)
    if not gestao:
        _conferir_posse(da_conta, prontuarios, remetente, me.get("id"))
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

    outras = (
        supabase.table("cm_conta").select("id").eq("atendimento_id", conta["atendimento_id"]).limit(1).execute().data
        or []
    )
    # O prontuário só sai sem outra conta do atendimento para usar ele. Quem
    # não é gestão só apaga o que ela mesma enviou: o prontuário de outra
    # pessoa fica para a retenção dos 7 dias.
    sai = [] if outras else [p for p in prontuarios if gestao or remetente.get(p["id"]) == me.get("id")]
    _apagar_arquivos(supabase, da_conta + sai)


def _arquivos(supabase, **filtros) -> list[dict]:
    consulta = supabase.table("cm_arquivo").select("*")
    for coluna, valor in filtros.items():
        consulta = consulta.eq(coluna, valor)
    return consulta.execute().data or []


def _remetentes(supabase, arquivos: list[dict]) -> dict[str, str | None]:
    """Quem enviou cada arquivo: o `usuario_id` do envio dele."""
    ids = list({a["envio_id"] for a in arquivos if a.get("envio_id")})
    if not ids:
        return {}
    envios = supabase.table("cm_envio").select("id, usuario_id").in_("id", ids).execute().data or []
    usuario = {e["id"]: e.get("usuario_id") for e in envios}
    return {a["id"]: usuario.get(a.get("envio_id")) for a in arquivos}


def _conferir_posse(da_conta: list[dict], prontuarios: list[dict], remetente: dict, pessoa_id: str | None) -> None:
    """A conta é de quem enviou o PDF dela. A conta à espera da Conta não tem
    PDF: é de quem enviou o prontuário, e se mais de uma pessoa enviou
    prontuário do atendimento, a posse é ambígua e só a gestão descarta."""
    if da_conta:
        dono = remetente.get(da_conta[0]["id"])
    else:
        donos = {remetente.get(p["id"]) for p in prontuarios}
        if len(donos) > 1:
            raise SemPermissaoDeDescartarError(MENSAGEM_POSSE_AMBIGUA)
        dono = next(iter(donos), None)
    if dono is None or dono != pessoa_id:
        raise SemPermissaoDeDescartarError(MENSAGEM_SEM_PERMISSAO)


def _apagar_arquivos(supabase, arquivos: list[dict]) -> None:
    """Tira do bucket o PDF e o texto ao lado, e a linha do banco. O que o
    Storage recusar fica com a linha, e a retenção dos 7 dias leva depois."""
    for arquivo in arquivos:
        if tirar_do_bucket(supabase, arquivo.get("chave_bucket")) is None:
            continue
        supabase.table("cm_arquivo").delete().eq("id", arquivo["id"]).execute()
