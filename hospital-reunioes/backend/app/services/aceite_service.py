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

import hashlib
import logging
import secrets
from datetime import UTC, datetime

from app.config import settings
from app.services import clicksign_service, pendencia_service, storage
from app.services.pendencia_service import _e_conflito_unicidade, _posicoes_ocupadas

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


def _signatarios_envelope(roster: dict[str, str]) -> set[str]:
    """Signatário do Envelope = membro do roster COM email (add_signer exige
    email; quem não tem nunca vai assinar e conta como fora do Envelope)."""
    return {pid for pid, email in roster.items() if email}


def _filtro_incremental(participante_id: str, eh_facilitador: bool, signatarios_envelope: set[str]):
    """Filtro do gatilho incremental (ADR 0030, decisão 1), compartilhado pela
    assinatura ClickSign e pelo Aceite interno: nascem as ações do próprio
    aceitante e, quando ele é o Facilitador, também as de quem está fora do
    Envelope (responsável sem vínculo ou que não é Signatário)."""

    def _filtro(acao: dict) -> bool:
        responsavel_id = acao.get("responsavel_id")
        if responsavel_id == participante_id:
            return True
        return eh_facilitador and (responsavel_id is None or responsavel_id not in signatarios_envelope)

    return _filtro


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
    filtro = _filtro_incremental(participante_id, eh_facilitador, _signatarios_envelope(roster))
    criadas = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="CLICKSIGN_SIGN", filtro=filtro)
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

    Idempotente por construção: o UPDATE só afeta a linha se `modo_interno_desde`
    ainda for NULL, então dois eventos concorrentes (ex.: refusal e cancel do
    mesmo redelivery) nunca reabrem nem reescrevem o timestamp um do outro.
    Retorna True se o modo interno foi aberto nesta chamada.
    """
    resultado = (
        supabase.table("reunioes")
        .update({"modo_interno_desde": datetime.now(UTC).isoformat()})
        .eq("id_reuniao", id_reuniao)
        .is_("modo_interno_desde", "null")
        .execute()
    )
    if not resultado.data:
        logger.info(f"[AceiteService] Modo interno de {id_reuniao} já aberto; evento '{evento}' duplicado ignorado.")
        return False
    logger.info(f"[AceiteService] Modo interno aberto para {id_reuniao} (evento '{evento}').")
    return True


# ─── Aceite interno (ADR 0030 decisão 3, issue #277) ─────────────────────────


class TokenInvalidoError(Exception):
    """Token que não existe no Registro (link forjado ou truncado)."""


class TokenJaUsadoError(Exception):
    """Token de uso único já consumido (aceite já registrado)."""


class TokenExpiradoError(Exception):
    """Token de Reunião que saiu do modo interno (ex.: já ASSINADA)."""


def _hash_token(token: str) -> str:
    """SHA-256 hex do token opaco: o banco só guarda o hash (vazamento de
    banco não expõe link válido)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _quadro_resolvido(supabase, id_reuniao: str, json_ata: dict | None) -> list[dict]:
    quadro = pendencia_service.extrair_quadro(json_ata)
    return pendencia_service.resolver_quadro_da_reuniao(supabase, id_reuniao, quadro)


