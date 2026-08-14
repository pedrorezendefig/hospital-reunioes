"""
Registro de Aceites (ADR 0030): módulo profundo do nascimento incremental.

Persiste, por Reunião e Signatário, a origem do compromisso ('clicksign',
'aceite_interno', 'super_admin') e o timestamp na tabela `reuniao_aceites`,
e encapsula TODA a regra incremental de nascimento de Pendências:

- Signatário assina no ClickSign: nascem na hora as Pendências dele, plenas.
- O Facilitador da Reunião assina: nascem também as de responsáveis fora do
  Envelope (sem vínculo ou fora do roster de signatários).

Correlação signatário ↔ Participante por `signer.key`, com fallback por email
normalizado (mesmo padrão da tela de signatários). Webhook e endpoints são
cascas finas por cima deste serviço.
"""

import logging
from datetime import UTC, datetime

from app.config import settings
from app.services import clicksign_service, pendencia_service, storage
from app.services.pendencia_service import _e_conflito_unicidade

logger = logging.getLogger(__name__)


def _normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _buscar_aceite(supabase, id_reuniao: str, signer_key: str | None, email_norm: str) -> dict | None:
    """Aceite já registrado para este signatário? Chave primária de correlação
    é o signer_key; fallback por email normalizado."""
    rows = (
        supabase.table("reuniao_aceites")
        .select("id, participante_id, signer_key, email")
        .eq("id_reuniao", id_reuniao)
        .execute()
        .data
        or []
    )
    if signer_key:
        achado = next((r for r in rows if r.get("signer_key") == signer_key), None)
        if achado:
            return achado
    if email_norm:
        return next((r for r in rows if (r.get("email") or "") == email_norm), None)
    return None


def _roster(supabase, id_reuniao: str) -> dict[str, str]:
    """Roster ativo da Reunião: {participante_id: email_normalizado}.

    Uma busca só serve à correlação por email e à regra do Facilitador.
    Participante inativo sai (Pendência não nasce para inativo, ADR 0008).
    """
    vinculos = (
        supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    roster_ids = {v["participante_id"] for v in vinculos}
    if not roster_ids:
        return {}
    pessoas = (
        supabase.table("participantes")
        .select("id, email")
        .eq("ativo", True)
        .in_("id", sorted(roster_ids))
        .execute()
        .data
        or []
    )
    return {p["id"]: _normalizar_email(p.get("email")) for p in pessoas}


def _correlacionar_participante(roster: dict[str, str], email_norm: str) -> str | None:
    """Resolve o Participante do roster pelo email normalizado."""
    if not email_norm:
        return None
    return next((pid for pid, email in roster.items() if email and email == email_norm), None)


def registrar_assinatura_clicksign(
    supabase,
    id_reuniao: str,
    signer_key: str | None,
    signer_email: str | None,
    aceito_em: str | None = None,
) -> int:
    """Registra o aceite de um signatário ClickSign e cria as Pendências dele.

    Idempotente: evento repetido não duplica aceite nem Pendência (a criação
    delega em `liberar_pendencias`, idempotente por ação do quadro). Retorna o
    número de Pendências criadas nesta chamada.
    """
    email_norm = _normalizar_email(signer_email)
    roster = _roster(supabase, id_reuniao)

    aceite = _buscar_aceite(supabase, id_reuniao, signer_key, email_norm)
    if aceite is not None:
        participante_id = aceite.get("participante_id")
        if not participante_id:
            # Aceite gravado sem correlação (email divergente na época): um
            # redelivery re-tenta a correlação para não congelar o signatário.
            participante_id = _correlacionar_participante(roster, email_norm)
            if participante_id:
                try:
                    supabase.table("reuniao_aceites").update({"participante_id": participante_id}).eq(
                        "id", aceite["id"]
                    ).execute()
                except Exception as e:
                    if not _e_conflito_unicidade(e):
                        raise
                    logger.info(f"[AceiteService] Participante {participante_id} já tem aceite em {id_reuniao}.")
    else:
        participante_id = _correlacionar_participante(roster, email_norm)
        registro = {
            "id_reuniao": id_reuniao,
            "participante_id": participante_id,
            "signer_key": signer_key,
            "email": email_norm or None,
            "origem": "clicksign",
            "aceito_em": aceito_em or datetime.now(UTC).isoformat(),
        }
        try:
            supabase.table("reuniao_aceites").insert(registro).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            # Webhook duplicado em paralelo já gravou o mesmo aceite: segue em
            # frente, a criação de Pendências abaixo é idempotente.
            logger.info(f"[AceiteService] Aceite de {signer_key or email_norm} em {id_reuniao} já registrado.")

    if not participante_id:
        # Log sem PII: email mascarado (só key + 2 primeiros chars)
        ident = signer_key or (email_norm[:2] + "***" if email_norm else "?")
        logger.warning(
            f"[AceiteService] Signatário sem correlação com Participante em {id_reuniao} "
            f"(signer={ident}). Aceite registrado; nenhuma Pendência criada."
        )
        return 0

    reuniao_q = supabase.table("reunioes").select("facilitador_id").eq("id_reuniao", id_reuniao).execute()
    facilitador_id = (reuniao_q.data or [{}])[0].get("facilitador_id")
    eh_facilitador = bool(facilitador_id) and participante_id == facilitador_id
    # Signatário do Envelope = membro do roster COM email (add_signer exige
    # email; quem não tem nunca vai assinar e conta como fora do Envelope).
    signatarios_envelope = {pid for pid, email in roster.items() if email}

    def _filtro(acao: dict) -> bool:
        responsavel_id = acao.get("responsavel_id")
        if responsavel_id == participante_id:
            return True
        # A assinatura do Facilitador libera quem está fora do Envelope:
        # responsável sem vínculo ou que não é Signatário.
        return eh_facilitador and (responsavel_id is None or responsavel_id not in signatarios_envelope)

    criadas = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="CLICKSIGN_SIGN", filtro=_filtro)
    logger.info(
        f"[AceiteService] Aceite clicksign de {participante_id} em {id_reuniao}: "
        f"{criadas} Pendências criadas (facilitador={eh_facilitador})."
    )
    return criadas


