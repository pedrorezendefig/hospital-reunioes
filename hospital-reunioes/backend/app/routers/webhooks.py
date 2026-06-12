import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_supabase_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


# Webhook ClickSign (callback de assinatura)
@router.post("/clicksign")
async def webhook_clicksign(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """
    Recebe notificações da ClickSign sobre fechamento de documentos.

    Eventos tratados: Close (fechamento manual) e AutoClose (todos assinaram).
    Header de segurança: Content-Hmac: sha256=<hash>
    Payload: { "event": {"name": "AutoClose"}, "document": {"key": "<uuid>", ...} }

    Roteamento por Envelope (issue #87): a document.key resolve para uma
    Reunião (fluxo original) ou para uma Versão de POP (publicação na
    Biblioteca). Ambos os fluxos são idempotentes a eventos duplicados.
    """
    from app.services import clicksign_service

    body = await request.body()

    # 1. Validar HMAC — garante que a requisição veio mesmo da ClickSign
    hmac_header = request.headers.get("content-hmac", "")
    received_signature = hmac_header.replace("sha256=", "").strip()

    if not clicksign_service.verify_webhook_hmac(body, received_signature, settings.clicksign_webhook_secret):
        logger.warning("[ClickSign webhook] Assinatura HMAC inválida — requisição rejeitada.")
        raise HTTPException(status_code=401, detail="Assinatura HMAC inválida")

    # 2. Parsear payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON inválido")

    event_name = payload.get("event", {}).get("name", "")

    # 3. Extrair a chave do documento — ClickSign envia em document.key
    envelope_key = payload.get("document", {}).get("key", "")

    logger.info(f"[ClickSign webhook] Evento='{event_name}' | document.key='{envelope_key}'")

    if not envelope_key:
        logger.warning("[ClickSign webhook] Payload sem document.key — ignorado.")
        return {"message": "Payload sem document.key, ignorado."}

    # 4. Rotear pelo Envelope: Reunião primeiro (fluxo original), senão POP
    result = (
        supabase.table("reunioes").select("id_reuniao, status_ata").eq("envelope_key_clicksign", envelope_key).execute()
    )
    if result.data:
        _processar_reuniao(supabase, result.data[0], event_name, envelope_key)
        return {"received": True}

    versao_q = supabase.table("pops_versoes").select("*").eq("envelope_key_clicksign", envelope_key).execute()
    if versao_q.data:
        _processar_versao_pop(supabase, versao_q.data[0], event_name)
        return {"received": True}

    logger.warning(f"[ClickSign webhook] envelope_key '{envelope_key}' não encontrado no banco.")
    return {"message": "Documento não encontrado."}


# ─── Reunião (fluxo original, intacto) ───────────────────────────────────────


def _processar_reuniao(supabase, reuniao: dict, event_name: str, envelope_key: str) -> None:
    """Ata de Reunião: todas as assinaturas → ASSINADA + PDF assinado no
    storage + pendências liberadas; recusa/expiração volta à validação."""
    from app.services import clicksign_service, pendencia_service, storage

    is_completed = event_name in ("AutoClose", "Close", "close", "auto_close")
    is_declined = event_name in ("Refused", "refused")
    is_cancelled = event_name in ("Expired", "Cancelled", "expired", "cancelled")

    id_reuniao = reuniao["id_reuniao"]
    logger.info(f"[ClickSign webhook] Reunião {id_reuniao} — processando evento '{event_name}'")

    if is_completed:
        try:
            # Tenta baixar o PDF assinado
            pdf_assinado = clicksign_service.get_signed_document(envelope_key)
            update_data = {
                "status_ata": "ASSINADA",
                "data_assinatura": datetime.now(UTC).date().isoformat(),
            }

            if pdf_assinado:
                url_pdf_assinado = storage.upload_file(
                    supabase,
                    bucket=settings.supabase_storage_bucket_pdfs_assinados,
                    path=f"{id_reuniao}/ata_assinada.pdf",
                    content=pdf_assinado,
                    content_type="application/pdf",
                )
                update_data["url_pdf_assinado"] = url_pdf_assinado
                logger.info(f"[ClickSign webhook] PDF assinado salvo: {url_pdf_assinado}")
            else:
                logger.warning("[ClickSign webhook] PDF não disponível. Marcando como ASSINADA sem PDF.")

            supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()
            logger.info(f"[ClickSign webhook] ✅ Reunião {id_reuniao} marcada como ASSINADA.")

            # Liberar as pendências (tarefas) do quadro_atribuicoes
            total = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="CLICKSIGN_WEBHOOK")
            logger.info(f"[ClickSign webhook] 📋 {total} pendências liberadas para {id_reuniao}.")

        except Exception as e:
            logger.error(f"[ClickSign webhook] Erro ao concluir assinatura de {id_reuniao}: {e}", exc_info=True)

    elif is_declined:
        supabase.table("reunioes").update({"status_ata": "AGUARDANDO_VALIDACAO"}).eq("id_reuniao", id_reuniao).execute()
        logger.warning(f"[ClickSign webhook] Assinatura recusada — reunião {id_reuniao} voltou para validação.")

    elif is_cancelled:
        supabase.table("reunioes").update({"status_ata": "AGUARDANDO_VALIDACAO"}).eq("id_reuniao", id_reuniao).execute()
        logger.warning(f"[ClickSign webhook] Envelope expirado/cancelado — reunião {id_reuniao} voltou para validação.")

    else:
        logger.info(f"[ClickSign webhook] Evento '{event_name}' sem ação definida — ignorado.")


