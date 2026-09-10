import hashlib
import hmac
import json
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
    Recebe notificações da ClickSign sobre assinaturas e fechamento de documentos.

    Eventos tratados (nomes oficiais em snake_case): `sign` (assinatura
    individual, gatilho incremental do ADR 0030), `close` (fechamento manual),
    `auto_close` (todos assinaram), `deadline` (prazo atingido: finaliza com
    ao menos uma assinatura), `document_closed` (PDF pronto para download) e,
    para Reunião, `refusal`/`cancel`/`deadline` sem assinaturas (abrem o modo
    interno, ADR 0030 decisão 3).
    Grafias legadas AutoClose/Close seguem aceitas por compatibilidade.
    Header de segurança: Content-Hmac: sha256=<hash>
    Payload: { "event": {"name": "auto_close"}, "document": {"key": "<uuid>", ...} }

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
        supabase.table("reunioes")
        .select("id_reuniao, status_ata, envelope_id_clicksign, url_pdf_assinado")
        .eq("envelope_key_clicksign", envelope_key)
        .execute()
    )
    if result.data:
        _processar_reuniao(supabase, result.data[0], event_name, envelope_key, payload)
        return {"received": True}

    versao_q = supabase.table("pops_versoes").select("*").eq("envelope_key_clicksign", envelope_key).execute()
    if versao_q.data:
        _processar_versao_pop(supabase, versao_q.data[0], event_name)
        return {"received": True}

    logger.warning(f"[ClickSign webhook] envelope_key '{envelope_key}' não encontrado no banco.")
    return {"message": "Documento não encontrado."}


# ─── Reunião (fluxo original, intacto) ───────────────────────────────────────


def _iniciar_coleta_interna_best_effort(supabase, id_reuniao: str) -> None:
    """Dispara a coleta de Aceites internos (emails + notificação + desfecho
    imediato, issue #277). Best-effort: o modo interno já está aberto e o
    webhook responde 200 mesmo se o provedor de email falhar."""
    from app.services import aceite_service

    try:
        aceite_service.iniciar_coleta_interna(supabase, id_reuniao)
    except Exception as e:
        logger.error(f"[ClickSign webhook] Falha best-effort na coleta interna de {id_reuniao}: {e}", exc_info=True)


