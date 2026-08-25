"""
Cron Jobs — APScheduler BackgroundScheduler

Jobs:
  1. marcar_atrasadas: 06:00 diário — pendências com prazo vencido → ATRASADO
  2. enviar_lembretes_24h: a cada 15 minutos — reuniões PROGRAMADAS cujo horário cai dentro
     das proximas 24 horas e que ainda nao receberam o lembrete.
  3. reconciliar_clicksign: 05:30 diário, reconcilia Reuniões em AGUARDANDO_ASSINATURA
     com a ClickSign (ADR 0030, issue #279). Roda antes de marcar_atrasadas para que
     Pendências nascidas na reconciliação já entrem na checagem de atraso do dia.
  4. despachar_notificacoes_ouvidoria: a cada 10 minutos, entrega as notificações da
     Ouvidoria que já podem sair (issue #325). É por aqui que a notificação retida
     pela janela comercial sai na abertura do expediente e que a falha do Resend
     ganha nova tentativa.
  5. cobrar_prazos_ouvidoria: a cada 10 minutos, varre os casos aguardando área com
     prazo vencido e cobra PRAZO_ROMPIDO ao titular e ao substituto do setor
     (issue #327). Idempotente: o caso cobrado ganha carimbo e não é cobrado de novo.
"""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.dependencies import get_supabase_client
from app.services import reuniao_email_service

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Sao_Paulo")
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def _supabase():
    return get_supabase_client()


def marcar_atrasadas() -> None:
    """Marca como ATRASADO todas as pendências com prazo vencido ainda em PENDENTE."""
    supabase = _supabase()
    hoje = date.today().isoformat()
    try:
        result = (
            supabase.table("pendencias")
            .update({"status": "ATRASADO"})
            .eq("status", "PENDENTE")
            .lt("prazo", hoje)
            .execute()
        )
        atualizadas = len(result.data or [])
        if atualizadas:
            logger.info(f"[Cron] {atualizadas} pendências marcadas como ATRASADO.")
    except Exception as e:
        logger.error(f"[Cron] Erro em marcar_atrasadas: {e}", exc_info=True)


def enviar_lembretes_24h() -> None:
    """Envia lembrete por email aos participantes de reunioes que acontecem em aprox. 24h.

    Estrategia:
      1. Pre-filtra no Supabase reunioes PROGRAMADAS com lembrete pendente e data no intervalo
         [hoje, hoje + 1 dia + margem]. O index parcial idx_reunioes_lembrete_pendente cobre
         exatamente esse filtro.
      2. Em Python, compara (data + hora_inicio) - 24h com agora. Considera elegivel quando
         o ponto "24h antes" ja passou e o horario da reuniao ainda esta no futuro.
      3. Para cada elegivel, chama o service de email. Se ao menos um envio teve sucesso
         (ou nao havia destinatarios validos), marca a flag. Se o provider quebrou
         completamente, deixa para o tick seguinte.
    """
    supabase = _supabase()
    agora = datetime.now(tz=_TZ)
    hoje_iso = agora.date().isoformat()
    # +25h dá margem pra capturar reuniões da virada de dia mesmo se o job atrasar uns minutos.
    limite_iso = (agora + timedelta(hours=25)).date().isoformat()

    try:
        res = (
            supabase.table("reunioes")
            .select("id_reuniao, data, hora_inicio")
            .eq("status_ata", "PROGRAMADA")
            .is_("lembrete_24h_enviado_at", "null")
            .is_("deleted_at", "null")
            .gte("data", hoje_iso)
            .lte("data", limite_iso)
            .execute()
        )
    except Exception as e:
        logger.error(f"[Cron] Erro ao buscar reunioes para lembrete 24h: {e}", exc_info=True)
        return

    enviados = 0
    for row in res.data or []:
        if not row.get("hora_inicio"):
            continue
        try:
            inicio = datetime.fromisoformat(f"{row['data']}T{row['hora_inicio']}").replace(tzinfo=_TZ)
        except ValueError:
            logger.warning(f"[Cron] Reunião {row.get('id_reuniao')} com data/hora inválida; pulando.")
            continue

        ponto_24h = inicio - timedelta(hours=24)
        if not (ponto_24h <= agora < inicio):
            continue

        try:
            ok = reuniao_email_service.enviar_lembrete_24h(supabase, row["id_reuniao"])
            if ok:
                supabase.table("reunioes").update({"lembrete_24h_enviado_at": agora.isoformat()}).eq(
                    "id_reuniao", row["id_reuniao"]
                ).execute()
                enviados += 1
        except Exception as e:
            logger.error(
                f"[Cron] Erro inesperado ao processar lembrete da reunião {row.get('id_reuniao')}: {e}",
                exc_info=True,
            )

    if enviados:
        logger.info(f"[Cron] {enviados} lembrete(s) 24h enviado(s).")


