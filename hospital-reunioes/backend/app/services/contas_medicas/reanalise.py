"""Analisar de novo a conta em Erro sem anexar o PDF (issue #1339, PRD #1335).

A conta em Erro cuja ação, pelo Código do erro, é Analisar de novo (a IA, a
configuração, o app e o `CM-IA-ANTIGO`) volta para a fila com um clique, desde
que os PDFs dela ainda estejam no bucket: o da conta e um prontuário do
atendimento, os dois sem `apagado_em` e antes do `apagar_em` (o job da
retenção roda uma vez por dia, e o PDF vencido pode sair no meio da análise).

O PDF que saiu do sistema, ou o erro que está no próprio PDF, fica com Enviar
de novo: o cartão mostra esse botão e a rota recusa com a frase.

Pode quem enviou a conta e quem tem o Painel completo, a mesma regra do
descarte.

Analisar assim mesmo (issue #1401, PRD #1397): a conta parada em
`CM-ARQ-DIGITALIZADO` volta para a fila com as mesmas guardas e uma marca que
faz a análise pular o bloqueio das folhas digitalizadas e seguir com a
ressalva "Confira à mão" no Parecer parcial. A marca mora em `faltantes`, que
já guarda o que não é coluna (o tempo das etapas, o reenvio), e é o id do
prontuário da análise: o prontuário novo do atendimento é outro arquivo, e a
marca deixa de valer sozinha.
"""

from __future__ import annotations

from datetime import datetime

from app.services.contas_medicas.erro_da_conta import (
    ANALISAR_DE_NOVO,
    CATALOGO,
    ENVIAR_DE_NOVO,
    Acao,
    acao_do_codigo,
)
from app.services.contas_medicas.fila import ve_todas

MENSAGEM_SEM_PERMISSAO = "Só quem enviou a conta ou a gestão pode analisar de novo."
MENSAGEM_FORA_DO_ERRO = "Só a conta em Erro pode ser analisada de novo."
MENSAGEM_ERRO_DO_ARQUIVO = "O problema está no PDF. Envie o arquivo de novo."
MENSAGEM_VENCIDO = f"{CATALOGO['vencido'].frase} Envie de novo."
MENSAGEM_SEM_PERMISSAO_ASSIM_MESMO = "Só quem enviou a conta ou a gestão pode analisar assim mesmo."
MENSAGEM_SO_DIGITALIZADO = "Analisar assim mesmo é só para a conta parada por folha digitalizada que não deu para ler."

# O Erro das folhas digitalizadas que sustentam a conta (#1400) e a marca que o pula.
DIGITALIZADO = CATALOGO["digitalizadas_ilegiveis"].codigo
MARCA_ASSIM_MESMO = "analisar_assim_mesmo"


class ContaNaoEncontradaError(LookupError):
    """A conta não existe."""


class SemPermissaoError(PermissionError):
    """A pessoa não enviou a conta e não tem o Painel completo."""


class NaoAnalisavelError(ValueError):
    """A conta não volta para a fila sem um PDF novo; `args[0]` é a frase."""


def _guardado(arquivo: dict, agora: datetime) -> bool:
    apagar_em = arquivo.get("apagar_em")
    if arquivo.get("apagado_em") is not None or not apagar_em:
        return False
    return datetime.fromisoformat(str(apagar_em)) > agora


def com_pdf_guardado(supabase, contas: list[dict], agora: datetime) -> set[str]:
    """As contas cujo PDF da conta e algum prontuário do atendimento ainda
    estão no bucket."""
    contas = [c for c in contas if c.get("arquivo_id")]
    if not contas:
        return set()
    da_conta = (
        supabase.table("cm_arquivo").select("*").in_("id", list({c["arquivo_id"] for c in contas})).execute().data or []
    )
    prontuarios = (
        supabase.table("cm_arquivo")
        .select("*")
        .in_("atendimento_id", list({c["atendimento_id"] for c in contas}))
        .eq("tipo", "PRONTUARIO")
        .execute()
        .data
        or []
    )
    contas_guardadas = {a["id"] for a in da_conta if _guardado(a, agora)}
    atendimentos_guardados = {p["atendimento_id"] for p in prontuarios if _guardado(p, agora)}
    return {
        c["id"] for c in contas if c["arquivo_id"] in contas_guardadas and c["atendimento_id"] in atendimentos_guardados
    }


def acao_do_cartao(conta: dict, guardado: bool) -> Acao | None:
    """A ação da conta em Erro: a do Código do erro, e Enviar de novo quando
    o PDF já saiu do sistema."""
    acao = acao_do_codigo(conta.get("erro_codigo"))
    if acao == ANALISAR_DE_NOVO and not guardado:
        return ENVIAR_DE_NOVO
    return acao