def _processar_reuniao(supabase, reuniao: dict, event_name: str, envelope_key: str, payload: dict) -> None:
    """Ata de Reunião: `sign` cria na hora as Pendências do signatário (ADR
    0030, nascimento incremental via Registro de Aceites); fechamento
    (`close`/`auto_close`/`deadline` com ao menos uma assinatura) libera o
    restante + registro de faltantes + ASSINADA + PDF best-effort;
    `document_closed` baixa o PDF assinado; `refusal`, `cancel` e `deadline`
    com zero assinaturas abrem o modo interno (Envelope morto, sem reenvio; a
    Reunião permanece em AGUARDANDO_ASSINATURA com flag persistida).

    Ordem do invariante (ADR 0003, issue #190): as Pendências nascem ANTES do
    estado terminal. Falha na liberação aborta com não-2xx para a ClickSign
    reenviar o evento (a liberação é idempotente por ação do quadro). Reunião
    já ASSINADA encerra sem reprocessar o evento duplicado.
    """
    from app.services import aceite_service

    is_signed = event_name == "sign"
    is_completed = event_name in ("AutoClose", "Close", "close", "auto_close")
    is_deadline = event_name == "deadline"
    is_document_closed = event_name == "document_closed"
    # Nomes oficiais da API v3 (snake_case). Os antigos Refused/Expired/
    # Cancelled não existem na doc e saíram do mapeamento (PRD #272): recusa e
    # cancelamento não devolvem mais a Reunião para AGUARDANDO_VALIDACAO.
    is_envelope_morto = event_name in ("refusal", "cancel")

    id_reuniao = reuniao["id_reuniao"]
    logger.info(f"[ClickSign webhook] Reunião {id_reuniao} — processando evento '{event_name}'")

    if is_signed:
        # Gatilho incremental só vale com a Ata aguardando assinatura (o modo
        # interno permanece nesse status, então um 'sign' atrasado ainda conta).
        # Evento tardio ou redelivery fora de ordem não pode criar Pendência de
        # uma ata em revisão nem reprocessar estado terminal.
        if reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA":
            logger.info(
                f"[ClickSign webhook] Reunião {id_reuniao} em '{reuniao.get('status_ata')}', "
                "'sign' ignorado (gatilho incremental exige AGUARDANDO_ASSINATURA)."
            )
            return
        event = payload.get("event") or {}
        signer = (event.get("data") or {}).get("signer") or {}
        signer_key = signer.get("key")
        signer_email = signer.get("email")
        if not signer_key and not signer_email:
            logger.warning(f"[ClickSign webhook] Evento 'sign' sem signer identificável para {id_reuniao}, ignorado.")
            return
        try:
            criadas = aceite_service.registrar_assinatura_clicksign(
                supabase,
                id_reuniao,
                signer_key=signer_key,
                signer_email=signer_email,
                aceito_em=event.get("occurred_at"),
            )
            logger.info(f"[ClickSign webhook] 📋 'sign' (key={signer_key}): {criadas} pendências em {id_reuniao}.")
            # `sign` atrasado no modo interno ainda conta (issue #277): se era
            # a última ação sem Pendência, o desfecho terminal fecha a Reunião.
            # Auto-guardado: fora do modo interno é no-op. Falha propaga para o
            # except abaixo (não-2xx, a ClickSign reenvia; tudo idempotente).
            aceite_service.verificar_desfecho_modo_interno(supabase, id_reuniao)
        except Exception as e:
            logger.error(f"[ClickSign webhook] Falha no aceite incremental de {id_reuniao}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Falha ao registrar a assinatura; a ClickSign deve reenviar o evento.",
            )
        return

    if is_completed or is_deadline:
        if reuniao.get("status_ata") == "ASSINADA":
            logger.info(f"[ClickSign webhook] Reunião {id_reuniao} já ASSINADA, evento duplicado ignorado.")
            return

        # `deadline` é evento agendado, chega tarde por natureza: só finaliza
        # com a Ata ainda aguardando assinatura (mesma guarda do `sign`).
        if is_deadline and reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA":
            logger.info(
                f"[ClickSign webhook] Reunião {id_reuniao} em '{reuniao.get('status_ata')}', "
                "'deadline' ignorado (finalização exige AGUARDANDO_ASSINATURA)."
            )
            return

        # `deadline` só finaliza com ao menos uma assinatura (comportamento
        # default da ClickSign: com zero assinaturas o documento é cancelado
        # e o caminho é o modo interno, ADR 0030 decisão 3 / issue #276).
        signers = None
        if is_deadline:
            signers = aceite_service.consultar_signatarios(reuniao.get("envelope_id_clicksign"))
            if not aceite_service.houve_assinatura(supabase, id_reuniao, signers):
                aberto = aceite_service.abrir_modo_interno(supabase, id_reuniao, evento=event_name)
                if aberto:
                    logger.warning(
                        f"[ClickSign webhook] 'deadline' sem nenhuma assinatura em {id_reuniao}: "
                        "a ClickSign cancela o documento; Reunião entrou no modo interno "
                        "(Pendências mantidas, sem reenvio ao ClickSign)."
                    )
                    _iniciar_coleta_interna_best_effort(supabase, id_reuniao)
                return

        # Finalização real (ADR 0030): Pendências restantes ANTES do estado
        # terminal, registro de quem assinou/faltou e PDF best-effort. Falha
        # responde não-2xx: a Reunião não vira ASSINADA e a ClickSign reenvia.
        try:
            aceite_service.finalizar_documento(supabase, reuniao, envelope_key=envelope_key, signers=signers)
        except Exception as e:
            logger.error(f"[ClickSign webhook] Falha na finalização de {id_reuniao}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Falha ao liberar pendências; a Reunião não foi marcada como ASSINADA.",
            )
        logger.info(f"[ClickSign webhook] ✅ Reunião {id_reuniao} marcada como ASSINADA (evento '{event_name}').")

    elif is_document_closed:
        # PDF pronto para download (a doc só garante o arquivo aqui). Best-
        # effort e idempotente; não mexe no status da Reunião.
        try:
            aceite_service.registrar_documento_pronto(supabase, reuniao, envelope_key=envelope_key)
        except Exception as e:
            logger.warning(f"[ClickSign webhook] Falha best-effort no document_closed de {id_reuniao}: {e}")

    elif is_envelope_morto:
        if reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA":
            logger.info(
                f"[ClickSign webhook] Reunião {id_reuniao} em '{reuniao.get('status_ata')}', "
                f"evento '{event_name}' ignorado (modo interno exige AGUARDANDO_ASSINATURA)."
            )
            return
        aberto = aceite_service.abrir_modo_interno(supabase, id_reuniao, evento=event_name)
        if aberto:
            logger.warning(
                f"[ClickSign webhook] Envelope morto ('{event_name}'): Reunião {id_reuniao} "
                "entrou no modo interno: Pendências mantidas, sem reenvio ao ClickSign."
            )
            _iniciar_coleta_interna_best_effort(supabase, id_reuniao)

    else:
        logger.info(f"[ClickSign webhook] Evento '{event_name}' sem ação definida — ignorado.")


