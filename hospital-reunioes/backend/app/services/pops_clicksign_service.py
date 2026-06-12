"""Orquestrador ClickSign do contexto POPs (issue #87, PRD #76).

A aprovação do Validador (EM_ASSINATURA) dispara o envio automático:
Envelope com o PDF institucional e 3 Signatários nomeados por papel —
Elaborador, Revisor e Validador — que assinam pelos emails da própria
ClickSign. Reusa os primitivos de app.services.clicksign_service (envelope,
documento, signatário, requisitos, ativação, notificação).

Falha parcial: nada persiste até o Envelope estar ativado — a Versão fica
EM_ASSINATURA re-tentável e o reenvio cria um Envelope novo (o anterior,
se houver, morre como rascunho órfão no ClickSign, como no fluxo de Atas).
Com envio anterior OK (envelope_id gravado), reenvio é no-op idempotente.
"""

from __future__ import annotations

import logging

from app.services import audit, clicksign_service, pops_pdf_service

logger = logging.getLogger(__name__)

# Ordem institucional das assinaturas (DRF §4.2): quem fez, quem revisou,
# quem validou. A mesma pessoa em dois papéis assina uma única vez.
PAPEIS_SIGNATARIOS: tuple[str, ...] = ("elaborador_id", "revisor_id", "validador_id")


def _signatarios_do_pop(supabase, pop: dict) -> list[dict] | None:
    """Os designados do POP na ordem dos papéis, deduplicados por pessoa.

    None se algum designado estiver sem cadastro ou sem email — sem os 3
    papéis cobertos não há Envelope válido (o envio fica re-tentável após
    correção do cadastro).
    """
    ids_na_ordem: list[str] = []
    for papel in PAPEIS_SIGNATARIOS:
        pid = pop.get(papel)
        if pid and pid not in ids_na_ordem:
            ids_na_ordem.append(pid)

    result = supabase.table("participantes").select("id, nome_completo, email").in_("id", ids_na_ordem).execute()
    por_id = {row["id"]: row for row in (result.data or [])}

    signatarios = []
    for pid in ids_na_ordem:
        pessoa = por_id.get(pid)
        if not pessoa or not pessoa.get("email"):
            logger.error(f"[POPs ClickSign] Designado {pid} do POP {pop.get('codigo')} sem cadastro/email — abortando")
            return None
        signatarios.append(pessoa)
    return signatarios


def enviar_para_assinatura(
    supabase, pop: dict, setor: dict, versao: dict, *, actor: dict | None = None, request=None
) -> dict | None:
    """Monta e ativa o Envelope da Versão (PDF institucional + Signatários).

    Retorna a Versão com envelope_id/key persistidos, ou None em falha —
    o estado EM_ASSINATURA não se desfaz e o reenvio re-tenta do zero.
    Idempotente: Versão com Envelope já gravado retorna sem duplicar.
    """
    if versao.get("envelope_id_clicksign"):
        logger.info(
            f"[POPs ClickSign] Versão {versao.get('id')} já tem Envelope "
            f"{versao.get('envelope_id_clicksign')} — envio não duplicado"
        )
        return versao

    try:
        signatarios = _signatarios_do_pop(supabase, pop)
        if not signatarios:
            return None

        # PDF institucional gerado do rascunho persistido (estado da Versão
        # já EM_ASSINATURA); nome do arquivo e do Envelope seguem a
        # nomenclatura travada do DRF §3.3.
        nomes_designados = {p["id"]: p.get("nome_completo") for p in signatarios}
        pdf_bytes = pops_pdf_service.gerar_pdf_pop(
            pop=pop, setor=setor, versao=versao, nomes_designados=nomes_designados
        )
        nome_arquivo = pops_pdf_service.nome_arquivo_pop(
            codigo=pop["codigo"], nome=pop["nome"], numero_versao=versao["numero_versao"]
        )

        envelope_id = clicksign_service.create_envelope(nome_arquivo.removesuffix(".pdf"))
        if not envelope_id:
            return None

        document_id = clicksign_service.add_document(envelope_id, pdf_bytes, nome_arquivo)
        if not document_id:
            return None

        for pessoa in signatarios:
            signer_id = clicksign_service.add_signer(envelope_id, nome=pessoa["nome_completo"], email=pessoa["email"])
            if not signer_id:
                return None
            if not clicksign_service.create_qualification_requirement(envelope_id, document_id, signer_id):
                return None
            if not clicksign_service.create_auth_requirement(envelope_id, document_id, signer_id):
                return None

        if not clicksign_service.activate_envelope(envelope_id):
            return None

        # Best-effort (como nas Atas): a ClickSign também notifica por conta
        # própria; falha aqui não derruba um Envelope já ativo.
        clicksign_service.notify_signers(envelope_id)

        supabase.table("pops_versoes").update(
            {
                "envelope_id_clicksign": envelope_id,  # consultas e PDF assinado (API v3)
                "envelope_key_clicksign": document_id,  # webhook envia em document.key
            }
        ).eq("id", versao["id"]).execute()

        audit.log_action(
            supabase,
            actor=actor,
            action="POPS_ENVIAR_ASSINATURA",
            target_type="pop_versao",
            target_id=versao["id"],
            metadata={
                "pop_id": versao.get("pop_id"),
                "envelope_id": envelope_id,
                "document_id": document_id,
                "signatarios": [p["email"] for p in signatarios],
            },
            request=request,
        )

        logger.info(
            f"[POPs ClickSign] Envelope {envelope_id} ativado para o POP {pop.get('codigo')} "
            f"v{versao.get('numero_versao')} com {len(signatarios)} signatários"
        )
        return {**versao, "envelope_id_clicksign": envelope_id, "envelope_key_clicksign": document_id}

    except Exception as e:  # noqa: BLE001 — falha de envio nunca desfaz a aprovação
        logger.error(f"[POPs ClickSign] Erro no envio do POP {pop.get('codigo')}: {e}", exc_info=True)
        return None
