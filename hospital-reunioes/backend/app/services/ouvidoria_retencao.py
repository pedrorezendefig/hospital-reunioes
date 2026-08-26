"""Retenção da Ouvidoria: anonimização após cinco anos (issue #343, ADR 0034).

A manifestação encerrada há mais de cinco anos perde o Dossiê e vira estatística.
O que sai é o que identifica ou narra o caso; o que fica é o que os relatórios
contam. A separação é explícita de propósito: uma anonimização por lista de
exclusão erra sempre que uma coluna nova nasce, então aqui a lista é a das
colunas que SAEM, e cada coluna nova precisa de uma decisão consciente.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio; aqui
vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.config import settings
from app.services import storage

logger = logging.getLogger(__name__)

ENCERRADO = "encerrado"

# O prazo de retenção da ADR 0034: cinco anos contados do encerramento (T3).
ANOS_DE_RETENCAO = 5

# Teto de casos por rodada. O job roda uma vez por dia e nasce dormindo (nenhum
# caso tem cinco anos ainda), mas o dia em que a fila acumular não pode virar
# uma varredura infinita segurando o scheduler.
LOTE_POR_RODADA = 100

# O Dossiê: o que a retenção apaga. Cada campo é texto livre sobre o caso ou
# identificação de quem manifestou.
CAMPOS_DO_DOSSIE: dict[str, str | None] = {
    "relato_integral": None,
    "manifestante_nome": None,
    "manifestante_contato": None,
    # Cópias e derivados do relato, espalhados pela tramitação.
    "extrato_para_o_setor": None,
    "resposta_da_area": None,
    "desfecho_descricao": None,
    "classificacao_ia": None,
    # Ponte para a conversa da Ana, onde o relato original continua inteiro.
    "conversa_id": "",
}

# `resumo` é NOT NULL com CHECK anti-vazio desde a migration 063: não pode ir a
# NULL, então vira marcador. O texto some do mesmo jeito.
RESUMO_ANONIMIZADO = "[anonimizado pela retenção]"

# O que fica, e por quê: é disto que o módulo de métricas tira volume, prazo
# cumprido, ranking por área e reincidência. A lista não é usada pelo código
# (o update só toca no Dossiê); ela existe para o teste de retenção afirmar,
# campo a campo, o que a anonimização não pode ter mexido.
CAMPOS_ESTATISTICOS: tuple[str, ...] = (
    "numero",
    "protocolo",
    "status",
    "data_abertura",
    "contato_em",
    "validada_em",
    "respondida_em",
    "encerrada_em",
    "prazo_area_em",
    "tipo_manifestacao",
    "categoria",
    "setor",
    "gravidade",
    "canal",
    "desfecho",
    "minutos_pausados",
    "reincidencia",
    "anonimo",
    "sigilo_reforcado",
    "manifestante_vinculo",
)

# O que o job precisa do caso para decidir e anonimizar.
_CAMPOS_DA_RETENCAO = "id, protocolo, status, encerrada_em, anonimizada_em"


def data_de_corte(agora: dt.datetime) -> dt.datetime:
    """O instante a partir do qual o encerramento ainda está dentro da retenção.

    Encerramento anterior ou igual ao corte já passou dos cinco anos. Feito por
    subtração de ano (não por 365 dias) para o aniversário cair no mesmo dia;
    29 de fevereiro recua para 28."""
    try:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO)
    except ValueError:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO, day=28)


def anonimizar_encerradas_antigas(supabase, agora: dt.datetime) -> int:
    """Anonimiza as manifestações encerradas há mais de cinco anos.

    Devolve quantas foram anonimizadas nesta rodada."""
    corte = data_de_corte(agora)
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DA_RETENCAO)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            # Caso com `encerrada_em` nulo (encerrado antes do marco T3 existir)
            # fica de fora: sem saber quando fechou, não dá para dizer que os
            # cinco anos passaram.
            .lte("encerrada_em", corte.isoformat())
            .order("encerrada_em")
            .limit(LOTE_POR_RODADA)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos encerrados para a retenção")
        return 0

    anonimizadas = 0
    for caso in result.data or []:
        if _anonimizar_caso(supabase, caso, agora):
            anonimizadas += 1
    return anonimizadas


def _anonimizar_caso(supabase, caso: dict, agora: dt.datetime) -> bool:
    """Apaga anexos e Dossiê de um caso e registra o ato na trilha.

    Os anexos saem ANTES do carimbo de propósito: um carimbo colocado primeiro
    e uma falha logo depois deixariam o caso marcado como anonimizado com a
    evidência (foto, áudio, documento) ainda no bucket, e nenhuma rodada
    seguinte voltaria nele. Nesta ordem, a falha só custa uma repetição."""
    if not _apagar_anexos(supabase, caso["id"]):
        return False
    if not _apagar_dossie(supabase, caso["id"], agora):
        return False
    _registrar_movimento(supabase, caso["id"])
    return True


def _apagar_anexos(supabase, manifestacao_id: str) -> bool:
    """Remove o binário do bucket e depois os metadados do caso.

    Binário primeiro: a linha é o único ponteiro para o arquivo, e apagá-la
    antes deixaria o arquivo órfão no bucket para sempre. Se alguma remoção
    falhar, nada é apagado do banco e a rodada seguinte tenta de novo."""
    try:
        result = (
            supabase.table("ouvidoria_anexos")
            .select("id, storage_path")
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao listar os anexos do caso %s para a retenção", manifestacao_id)
        return False

    anexos = result.data or []
    for anexo in anexos:
        caminho = anexo.get("storage_path")
        if not caminho:
            continue
        if not storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, caminho):
            logger.error("[Ouvidoria] Falha ao remover o anexo %s do bucket; retenção adiada", caminho)
            return False

    if not anexos:
        return True
    try:
        supabase.table("ouvidoria_anexos").delete().eq("manifestacao_id", manifestacao_id).execute()
    except Exception:
        logger.error("[Ouvidoria] Falha ao apagar os metadados dos anexos do caso %s", manifestacao_id)
        return False
    return True


def _registrar_movimento(supabase, manifestacao_id: str) -> None:
    """O ato entra na trilha do caso. Não é transição de estado (o caso segue
    encerrado), então o insert é direto, no molde do movimento de prazo
    rompido. O carimbo `anonimizada_em` garante a vez única.

    A observação não cita nada do Dossiê: a trilha é imutável, e um nome
    escrito aqui seria dado pessoal que a retenção nunca mais apagaria."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "estado_anterior": ENCERRADO,
                "estado_novo": ENCERRADO,
                "autor_id": None,
                "autor_nome": "Sistema (retenção)",
                "observacao": (
                    f"Manifestação anonimizada pela política de retenção de {ANOS_DE_RETENCAO} anos: "
                    "relato, identificação do manifestante e anexos apagados. "
                    "Os campos estatísticos do caso foram preservados."
                ),
            }
        ).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao gravar o movimento de anonimização do caso %s", manifestacao_id)


def _apagar_dossie(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    """Zera o Dossiê e carimba a anonimização no mesmo update.

    O update é condicional (`anonimizada_em IS NULL`): a segunda rodada do job,
    ou uma rodada concorrente, não acha caso para anonimizar e não repete o
    ato."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update(dict(CAMPOS_DO_DOSSIE) | {"resumo": RESUMO_ANONIMIZADO, "anonimizada_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao apagar o Dossiê do caso %s", manifestacao_id)
        return False
    return bool(result.data)