def consultar_signatarios(envelope_id: str | None) -> list[dict] | None:
    """Signers do Envelope com o status real de assinatura (eventos `sign`
    cruzados com a lista de signers, padrão da tela de signatários).

    None = indisponível (sem envelope_id ou ClickSign fora do ar)."""
    if not envelope_id:
        return None
    return clicksign_service.list_signers(envelope_id)


def houve_assinatura(supabase, id_reuniao: str, signers: list[dict] | None) -> bool:
    """Ao menos um signatário assinou? Decide o desfecho do `deadline`
    (finaliza com parciais; com zero a ClickSign cancela o documento).

    Fonte primária: signers consultados na ClickSign. Fallback quando a
    consulta está indisponível: aceites `clicksign` já registrados pelo
    gatilho incremental (webhook `sign`)."""
    if signers is not None:
        return any(s.get("status") == "signed" for s in signers)
    aceites = (
        supabase.table("reuniao_aceites")
        .select("id")
        .eq("id_reuniao", id_reuniao)
        .eq("origem", "clicksign")
        .execute()
        .data
        or []
    )
    return bool(aceites)


def _reconciliar_aceites_do_fechamento(supabase, id_reuniao: str, signers: list[dict]) -> int:
    """Garante um aceite `clicksign` para cada signer que assinou (cobre
    webhook `sign` perdido). Quem NÃO assinou fica sem aceite: é assim que o
    Registro de Aceites registra os faltantes. Retorna quantos assinaram."""
    roster = _roster(supabase, id_reuniao)
    assinaram = 0
    for signer in signers:
        if signer.get("status") != "signed":
            continue
        assinaram += 1
        signer_key = signer.get("signer_id")
        email_norm = _normalizar_email(signer.get("email"))
        if _buscar_aceite(supabase, id_reuniao, signer_key, email_norm):
            continue
        registro = {
            "id_reuniao": id_reuniao,
            "participante_id": _correlacionar_participante(roster, email_norm),
            "signer_key": signer_key,
            "email": email_norm or None,
            "origem": "clicksign",
            "aceito_em": signer.get("signed_at") or datetime.now(UTC).isoformat(),
        }
        try:
            supabase.table("reuniao_aceites").insert(registro).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            logger.info(f"[AceiteService] Aceite de {signer_key or email_norm} em {id_reuniao} já registrado.")
    return assinaram


def _baixar_e_subir_pdf_assinado(supabase, id_reuniao: str, envelope_ref: str | None) -> str | None:
    """Baixa o PDF assinado da ClickSign e sobe pro storage. None = indisponível."""
    if not envelope_ref:
        return None
    pdf_assinado = clicksign_service.get_signed_document(envelope_ref)
    if not pdf_assinado:
        return None
    return storage.upload_file(
        supabase,
        bucket=settings.supabase_storage_bucket_pdfs_assinados,
        path=f"{id_reuniao}/ata_assinada.pdf",
        content=pdf_assinado,
        content_type="application/pdf",
    )