def _buscar_reuniao(supabase, id_reuniao: str) -> dict | None:
    rows = (
        supabase.table("reunioes")
        .select("id_reuniao, titulo, tipo, data, hora_inicio, status_ata, modo_interno_desde, facilitador_id, json_ata")
        .eq("id_reuniao", id_reuniao)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def verificar_desfecho_modo_interno(supabase, id_reuniao: str) -> bool:
    """Desfecho terminal do modo interno (regra EXCLUSIVA dele): quando toda
    ação do quadro tem Pendência nascida, a Reunião vira ASSINADA com
    `data_assinatura` e o selo de assinaturas mistas (contagem persistida:
    total = signatários do Envelope, assinaram = aceites `clicksign`; como o
    modo interno implica aceite não-ClickSign, assinaram < total e o selo
    discreto do banner aparece). Retorna True se finalizou nesta chamada.

    Quadro sem ações conta como satisfeito: não há compromisso a colher e a
    Reunião não pode ficar presa em AGUARDANDO_ASSINATURA para sempre.
    """
    reuniao = _buscar_reuniao(supabase, id_reuniao)
    if not reuniao or reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA" or not reuniao.get("modo_interno_desde"):
        return False

    quadro = pendencia_service.extrair_quadro(reuniao.get("json_ata"))
    ocupadas = _posicoes_ocupadas(supabase, id_reuniao)
    if any(pos not in ocupadas for pos in range(len(quadro))):
        return False

    # Selo com base única: total e assinaram contados sobre o MESMO conjunto
    # (signatários do roster atual). Aceite clicksign sem correlação ou de
    # participante desativado fica fora dos dois lados: assinaram <= total
    # sempre, e o selo misto nunca some por contagem absurda.
    roster = _roster(supabase, id_reuniao)
    signatarios = _signatarios_envelope(roster)
    total = len(signatarios)
    aceites = (
        supabase.table("reuniao_aceites").select("participante_id, origem").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    assinaram = len(
        {
            a["participante_id"]
            for a in aceites
            if a.get("origem") == "clicksign" and a.get("participante_id") in signatarios
        }  # noqa: E501
    )

    # Guarda de concorrência: o UPDATE só afeta a Reunião ainda aguardando
    # (dois aceites simultâneos não re-finalizam um por cima do outro).
    resultado = (
        supabase.table("reunioes")
        .update(
            {
                "status_ata": "ASSINADA",
                "data_assinatura": datetime.now(UTC).date().isoformat(),
                "signatarios_total": total,
                "signatarios_assinaram": assinaram,
            }
        )
        .eq("id_reuniao", id_reuniao)
        .eq("status_ata", "AGUARDANDO_ASSINATURA")
        .execute()
    )
    if not resultado.data:
        return False
    logger.info(
        f"[AceiteService] ✅ Desfecho terminal do modo interno em {id_reuniao}: "
        f"toda ação com Pendência, ASSINADA com aceites mistos ({assinaram} de {total} no ClickSign)."
    )
    return True


def iniciar_coleta_interna(supabase, id_reuniao: str) -> dict:
    """Dispara (ou re-dispara) a coleta de Aceites internos no modo interno.

    Idempotente e re-invocável: roda na abertura do modo interno e de novo
    quando o quadro muda (ex.: ação reatribuída na edição parcial). Em ordem:

    1. Ações abertas de quem JÁ firmou compromisso (aceite registrado, de
       qualquer origem) nascem direto, com a regra do Facilitador (ADR 0030
       decisão 1: o aceite dele libera sem vínculo e não-signatários).
    2. Se toda ação do quadro tem Pendência, o desfecho terminal fecha a
       Reunião, sem emails.
    3. Cada signatário pendente cujo aceite ainda LIBERA algo (ações próprias
       abertas; para o Facilitador, também as sem vínculo/de não-signatários)
       recebe email com link público tokenizado (token opaco de uso único; só
       o hash é persistido). Signatário sem ação não recebe link nem trava o
       desfecho. Facilitador pendente recebe também notificação in-app.
       Se o email falha e nenhum canal chegou ao signatário, o token é
       removido para uma recoleta futura reemitir o link.

    Best-effort por destinatário: falha de email/notificação fica no log e
    não interrompe os demais (o caller já tratou o webhook como 200).
    """
    from app.services import notificacao_service, reuniao_email_service

    reuniao = _buscar_reuniao(supabase, id_reuniao)
    if not reuniao or reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA" or not reuniao.get("modo_interno_desde"):
        return {"emails_enviados": 0, "desfecho_terminal": False}

    roster = _roster(supabase, id_reuniao)
    signatarios = _signatarios_envelope(roster)
    facilitador_id = reuniao.get("facilitador_id")
    aceites = (
        supabase.table("reuniao_aceites").select("participante_id, email").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    aceitaram = {a["participante_id"] for a in aceites if a.get("participante_id")}
    emails_com_aceite = {(a.get("email") or "") for a in aceites if a.get("email")}

    quadro = _quadro_resolvido(supabase, id_reuniao, reuniao.get("json_ata"))
    ocupadas = _posicoes_ocupadas(supabase, id_reuniao)

    # 1. Compromisso já firmado libera direto (cobre ação reatribuída para quem
    # já aceitou e webhook `sign` perdido; idempotente por ação do quadro).
    fac_aceitou = bool(facilitador_id) and facilitador_id in aceitaram

    def _filtro_ja_firmados(acao: dict) -> bool:
        responsavel_id = acao.get("responsavel_id")
        if responsavel_id in aceitaram:
            return True
        return fac_aceitou and (responsavel_id is None or responsavel_id not in signatarios)

    if any(pos not in ocupadas and _filtro_ja_firmados(acao) for pos, acao in enumerate(quadro)):
        pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="ACEITE_RECOLETA", filtro=_filtro_ja_firmados)
        ocupadas = _posicoes_ocupadas(supabase, id_reuniao)

    # 2. Desfecho terminal: nada mais a colher.
    if all(pos in ocupadas for pos in range(len(quadro))):
        finalizou = verificar_desfecho_modo_interno(supabase, id_reuniao)
        return {"emails_enviados": 0, "desfecho_terminal": finalizou}

    # 3. Links de Aceite interno para quem ainda destrava algo.
    abertas = [acao for pos, acao in enumerate(quadro) if pos not in ocupadas]
    responsaveis_com_acao_aberta = {acao.get("responsavel_id") for acao in abertas if acao.get("responsavel_id")}
    ha_aberta_fora_do_envelope = any(
        acao.get("responsavel_id") is None or acao.get("responsavel_id") not in signatarios for acao in abertas
    )
    nomes = {
        p["id"]: p.get("nome_completo") or "Participante"
        for p in (
            supabase.table("participantes").select("id, nome_completo").in_("id", sorted(roster)).execute().data or []
        )
    }

    enviados = 0
    for pid, email in sorted(roster.items()):
        if not email:
            continue  # sem email = fora do Envelope, nunca foi signatário
        if pid in aceitaram or email in emails_com_aceite:
            continue  # já firmou compromisso
        eh_facilitador = bool(facilitador_id) and pid == facilitador_id
        libera_algo = pid in responsaveis_com_acao_aberta or (eh_facilitador and ha_aberta_fora_do_envelope)
        if not libera_algo:
            continue  # signatário sem ação não recebe link (ADR 0030)

        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        try:
            supabase.table("reuniao_aceite_tokens").insert(
                {"id_reuniao": id_reuniao, "participante_id": pid, "token_hash": token_hash}
            ).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            # Link já emitido numa coleta anterior (redelivery): não reenvia.
            logger.info(f"[AceiteService] Token de Aceite interno de {pid} em {id_reuniao} já emitido.")
            continue

        link = f"{settings.frontend_url}/aceite/{token}"
        email_ok = False
        try:
            email_ok = reuniao_email_service.enviar_email_aceite_interno(
                supabase, reuniao, nomes.get(pid, ""), email, link
            )
        except Exception as e:
            logger.error(f"[AceiteService] Falha best-effort no email de Aceite interno para {pid}: {e}")
        if email_ok:
            enviados += 1

        if eh_facilitador:
            try:
                notificacao_service.criar_notificacao_aceite_interno(
                    supabase,
                    destinatario_id=pid,
                    id_reuniao=id_reuniao,
                    titulo_reuniao=reuniao.get("titulo") or id_reuniao,
                )
            except Exception as e:
                logger.error(f"[AceiteService] Falha best-effort na notificação de Aceite interno para {pid}: {e}")
        elif not email_ok:
            # Nenhum canal chegou ao signatário: solta o token (o hash não é
            # recuperável) para a próxima coleta reemitir o link.
            try:
                supabase.table("reuniao_aceite_tokens").delete().eq("token_hash", token_hash).execute()
            except Exception as e:
                logger.error(f"[AceiteService] Falha ao soltar token não entregue de {pid}: {e}")

    logger.info(f"[AceiteService] Coleta interna de {id_reuniao}: {enviados} emails de Aceite interno enviados.")
    return {"emails_enviados": enviados, "desfecho_terminal": False}


def _carregar_token(supabase, token: str) -> tuple[dict, dict]:
    """Valida o token e devolve (registro do token, Reunião). Levanta
    TokenInvalidoError / TokenJaUsadoError / TokenExpiradoError sem nenhum efeito."""
    rows = (
        supabase.table("reuniao_aceite_tokens")
        .select("id, id_reuniao, participante_id, usado_em")
        .eq("token_hash", _hash_token(token))
        .execute()
        .data
        or []
    )
    if not rows:
        raise TokenInvalidoError()
    registro = rows[0]
    if registro.get("usado_em"):
        raise TokenJaUsadoError()
    reuniao = _buscar_reuniao(supabase, registro["id_reuniao"])
    if not reuniao or reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA" or not reuniao.get("modo_interno_desde"):
        raise TokenExpiradoError()
    return registro, reuniao


def reemitir_link_aceite_interno(supabase, id_reuniao: str, participante_id: str) -> str:
    """Devolve um link de Aceite interno vivo para o próprio signatário (issue #295).

    O sino do Facilitador precisa levar ao aceite, e a notificação não guarda
    mais o token: guardar o token em claro furava o invariante hash-only da
    tabela e, num vazamento do banco, entregava tokens utilizáveis.

    Como o banco só tem o SHA-256 (migration 060), não existe "ler o link de
    volta": o hash não volta ao token. O caminho é emitir um token novo e
    trocar o hash na linha que já existe, o que mantém o banco hash-only e
    preserva o uso único e o índice por (Reunião, signatário).

    Consequência assumida: o link que foi por email deixa de valer assim que o
    signatário usa o sino. É o mesmo dono, o mesmo aceite e um só uso, e o
    caminho autenticado é o mais forte dos dois.

    O par (Reunião, signatário) é a autorização: quem pede só recebe o link do
    token que é seu. Levanta TokenInvalidoError (não há token para essa pessoa
    nessa Reunião), TokenJaUsadoError ou TokenExpiradoError, sem nenhum efeito.
    """
    rows = (
        supabase.table("reuniao_aceite_tokens")
        .select("id, id_reuniao, participante_id, usado_em")
        .eq("id_reuniao", id_reuniao)
        .eq("participante_id", participante_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TokenInvalidoError()
    registro = rows[0]
    if registro.get("usado_em"):
        raise TokenJaUsadoError()
    reuniao = _buscar_reuniao(supabase, id_reuniao)
    if not reuniao or reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA" or not reuniao.get("modo_interno_desde"):
        raise TokenExpiradoError()

    token = secrets.token_urlsafe(32)
    supabase.table("reuniao_aceite_tokens").update({"token_hash": _hash_token(token)}).eq(
        "id", registro["id"]
    ).execute()
    logger.info(f"[AceiteService] Link de Aceite interno reemitido para {participante_id} em {id_reuniao}.")
    return token


def consultar_aceite_interno(supabase, token: str) -> dict:
    """Dados da página pública do Aceite interno: a ata completa (mesmo
    conteúdo do PDF preliminar, via json_ata) + quem está aceitando."""
    registro, reuniao = _carregar_token(supabase, token)
    participante = (
        supabase.table("participantes").select("nome_completo").eq("id", registro["participante_id"]).execute().data
        or []
    )
    return {
        "reuniao": {
            "titulo": reuniao.get("titulo"),
            "tipo": reuniao.get("tipo"),
            "data": reuniao.get("data"),
            "hora_inicio": reuniao.get("hora_inicio"),
        },
        "signatario": {"nome": (participante[0].get("nome_completo") if participante else "") or ""},
        "ata": reuniao.get("json_ata") or {},
    }


def registrar_aceite_interno(supabase, token: str) -> dict:
    """Registra o Aceite interno de um signatário pelo token do link público.

    Uso único garantido por claim atômico (UPDATE condicionado a
    `usado_em IS NULL`): reuso concorrente falha sem nenhum efeito. O aceite
    nasce com origem `aceite_interno` e timestamp; as Pendências do
    signatário nascem todas de uma vez (idempotente por ação do quadro); o
    desfecho terminal fecha a Reunião quando este era o último aceite
    necessário. Falha após o claim devolve o token (best-effort) para o link
    não queimar por erro transitório.
    """
    registro, reuniao = _carregar_token(supabase, token)
    id_reuniao = registro["id_reuniao"]
    participante_id = registro["participante_id"]

    claim = (
        supabase.table("reuniao_aceite_tokens")
        .update({"usado_em": datetime.now(UTC).isoformat()})
        .eq("id", registro["id"])
        .is_("usado_em", "null")
        .execute()
    )
    if not claim.data:
        raise TokenJaUsadoError()

    try:
        email_q = supabase.table("participantes").select("email").eq("id", participante_id).execute()
        email_norm = _normalizar_email((email_q.data or [{}])[0].get("email"))
        try:
            supabase.table("reuniao_aceites").insert(
                {
                    "id_reuniao": id_reuniao,
                    "participante_id": participante_id,
                    "signer_key": None,
                    "email": email_norm or None,
                    "origem": "aceite_interno",
                    "aceito_em": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            # Aceite já registrado por outra via (ex.: super admin): segue em
            # frente, a criação de Pendências abaixo é idempotente.
            logger.info(f"[AceiteService] Aceite de {participante_id} em {id_reuniao} já registrado por outra via.")

        # Mesma regra incremental da assinatura ClickSign (ADR 0030, decisão
        # 1): o aceite do Facilitador libera também as ações sem vínculo e as
        # de responsáveis fora do Envelope; sem isso, essas ações nunca
        # nasceriam no modo interno e o desfecho terminal ficaria preso.
        roster = _roster(supabase, id_reuniao)
        facilitador_id = reuniao.get("facilitador_id")
        eh_facilitador = bool(facilitador_id) and participante_id == facilitador_id
        filtro = _filtro_incremental(participante_id, eh_facilitador, _signatarios_envelope(roster))
        criadas = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="ACEITE_INTERNO", filtro=filtro)
        assinada = verificar_desfecho_modo_interno(supabase, id_reuniao)
    except Exception:
        supabase.table("reuniao_aceite_tokens").update({"usado_em": None}).eq("id", registro["id"]).execute()
        raise

    logger.info(
        f"[AceiteService] Aceite interno de {participante_id} em {id_reuniao}: "
        f"{criadas} Pendências criadas (reuniao_assinada={assinada})."
    )
    return {"pendencias_criadas": criadas, "reuniao_assinada": assinada}


# ─── Aceite manual do Super admin (ADR 0030 decisão 3, issue #278) ───────────


class ReuniaoNaoEncontradaError(Exception):
    """Reunião inexistente."""


class ModoInternoInativoError(Exception):
    """A Reunião não está na coleta interna de aceites (modo interno)."""


class SignatarioForaDaReuniaoError(Exception):
    """Participante que não pertence ao roster ativo da Reunião."""


def registrar_aceite_manual(supabase, id_reuniao: str, participante_id: str) -> dict:
    """Registra o aceite em nome de um signatário pendente (Super admin).

    Regra exclusiva do modo interno: o Envelope morreu e o Super admin destrava
    a ata registrando o compromisso pela pessoa que sumiu. O aceite nasce com
    origem `super_admin`; as Pendências do signatário nascem pela MESMA regra
    incremental do Aceite interno (o aceite do Facilitador libera também as
    ações de quem está fora do Envelope) e o desfecho terminal fecha a Reunião
    quando este era o último aceite necessário.

    Idempotente: signatário que já firmou compromisso (qualquer origem) não
    ganha aceite novo; a criação de Pendências é idempotente por ação do
    quadro. O retorno informa `ja_registrado` para o caller decidir o rastro
    de auditoria (só a primeira chamada audita).
    """
    reuniao = _buscar_reuniao(supabase, id_reuniao)
    if not reuniao:
        raise ReuniaoNaoEncontradaError()
    if reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA" or not reuniao.get("modo_interno_desde"):
        raise ModoInternoInativoError()

    roster = _roster(supabase, id_reuniao)
    if participante_id not in roster:
        raise SignatarioForaDaReuniaoError()
    email_norm = roster[participante_id]

    aceites = (
        supabase.table("reuniao_aceites").select("participante_id, email").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    ja_registrado = any(
        a.get("participante_id") == participante_id or (email_norm and (a.get("email") or "") == email_norm)
        for a in aceites
    )
    if not ja_registrado:
        try:
            supabase.table("reuniao_aceites").insert(
                {
                    "id_reuniao": id_reuniao,
                    "participante_id": participante_id,
                    "signer_key": None,
                    "email": email_norm or None,
                    "origem": "super_admin",
                    "aceito_em": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            # Corrida com outra via (Aceite interno ou webhook): já registrado.
            ja_registrado = True
            logger.info(f"[AceiteService] Aceite de {participante_id} em {id_reuniao} já registrado por outra via.")

    facilitador_id = reuniao.get("facilitador_id")
    eh_facilitador = bool(facilitador_id) and participante_id == facilitador_id
    filtro = _filtro_incremental(participante_id, eh_facilitador, _signatarios_envelope(roster))
    criadas = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="ACEITE_SUPER_ADMIN", filtro=filtro)
    assinada = verificar_desfecho_modo_interno(supabase, id_reuniao)

    nome_q = supabase.table("participantes").select("nome_completo").eq("id", participante_id).execute()
    nome = ((nome_q.data or [{}])[0].get("nome_completo")) or ""

    logger.info(
        f"[AceiteService] Aceite manual (super_admin) de {participante_id} em {id_reuniao}: "
        f"{criadas} Pendências criadas (ja_registrado={ja_registrado}, reuniao_assinada={assinada})."
    )
    return {
        "ja_registrado": ja_registrado,
        "pendencias_criadas": criadas,
        "reuniao_assinada": assinada,
        "signatario": {"id": participante_id, "nome": nome, "email": email_norm or None},
    }


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