def pode_analisar_assim_mesmo(conta: dict, guardado: bool) -> bool:
    """O botão Analisar assim mesmo do cartão: a conta em Erro por folha
    digitalizada, com os PDFs ainda no sistema."""
    return conta.get("situacao") == "ERRO" and conta.get("erro_codigo") == DIGITALIZADO and guardado


def marca_assim_mesmo(conta: dict) -> str | None:
    """O id do prontuário com que a pessoa mandou analisar assim mesmo, ou None."""
    faltantes = conta.get("faltantes")
    return faltantes.get(MARCA_ASSIM_MESMO) if isinstance(faltantes, dict) else None


def _quem_enviou(supabase, conta: dict) -> str | None:
    """O `cm_envio.usuario_id` do PDF da conta."""
    if not conta.get("arquivo_id"):
        return None
    arquivos = supabase.table("cm_arquivo").select("envio_id").eq("id", conta["arquivo_id"]).execute().data or []
    envio_id = arquivos[0].get("envio_id") if arquivos else None
    if not envio_id:
        return None
    envios = supabase.table("cm_envio").select("usuario_id").eq("id", envio_id).execute().data or []
    return envios[0].get("usuario_id") if envios else None


def _conta_da_pessoa(supabase, conta_id: str, me: dict, sem_permissao: str) -> dict:
    contas = supabase.table("cm_conta").select("*").eq("id", conta_id).limit(1).execute().data or []
    if not contas:
        raise ContaNaoEncontradaError(conta_id)
    conta = contas[0]
    if not ve_todas(me) and _quem_enviou(supabase, conta) != me.get("id"):
        raise SemPermissaoError(sem_permissao)
    if conta.get("situacao") != "ERRO":
        raise NaoAnalisavelError(MENSAGEM_FORA_DO_ERRO)
    return conta


def _de_volta_para_a_fila(supabase, conta_id: str, campos: dict | None = None) -> None:
    """A conta na fila com as tentativas zeradas e o Erro limpo, com a mesma
    guarda da situação no UPDATE: duas abas que clicam juntas põem a conta na
    fila uma vez só."""
    voltou = (
        supabase.table("cm_conta")
        .update(
            {
                "situacao": "NA_FILA",
                "tentativas": 0,
                "erro_motivo": None,
                "erro_codigo": None,
                "erro_detalhe": None,
                "processando_desde": None,
                **(campos or {}),
            }
        )
        .eq("id", conta_id)
        .eq("situacao", "ERRO")
        .execute()
        .data
        or []
    )
    if not voltou:
        raise NaoAnalisavelError(MENSAGEM_FORA_DO_ERRO)


def analisar_de_novo(supabase, conta_id: str, me: dict, agora: datetime) -> None:
    """A conta volta para a fila com as tentativas zeradas e o Erro limpo."""
    conta = _conta_da_pessoa(supabase, conta_id, me, MENSAGEM_SEM_PERMISSAO)
    if acao_do_codigo(conta.get("erro_codigo")) != ANALISAR_DE_NOVO:
        raise NaoAnalisavelError(MENSAGEM_ERRO_DO_ARQUIVO)
    if conta_id not in com_pdf_guardado(supabase, [conta], agora):
        raise NaoAnalisavelError(MENSAGEM_VENCIDO)
    _de_volta_para_a_fila(supabase, conta_id)


def analisar_assim_mesmo(supabase, conta_id: str, me: dict, agora: datetime) -> None:
    """A conta em `CM-ARQ-DIGITALIZADO` volta para a fila com a marca no
    prontuário da análise: a próxima análise não para nas folhas digitalizadas."""
    conta = _conta_da_pessoa(supabase, conta_id, me, MENSAGEM_SEM_PERMISSAO_ASSIM_MESMO)
    if conta.get("erro_codigo") != DIGITALIZADO:
        raise NaoAnalisavelError(MENSAGEM_SO_DIGITALIZADO)
    if conta_id not in com_pdf_guardado(supabase, [conta], agora):
        raise NaoAnalisavelError(MENSAGEM_VENCIDO)
    faltantes = conta.get("faltantes")
    guardado = dict(faltantes) if isinstance(faltantes, dict) else {"itens": faltantes or []}
    guardado[MARCA_ASSIM_MESMO] = prontuario_da_analise(supabase, conta["atendimento_id"])["id"]
    _de_volta_para_a_fila(supabase, conta_id, {"faltantes": guardado})


def prontuario_da_analise(supabase, atendimento_id: str) -> dict | None:
    """O prontuário que a análise lê: o mais novo do atendimento ainda no bucket."""
    achados = (
        supabase.table("cm_arquivo")
        .select("*")
        .eq("atendimento_id", atendimento_id)
        .eq("tipo", "PRONTUARIO")
        .is_("apagado_em", "null")
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return achados[0] if achados else None
