"""
Cron Jobs — APScheduler BackgroundScheduler

Jobs:
  1. marcar_atrasadas: 06:00 diário — pendências com prazo vencido → ATRASADO
"""

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from app.dependencies import get_supabase_client

logger = logging.getLogger(__name__)

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


def start_scheduler() -> None:
    """Inicia o BackgroundScheduler com os jobs configurados."""
    scheduler.add_job(marcar_atrasadas, "cron", hour=6, minute=0, id="marcar_atrasadas", replace_existing=True)
    scheduler.start()
    logger.info("[Scheduler] APScheduler iniciado — jobs: marcar_atrasadas (06:00)")


def stop_scheduler() -> None:
    """Para o scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] APScheduler encerrado.")