def finalizar_documento(supabase, reuniao: dict, *, envelope_key: str, signers: list[dict] | None = None) -> None:
    """Fechamento real do Envelope (`close`, `auto_close` ou `deadline` com ao
    menos uma assinatura): libera as Pendências restantes, registra quem
    assinou e quem faltou, e marca a Reunião como ASSINADA.

    Ordem do invariante (ADR 0003): as Pendências nascem ANTES do estado
    terminal; falha na liberação propaga (o caller responde não-2xx e a
    ClickSign reenvia o evento; a liberação é idempotente por ação do quadro).
    Registro de aceites/contagem e PDF assinado são best-effort.
    """
    id_reuniao = reuniao["id_reuniao"]
    envelope_id = reuniao.get("envelope_id_clicksign")

    total = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="CLICKSIGN_WEBHOOK")
    logger.info(f"[AceiteService] 📋 {total} pendências liberadas na finalização de {id_reuniao}.")

    update_data: dict = {
        "status_ata": "ASSINADA",
        "data_assinatura": datetime.now(UTC).date().isoformat(),
    }

    # Quem assinou × quem faltou (selo discreto "N de M assinaram"): cruzamento
    # feito pela ClickSign (eventos sign × signers). Best-effort: indisponível,
    # a contagem fica nula e o banner segue sem selo.
    try:
        if signers is None:
            signers = consultar_signatarios(envelope_id)
        if signers is not None:
            assinaram = _reconciliar_aceites_do_fechamento(supabase, id_reuniao, signers)
            update_data["signatarios_total"] = len(signers)
            update_data["signatarios_assinaram"] = assinaram
            if assinaram < len(signers):
                logger.info(
                    f"[AceiteService] Finalização de {id_reuniao} com faltantes: "
                    f"{assinaram} de {len(signers)} assinaram."
                )
    except Exception as e:
        logger.warning(f"[AceiteService] Falha best-effort no registro de faltantes de {id_reuniao}: {e}")

    # PDF assinado best-effort: falha não segura a finalização. Sem
    # envelope_id (Atas pré-039) mantém a consulta pela document key.
    # `document_closed` pode ter chegado antes do fechamento: PDF já salvo,
    # não baixa de novo.
    try:
        if reuniao.get("url_pdf_assinado"):
            url_pdf_assinado = reuniao["url_pdf_assinado"]
        else:
            url_pdf_assinado = _baixar_e_subir_pdf_assinado(supabase, id_reuniao, envelope_id or envelope_key)
        if url_pdf_assinado:
            update_data["url_pdf_assinado"] = url_pdf_assinado
            logger.info(f"[AceiteService] PDF assinado salvo: {url_pdf_assinado}")
        else:
            logger.warning("[AceiteService] PDF não disponível. Marcando como ASSINADA sem PDF.")
    except Exception as e:
        logger.warning(f"[AceiteService] Falha best-effort no PDF assinado de {id_reuniao}: {e}")

    # Estado terminal por último (ADR 0003).
    supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()


def registrar_documento_pronto(supabase, reuniao: dict, *, envelope_key: str) -> str | None:
    """`document_closed`: o PDF assinado está pronto para download (a doc da
    ClickSign só garante o arquivo neste evento). Baixa e grava a URL na
    Reunião, sem mexer no status. Idempotente: URL já gravada, nada a fazer."""
    if reuniao.get("url_pdf_assinado"):
        return reuniao["url_pdf_assinado"]
    id_reuniao = reuniao["id_reuniao"]
    envelope_ref = reuniao.get("envelope_id_clicksign") or envelope_key
    url_pdf_assinado = _baixar_e_subir_pdf_assinado(supabase, id_reuniao, envelope_ref)
    if url_pdf_assinado:
        supabase.table("reunioes").update({"url_pdf_assinado": url_pdf_assinado}).eq("id_reuniao", id_reuniao).execute()
        logger.info(f"[AceiteService] PDF assinado de {id_reuniao} salvo via document_closed: {url_pdf_assinado}")
    return url_pdf_assinado


def abrir_modo_interno(supabase, id_reuniao: str, evento: str) -> bool:
    """Abre o modo interno da Reunião (ADR 0030, decisão 3).

    O Envelope morreu (recusa, cancelamento ou deadline sem assinaturas) e não
    há reenvio ao ClickSign: a Reunião permanece em AGUARDANDO_ASSINATURA com a
    flag `modo_interno_desde` persistida. As Pendências já nascidas são
    mantidas intactas; as ações correspondentes ficam travadas para edição
    (regra aplicada no endpoint de edição do quadro).

    Idempotente: redelivery não reabre nem reescreve o timestamp. Retorna True
    se o modo interno foi aberto nesta chamada.
    """
    reuniao_q = supabase.table("reunioes").select("modo_interno_desde").eq("id_reuniao", id_reuniao).execute()
    row = (reuniao_q.data or [{}])[0]
    if row.get("modo_interno_desde"):
        logger.info(f"[AceiteService] Modo interno de {id_reuniao} já aberto; evento '{evento}' duplicado ignorado.")
        return False

    supabase.table("reunioes").update({"modo_interno_desde": datetime.now(UTC).isoformat()}).eq(
        "id_reuniao", id_reuniao
    ).execute()
    logger.info(f"[AceiteService] Modo interno aberto para {id_reuniao} (evento '{evento}').")
    return True


def progresso_pendencias(supabase, id_reuniao: str) -> dict:
    """Progresso do nascimento incremental: Pendências criadas × total de ações
    do quadro. Alimenta a linha "Pendências criadas: X de Y" do card."""
    reuniao_q = supabase.table("reunioes").select("json_ata").eq("id_reuniao", id_reuniao).execute()
    json_ata = (reuniao_q.data or [{}])[0].get("json_ata")
    quadro = pendencia_service.extrair_quadro(json_ata)
    criadas = (
        supabase.table("pendencias")
        .select("id_acao")
        .eq("id_reuniao", id_reuniao)
        .is_("deleted_at", "null")
        .execute()
        .data
        or []
    )
    return {"pendencias_criadas": len(criadas), "total_acoes": len(quadro)}
