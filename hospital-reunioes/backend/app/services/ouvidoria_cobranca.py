"""Cobrança de prazo rompido da Ouvidoria (issue #327, ADR 0034 decisão 7).

O degrau do vencimento: um job periódico varre os casos aguardando área, acha
os prazos vencidos pelo motor de prazos e cobra titular e substituto do setor.
A escada completa de escalonamento (véspera, gestor, Diretoria) é do PRD #318.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio e os
feriados; aqui vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.services.ouvidoria_notificacoes import (
    GATILHO_PRAZO_ROMPIDO,
    despachar_agora_se_puder,
    quando_enviar,
    registrar,
)
from app.services.ouvidoria_prazos import FUSO, esta_vencido
from app.services.ouvidoria_responsaveis import destinatarios_da_cobranca

logger = logging.getLogger(__name__)

AGUARDANDO_AREA = "aguardando_area"

# O que o job precisa do caso para decidir e cobrar. O conteúdo do email sai
# depois, pela projeção fechada do módulo de notificações.
_CAMPOS_DA_COBRANCA = "id, protocolo, setor, gravidade, prazo_area_em, prazo_rompido_em"


def cobrar_prazos_rompidos(supabase, agora: dt.datetime, feriados: frozenset[dt.date]) -> int:
    """Varre os casos aguardando área e cobra os que têm prazo vencido.

    Devolve quantos casos foram cobrados nesta rodada."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DA_COBRANCA)
            .eq("status", AGUARDANDO_AREA)
            .is_("prazo_rompido_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos aguardando área para a cobrança")
        return 0

    cobrados = 0
    for caso in result.data or []:
        bruto = caso.get("prazo_area_em")
        if not bruto:
            continue
        try:
            vencimento = dt.datetime.fromisoformat(str(bruto))
        except ValueError:
            # Um vencimento malformado não pode calar a cobrança dos demais.
            logger.error("[Ouvidoria] Caso %s com prazo_area_em ilegível: %r", caso.get("protocolo"), bruto)
            continue
        if not esta_vencido(vencimento, agora):
            continue
        if not _reivindicar_caso(supabase, caso["id"], agora):
            continue
        if _cobrar_caso(supabase, caso, agora, feriados):
            cobrados += 1
    return cobrados


def _registrar_movimento_de_prazo_rompido(supabase, caso: dict, observacao: str) -> None:
    """O fato entra na trilha do caso: o prazo da área rompeu. Não é transição
    de estado (o caso segue aguardando área), então o insert é direto, no molde
    do movimento de abertura. O carimbo `prazo_rompido_em` garante a vez única."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": caso["id"],
                "estado_anterior": AGUARDANDO_AREA,
                "estado_novo": AGUARDANDO_AREA,
                "autor_id": None,
                "autor_nome": "Sistema (cobrança de prazos)",
                "observacao": observacao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de prazo rompido do caso %s", caso.get("id"))


def _reivindicar_caso(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    """Carimba `prazo_rompido_em` antes de cobrar. O update é condicional
    (`prazo_rompido_em IS NULL`): a segunda rodada do job, ou uma rodada
    concorrente, não acha caso para carimbar e não cobra de novo."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({"prazo_rompido_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", AGUARDANDO_AREA)
            .is_("prazo_rompido_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o prazo rompido do caso %s", manifestacao_id)
        return False
    return bool(result.data)


def _cobrar_caso(supabase, caso: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> bool:
    """Cobra um caso vencido: registra as notificações ao titular e ao
    substituto vigentes e entrega já o que a janela comercial permitir.

    A trilha diz o que de fato aconteceu: com destinatários, a cobrança saiu;
    sem ninguém vigente, o rompimento fica registrado sem afirmar envio (o
    degrau do gestor é do PRD #318)."""
    destinatarios = _carregar_destinatarios(supabase, caso.get("setor") or "", agora)
    if not destinatarios:
        logger.warning(
            "[Ouvidoria] Caso %s com prazo rompido e setor %s sem titular nem substituto vigentes",
            caso.get("protocolo"),
            caso.get("setor"),
        )
        _registrar_movimento_de_prazo_rompido(
            supabase,
            caso,
            "Prazo de resposta da área rompido; setor sem titular nem substituto vigentes para cobrar.",
        )
        return False

    _registrar_movimento_de_prazo_rompido(
        supabase,
        caso,
        "Prazo de resposta da área rompido; cobrança enviada ao titular e ao substituto.",
    )

    quando = quando_enviar(agora, caso.get("gravidade"), feriados)
    for destinatario in destinatarios:
        notificacao = registrar(
            supabase,
            manifestacao_id=caso["id"],
            gatilho=GATILHO_PRAZO_ROMPIDO,
            destinatario_nome=destinatario.nome,
            destinatario_email=destinatario.email,
            papel_destinatario=destinatario.papel,
            enviar_a_partir_de=quando,
        )
        despachar_agora_se_puder(supabase, notificacao, agora, feriados)
    return True


def _carregar_destinatarios(supabase, setor: str, agora: dt.datetime):
    try:
        result = (
            supabase.table("ouvidoria_setor_responsaveis")
            .select("setor, papel, nome, email, vigencia_inicio, vigencia_fim")
            .eq("setor", setor)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carregar os responsáveis do setor %s", setor)
        return []
    return destinatarios_da_cobranca(result.data or [], agora.astimezone(FUSO).date())