def reconciliar_clicksign() -> None:
    """Reconcilia com a ClickSign as Reuniões em AGUARDANDO_ASSINATURA com Envelope.

    Documento fechado aplica o mesmo fluxo do webhook de fechamento; cancelado
    abre o modo interno (ADR 0030, issue #279). Idempotente: rodar de novo não
    duplica Pendência nem muda estado já resolvido.
    """
    from app.services import reconciliacao_service

    try:
        contadores = reconciliacao_service.reconciliar_pendentes(_supabase())
        if contadores["finalizada"] or contadores["modo_interno"]:
            logger.info(
                f"[Cron] Reconciliação ClickSign: {contadores['finalizada']} finalizada(s), "
                f"{contadores['modo_interno']} em modo interno."
            )
    except Exception as e:
        logger.error(f"[Cron] Erro em reconciliar_clicksign: {e}", exc_info=True)


def despachar_notificacoes_ouvidoria() -> None:
    """Entrega as notificações da Ouvidoria cuja hora chegou (issue #325).

    Duas filas caem aqui: a que esperou a janela comercial (notificação não
    crítica gerada fora do expediente) e a que falhou e voltou com backoff.
    Idempotente: o que já saiu está marcado como enviada e não é lido de novo."""
    from app.routers.ouvidoria import carregar_feriados
    from app.services import ouvidoria_notificacoes

    supabase = _supabase()
    try:
        entregues = ouvidoria_notificacoes.despachar_pendentes(
            supabase, datetime.now(tz=ZoneInfo("UTC")), carregar_feriados(supabase)
        )
    except Exception as e:
        logger.error(f"[Cron] Erro em despachar_notificacoes_ouvidoria: {e}", exc_info=True)
        return
    if entregues:
        logger.info(f"[Cron] {entregues} notificação(ões) da Ouvidoria entregue(s).")


def cobrar_prazos_ouvidoria() -> None:
    """Cobra os casos da Ouvidoria com prazo da área rompido (issue #327).

    O degrau do vencimento: titular e substituto recebem PRAZO_ROMPIDO e o
    movimento entra na trilha uma única vez por caso. Idempotente: o carimbo
    `prazo_rompido_em` impede cobrança dupla."""
    from app.routers.ouvidoria import carregar_feriados
    from app.services import ouvidoria_cobranca

    supabase = _supabase()
    try:
        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, datetime.now(tz=ZoneInfo("UTC")), carregar_feriados(supabase)
        )
    except Exception as e:
        logger.error(f"[Cron] Erro em cobrar_prazos_ouvidoria: {e}", exc_info=True)
        return
    if cobrados:
        logger.info(f"[Cron] {cobrados} caso(s) da Ouvidoria cobrado(s) por prazo rompido.")


def start_scheduler() -> None:
    """Inicia o BackgroundScheduler com os jobs configurados."""
    scheduler.add_job(marcar_atrasadas, "cron", hour=6, minute=0, id="marcar_atrasadas", replace_existing=True)
    scheduler.add_job(
        enviar_lembretes_24h,
        "interval",
        minutes=15,
        id="lembrete_24h_reunioes",
        replace_existing=True,
    )
    scheduler.add_job(
        reconciliar_clicksign,
        "cron",
        hour=5,
        minute=30,
        id="reconciliar_clicksign",
        replace_existing=True,
    )
    scheduler.add_job(
        despachar_notificacoes_ouvidoria,
        "interval",
        minutes=10,
        id="notificacoes_ouvidoria",
        replace_existing=True,
    )
    scheduler.add_job(
        cobrar_prazos_ouvidoria,
        "interval",
        minutes=10,
        id="cobranca_prazos_ouvidoria",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[Scheduler] APScheduler iniciado. Jobs: marcar_atrasadas (06:00), "
        "lembrete_24h_reunioes (a cada 15min), reconciliar_clicksign (05:30), "
        "notificacoes_ouvidoria (a cada 10min), cobranca_prazos_ouvidoria (a cada 10min)"
    )


def stop_scheduler() -> None:
    """Para o scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] APScheduler encerrado.")
