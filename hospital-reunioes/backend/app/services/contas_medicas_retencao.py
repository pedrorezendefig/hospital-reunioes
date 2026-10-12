"""Retenção de 7 dias dos PDFs de Contas médicas (issue #1125, PRD #1113, ADR 0070).

O PDF enviado (conta ou prontuário) vive no bucket privado `contas-medicas` só
até `apagar_em` (envio + 7 dias). Vencido o prazo, o job diário do cron tira do
bucket o PDF e o texto extraído guardado ao lado dele, e carimba `apagado_em`
na linha de `cm_arquivo`, que fica. Depois disso sobra só o que o módulo já
estruturou e desidentificou (`cm_eventos`, `cm_conta_item`, `cm_guia_linha`
com o trecho curto de evidência), e nada disso é tocado aqui.

Mesmo padrão do expurgo da Ouvidoria (`ouvidoria_retencao`): a lógica vive
aqui, testável com um Supabase falso, e o scheduler só carrega o relógio.

O arquivo é dado pessoal sensível: nada daqui vai para log além de contagens.
Nem chave do bucket, nem número do atendimento, nem mensagem de exceção (que
pode trazer o caminho).
"""

from __future__ import annotations

import dataclasses
import datetime as dt

# O bucket da migration 116. Constante e não env var: o nome nasce na
# migration, e um ambiente com outro nome seria outro schema.
BUCKET = "contas-medicas"

# Teto de arquivos por rodada: o dia em que a fila acumular não pode virar uma
# varredura infinita segurando o scheduler. O que sobrar sai na rodada seguinte.
LOTE_POR_RODADA = 500

# O texto extraído do PDF fica no bucket ao lado dele, com a mesma chave e o
# sufixo abaixo. Quem grava (o envio) e quem apaga (esta retenção) usam esta
# mesma função: em lugares separados, mudar a convenção de um lado deixaria o
# texto do prontuário no bucket para sempre, em silêncio.
SUFIXO_DO_TEXTO = ".txt"


def chave_do_texto(chave_bucket: str) -> str:
    """A chave do texto extraído guardado ao lado do PDF."""
    return f"{chave_bucket}{SUFIXO_DO_TEXTO}"


@dataclasses.dataclass(frozen=True)
class Rodada:
    """O que uma passagem do job fez, só em contagens.

    `apagados`: saiu algo do bucket e a linha ganhou o carimbo.
    `ausentes`: o bucket já não tinha nada, e a linha ganhou o carimbo mesmo
    assim (sem isso, ela voltaria à varredura todo dia para sempre).
    `falhas`: o Storage recusou ou estava fora do ar; a linha fica sem carimbo
    e volta na rodada seguinte."""

    apagados: int = 0
    ausentes: int = 0
    falhas: int = 0


def apagar_arquivos_vencidos(supabase, agora: dt.datetime) -> Rodada:
    """Tira do bucket todo arquivo com `apagar_em` vencido e sem `apagado_em`,
    e carimba `apagado_em`. Idempotente: o carimbo tira a linha da varredura."""
    vencidos = (
        supabase.table("cm_arquivo")
        .select("id, chave_bucket")
        .is_("apagado_em", "null")
        .lte("apagar_em", agora.isoformat())
        .order("apagar_em")
        .limit(LOTE_POR_RODADA)
        .execute()
        .data
        or []
    )

    apagados = ausentes = falhas = 0
    for arquivo in vencidos:
        saiu = _tirar_do_bucket(supabase, arquivo.get("chave_bucket"))
        if saiu is None:
            falhas += 1
            continue
        # A mesma guarda da varredura no UPDATE: uma rodada concorrente que
        # carimbou antes não tem o carimbo dela sobrescrito.
        supabase.table("cm_arquivo").update({"apagado_em": agora.isoformat()}).eq("id", arquivo["id"]).is_(
            "apagado_em", "null"
        ).execute()
        if saiu:
            apagados += 1
        else:
            ausentes += 1
    return Rodada(apagados=apagados, ausentes=ausentes, falhas=falhas)


def _tirar_do_bucket(supabase, chave_bucket: str | None) -> bool | None:
    """Remove o PDF e o texto ao lado. Devolve True se algo saiu, False se o
    bucket já não tinha nenhum dos dois, e None se o Storage falhou.

    Não usa `storage.delete_file`: ele lê "nada casou" como falha, e aqui
    arquivo que já não existe é caso normal, que precisa do carimbo. A
    distinção vem do corpo da resposta: o Storage lista o que saiu, marca com
    `error` o que recusou e omite o que não existia."""
    if not chave_bucket:
        return False
    try:
        resposta = supabase.storage.from_(BUCKET).remove([chave_bucket, chave_do_texto(chave_bucket)])
    except Exception:
        return None
    if not isinstance(resposta, list):
        return None
    for item in resposta:
        if not isinstance(item, dict) or item.get("error"):
            return None
    return bool(resposta)
