from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_supabase_client

router = APIRouter(prefix="/webhook", tags=["webhooks"])
logger = logging.getLogger(__name__)


# Webhook ClickSign (callback de assinatura)
@router.post("/clicksign-completed")
async def webhook_clicksign(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """
    Recebe notificações da ClickSign sobre fechamento de documentos.

    Eventos tratados: Close (fechamento manual) e AutoClose (todos assinaram).
    Header de segurança: Content-Hmac: sha256=<hash>
    Payload: { "event": {"name": "AutoClose"}, "document": {"key": "<uuid>", ...} }
    """
    from app.services import clicksign_service, storage, pendencia_service

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

    # 4. Eventos de conclusão: Close (manual) e AutoClose (todos assinaram)
    is_completed = event_name in ("AutoClose", "Close", "close", "auto_close")
    is_declined = event_name in ("Refused", "refused")
    is_cancelled = event_name in ("Expired", "Cancelled", "expired", "cancelled")

    # 5. Buscar reunião pelo envelope_key
    result = supabase.table("reunioes").select("id_reuniao, status_ata").eq(
        "envelope_key_clicksign", envelope_key
    ).execute()

    if not result.data:
        logger.warning(f"[ClickSign webhook] envelope_key '{envelope_key}' não encontrado no banco.")
        return {"message": "Documento não encontrado."}

    reuniao = result.data[0]
    id_reuniao = reuniao["id_reuniao"]

    logger.info(f"[ClickSign webhook] Reunião {id_reuniao} — processando evento '{event_name}'")

    # 6. Processar conforme o evento
    if is_completed:
        try:
            # Tenta baixar o PDF assinado
            pdf_assinado = clicksign_service.get_signed_document(envelope_key)
            update_data = {
                "status_ata": "ASSINADA",
                "data_assinatura": datetime.now(timezone.utc).date().isoformat(),
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
                logger.warning(f"[ClickSign webhook] PDF não disponível. Marcando como ASSINADA sem PDF.")

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

    return {"received": True}