# ─── Versão de POP (issue #87) ───────────────────────────────────────────────


def _processar_versao_pop(supabase, versao: dict, event_name: str) -> None:
    """Versão de POP: todas as assinaturas → PUBLICADO + PDF assinado no
    storage + auditoria + email ao criador. Idempotente: já PUBLICADO, o
    evento duplicado encerra sem reprocessar. Envelope recusado/expirado
    limpa os IDs (o reenvio cria Envelope novo) mantendo EM_ASSINATURA.
    """
    from app.services import clicksign_service, pops_dominio, pops_email_service, pops_pdf_service, storage

    is_completed = event_name in ("AutoClose", "Close", "close", "auto_close")
    # Nomes oficiais v3 em snake_case (`refusal`, `cancel`, `deadline`, issue
    # #275) + grafias legadas; comportamento de interrupção preservado.
    is_interrupted = event_name in (
        "Refused",
        "refused",
        "refusal",
        "Expired",
        "expired",
        "Cancelled",
        "cancelled",
        "cancel",
        "deadline",
    )

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

            # PDF assinado: na API v3 o download é pelo Envelope (não pela
            # document key). Nome travado do DRF com status ASSINADO e a
            # competência da publicação — o download da Biblioteca deriva
            # o mesmo path a partir de data_publicacao.
            url_pdf_assinado = None
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
                logger.info(f"[ClickSign webhook] PDF assinado do POP salvo: {url_pdf_assinado}")
            else:
                logger.warning(
                    f"[ClickSign webhook] PDF assinado indisponível para a Versão {versao_id}. "
                    "Publicando sem PDF (download ficará indisponível até correção manual)."
                )

            pops_dominio.publicar_versao(
                supabase,
                versao,
                data_publicacao=agora.isoformat(),
                url_pdf_assinado=url_pdf_assinado,
                evento=event_name,
                codigo=pop["codigo"],
            )
            logger.info(f"[ClickSign webhook] ✅ POP {pop['codigo']} v{versao['numero_versao']} PUBLICADO.")

            setor_q = (
                supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
            )
            setor = setor_q.data[0] if setor_q.data else {}
            pops_email_service.send_pop_publicado_notification(
                supabase, pop, setor, numero_versao=versao.get("numero_versao")
            )

        except Exception as e:
            logger.error(f"[ClickSign webhook] Erro ao publicar Versão {versao_id}: {e}", exc_info=True)

    elif is_interrupted:
        pops_dominio.interromper_assinatura(supabase, versao, evento=event_name)
        logger.warning(
            f"[ClickSign webhook] Envelope da Versão {versao_id} interrompido ('{event_name}') — "
            "IDs limpos; EM_ASSINATURA segue re-tentável via reenvio."
        )

    else:
        logger.info(f"[ClickSign webhook] Evento '{event_name}' sem ação definida para POP — ignorado.")


# ─── Webhook do GitHub (issue #678, PRD #673, ADR 0054) ──────────────────────

# O que a porta responde a quem não está autenticado quando o segredo falta.
#
# Genérica de propósito: quem bate aqui não provou ser ninguém, e "falta a
# variável X" é informação sobre a instalação. A causa de verdade vai para o
# log, que é onde o operador olha.
MOTIVO_WEBHOOK_INDISPONIVEL = "Webhook indisponível."

MOTIVO_ASSINATURA_INVALIDA = "Assinatura inválida"