# ─── Versão de POP (issue #87) ───────────────────────────────────────────────


def _processar_versao_pop(supabase, versao: dict, event_name: str) -> None:
    """Versão de POP: todas as assinaturas → PUBLICADO + PDF assinado no
    storage + auditoria + email ao criador. Idempotente: já PUBLICADO, o
    evento duplicado encerra sem reprocessar. Envelope recusado/expirado
    limpa os IDs (o reenvio cria Envelope novo) mantendo EM_ASSINATURA.
    """
    from app.services import audit, clicksign_service, pops_email_service, pops_pdf_service, storage

    is_completed = event_name in ("AutoClose", "Close", "close", "auto_close")
    is_interrupted = event_name in ("Refused", "refused", "Expired", "Cancelled", "expired", "cancelled")

    versao_id = versao["id"]
    logger.info(f"[ClickSign webhook] Versão de POP {versao_id} — processando evento '{event_name}'")

    if is_completed:
        if versao.get("estado") == "PUBLICADO":
            logger.info(f"[ClickSign webhook] Versão {versao_id} já PUBLICADO — evento duplicado ignorado.")
            return
        try:
            pop_q = supabase.table("pops").select("*").eq("id", versao["pop_id"]).limit(1).execute()
            if not pop_q.data:
                logger.error(f"[ClickSign webhook] POP {versao.get('pop_id')} da Versão {versao_id} não encontrado.")
                return
            pop = pop_q.data[0]

            agora = datetime.now(UTC)
            update_data: dict = {"estado": "PUBLICADO", "data_publicacao": agora.isoformat()}

            # PDF assinado: na API v3 o download é pelo Envelope (não pela
            # document key). Nome travado do DRF com status ASSINADO e a
            # competência da publicação — o download da Biblioteca deriva
            # o mesmo path a partir de data_publicacao.
            pdf_assinado = clicksign_service.get_signed_document(versao.get("envelope_id_clicksign"))
            if pdf_assinado:
                nome_arquivo = pops_pdf_service.nome_arquivo_pop(
                    codigo=pop["codigo"],
                    nome=pop["nome"],
                    numero_versao=versao["numero_versao"],
                    status="ASSINADO",
                    quando=agora,
                )
                url_pdf_assinado = storage.upload_file(
                    supabase,
                    bucket=settings.supabase_storage_bucket_pdfs_assinados,
                    path=f"pops/{pop['id']}/{nome_arquivo}",
                    content=pdf_assinado,
                    content_type="application/pdf",
                )
                update_data["url_pdf_assinado"] = url_pdf_assinado
                logger.info(f"[ClickSign webhook] PDF assinado do POP salvo: {url_pdf_assinado}")
            else:
                logger.warning(
                    f"[ClickSign webhook] PDF assinado indisponível para a Versão {versao_id}. "
                    "Publicando sem PDF (download ficará indisponível até correção manual)."
                )

            supabase.table("pops_versoes").update(update_data).eq("id", versao_id).execute()

            audit.log_action(
                supabase,
                actor=None,  # ator: sistema (webhook ClickSign)
                action="POPS_PUBLICAR",
                target_type="pop_versao",
                target_id=versao_id,
                metadata={
                    "pop_id": pop["id"],
                    "codigo": pop["codigo"],
                    "evento": event_name,
                    "envelope_id": versao.get("envelope_id_clicksign"),
                },
            )
            logger.info(f"[ClickSign webhook] ✅ POP {pop['codigo']} v{versao['numero_versao']} PUBLICADO.")

            setor_q = (
                supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
            )
            setor = setor_q.data[0] if setor_q.data else {}
            pops_email_service.send_pop_publicado_notification(supabase, pop, setor)

        except Exception as e:
            logger.error(f"[ClickSign webhook] Erro ao publicar Versão {versao_id}: {e}", exc_info=True)

    elif is_interrupted:
        supabase.table("pops_versoes").update({"envelope_id_clicksign": None, "envelope_key_clicksign": None}).eq(
            "id", versao_id
        ).execute()
        audit.log_action(
            supabase,
            actor=None,
            action="POPS_ASSINATURA_INTERROMPIDA",
            target_type="pop_versao",
            target_id=versao_id,
            metadata={"pop_id": versao.get("pop_id"), "evento": event_name},
        )
        logger.warning(
            f"[ClickSign webhook] Envelope da Versão {versao_id} interrompido ('{event_name}') — "
            "IDs limpos; EM_ASSINATURA segue re-tentável via reenvio."
        )

    else:
        logger.info(f"[ClickSign webhook] Evento '{event_name}' sem ação definida para POP — ignorado.")