def _assinatura_do_github_confere(corpo: bytes, cabecalho: str | None, segredo: str) -> bool:
    """Se o `X-Hub-Signature-256` bate com o HMAC SHA-256 do CORPO CRU.

    Cru quer dizer os bytes que chegaram, e não o dicionário re-serializado. O
    GitHub assina o que mandou; um `json.dumps` do payload parseado devolve os
    mesmos dados com outro espaçamento, e a assinatura deixaria de bater no dia
    em que o GitHub mudasse a formatação, em produção, sem nada acusar antes.

    `compare_digest` e não `==`: a comparação ingênua para no primeiro byte
    diferente, e o tempo dela conta ao atacante quantos bytes ele já acertou.
    """
    if not cabecalho:
        return False
    algoritmo, _, recebida = cabecalho.partition("=")
    if algoritmo.strip().lower() != "sha256" or not recebida.strip():
        return False
    esperada = hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, recebida.strip())


@router.post("/github")
async def webhook_github(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """A Demanda vinculada aprendendo do GitHub em segundos (ADR 0054, decisão 2).

    Cadastro no repositório: URL desta rota, content type JSON, segredo igual ao
    `GITHUB_WEBHOOK_SECRET` do ambiente e **só o evento `issues`**. Os dois lados
    do cadastro são passo humano do deploy: sem o segredo a rota responde 503, e
    sem o webhook cadastrado o card só anda de hora em hora, pela reconciliação.

    A ordem das guardas é a ordem das causas, e não é negociável:

    1. **Segredo configurado.** Sem ele não há o que conferir, e aceitar seria
       deixar a porta aberta com aparência de guarda.
    2. **Assinatura.** Antes de olhar QUALQUER outra coisa do pedido, o header do
       evento incluído: conferir o evento primeiro deixaria qualquer um
       descobrir, sem segredo nenhum, quais eventos o app trata.
    3. **Evento e ação.** Só `issues`, e só nas ações que mexem em label, estado
       ou corpo. O resto sai em 2xx sem gastar cota do GitHub.
    4. **Demanda vinculada.** A esmagadora maioria das issues do repositório não
       tem Demanda nenhuma atrás, e isso não é erro.

    Responde 2xx mesmo quando a sincronização falha. O GitHub exige 2xx em 10
    segundos e **não reentrega** o que falhou: um 500 aqui perderia o evento para
    sempre, e quem recupera é a reconciliação de hora em hora.
    """
    from app.services import tecnologia_sincronizacao

    segredo = settings.github_webhook_secret
    if not segredo:
        logger.error("[GitHub webhook] GITHUB_WEBHOOK_SECRET não configurado; entrega recusada.")
        raise HTTPException(status_code=503, detail=MOTIVO_WEBHOOK_INDISPONIVEL)

    corpo = await request.body()
    if not _assinatura_do_github_confere(corpo, request.headers.get("x-hub-signature-256"), segredo):
        logger.warning("[GitHub webhook] Assinatura inválida: entrega recusada.")
        raise HTTPException(status_code=401, detail=MOTIVO_ASSINATURA_INVALIDA)

    if request.headers.get("x-github-event") != "issues":
        return {"ignorado": "evento"}

    try:
        payload = json.loads(corpo)
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload JSON inválido")

    if not isinstance(payload, dict) or payload.get("action") not in tecnologia_sincronizacao.ACOES_DE_ISSUE:
        return {"ignorado": "acao"}

    numero = (payload.get("issue") or {}).get("number")
    if not isinstance(numero, int):
        logger.warning("[GitHub webhook] Evento 'issues' sem número de issue; ignorado.")
        return {"ignorado": "issue"}

    demanda = tecnologia_sincronizacao.demanda_vinculada(supabase, numero)
    if demanda is None:
        return {"ignorado": "sem_vinculo"}

    try:
        mudou = tecnologia_sincronizacao.sincronizar_demanda(supabase, demanda)
    except Exception:
        logger.warning(
            "[GitHub webhook] Falha ao sincronizar a Demanda %s (issue #%s); a reconciliação recupera.",
            demanda.get("id"),
            numero,
            exc_info=True,
        )
        return {"recebido": True, "sincronizada": False}

    return {"recebido": True, "sincronizada": mudou}
