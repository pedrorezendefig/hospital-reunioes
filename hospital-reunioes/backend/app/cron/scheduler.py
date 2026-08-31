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
  6. escalonar_prazos_ouvidoria: a cada 10 minutos, sobe os demais degraus da escada
     de escalonamento da Ouvidoria (véspera, gestor da área, Diretoria Executiva),
     issue #336. Idempotente: cada degrau tem o próprio carimbo.
  7. anonimizar_manifestacoes_antigas: 04:00 diário, apaga o Dossiê das manifestações
     encerradas há mais de cinco anos e preserva a estatística (issue #343).
     Idempotente: o caso anonimizado ganha carimbo e não é revisitado.
  8. enviar_relatorio_quinzenal: 07:00 diário, manda à Diretoria Executiva o relatório
     em PDF da quinzena que fechou (issue #345). O email sai nos dias 1 e 16, que é
     quando a quinzena fecha; os demais dias existem para a edição não se perder se o
     container estiver fora do ar na hora. Idempotente: o registro guarda quando o
     email saiu, e a segunda rodada da mesma quinzena não manda nada.
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


def escalonar_prazos_ouvidoria() -> None:
    """Sobe os degraus da escada de escalonamento da Ouvidoria (issue #336).

    Véspera do vencimento avisa o titular; 24h úteis sem resposta cobram o
    gestor da área (ou a Diretoria, quando o setor não tem gestor); 48h úteis
    levam o caso à Diretoria Executiva. Idempotente: cada degrau tem carimbo
    próprio e não sobe duas vezes."""
    from app.routers.ouvidoria import carregar_feriados
    from app.services import ouvidoria_escalonamento

    supabase = _supabase()
    try:
        subidos = ouvidoria_escalonamento.escalar_prazos(
            supabase, datetime.now(tz=ZoneInfo("UTC")), carregar_feriados(supabase)
        )
    except Exception as e:
        logger.error(f"[Cron] Erro em escalonar_prazos_ouvidoria: {e}", exc_info=True)
        return
    if subidos:
        logger.info(f"[Cron] {subidos} degrau(s) de escalonamento da Ouvidoria.")


def anonimizar_manifestacoes_antigas() -> None:
    """Aplica a retenção de cinco anos da Ouvidoria (issue #343).

    Manifestação encerrada há mais de cinco anos perde o Dossiê (relato,
    identificação de quem manifestou, anexos) e mantém o que os relatórios
    contam. Na prática o job nasce dormindo, porque nenhum caso tem cinco anos
    ainda, mas a política existe desde o primeiro dia. Idempotente: o carimbo
    `anonimizada_em` impede o segundo passe."""
    from app.services import ouvidoria_retencao

    supabase = _supabase()
    try:
        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, datetime.now(tz=ZoneInfo("UTC")))
    except Exception as e:
        logger.error(f"[Cron] Erro em anonimizar_manifestacoes_antigas: {e}", exc_info=True)
        return
    if anonimizadas:
        logger.info(f"[Cron] {anonimizadas} manifestação(ões) da Ouvidoria anonimizada(s) por retenção.")


def _registrar_entrega(competencia: str, entrega, rotulo: str = "Relatório quinzenal") -> None:
    """Escreve no log o que aconteceu com uma tentativa de entrega.

    São TRÊS estados, não dois. O do meio é o que some quando se pergunta só
    "saiu?": a entrega parcial sai para alguém e deixa outros de fora, e tratá-la
    como sucesso faz o log de produção dizer "enviado para 1 destinatário(s)"
    enquanto dois diretores não receberam nada. O motivo viaja em `entrega.erro`
    com os nomes de quem ficou de fora, e é este o único lugar por onde ele
    aparece fora do banco: o job não tem tela."""
    if entrega.saiu and entrega.erro:
        logger.warning(f"[Cron] {rotulo} {competencia} saiu INCOMPLETO: {entrega.erro}")
    elif entrega.saiu:
        logger.info(f"[Cron] {rotulo} {competencia} enviado para {len(entrega.entregues)} destinatário(s).")
    else:
        logger.error(f"[Cron] {rotulo} {competencia} não saiu: {entrega.erro}")


def enviar_relatorio_quinzenal() -> None:
    """Manda à Diretoria Executiva o relatório da quinzena que fechou (issue #345).

    Roda TODO DIA às 07h, e não só nos dias 1 e 16, embora seja nesses dois
    dias que a quinzena fecha e que o email sai. O motivo é que a edição é
    insubstituível: o jobstore do APScheduler é em memória, então um deploy do
    Coolify ou um restart do container em torno das 07h do dia 16 não adia o
    disparo, ele o descarta, e a próxima parada seria o dia 1 com OUTRA
    competência. A quinzena estaria perdida sem nenhum rastro além da ausência
    dela. Rodando todo dia, o dia 17 entrega o que o dia 16 não entregou.

    Nada disso repete email: a guarda continua sendo uma só, o `enviado_em` do
    registro daquela competência, e todo dia de 16 a 31 fecha a MESMA quinzena.

    A ESTREIA. No primeiro 07h depois do deploy, a Diretoria recebe a quinzena
    já fechada, seja que dia for. É decisão registrada, e não efeito colateral:
    aquele relatório é verdadeiro, de um período fechado, e chegar uma vez fora
    do calendário de 1 e 16 está tudo bem. A alternativa seria esperar a
    próxima virada, e o custo dela é a quinzena que ninguém nunca leria. Quem
    for "consertar" isso está apagando a decisão.

    Antes da edição do dia, a varredura das atrasadas: relatório gerado que não
    saiu (provedor fora do ar, render que estourou) volta para a fila em vez de
    esperar alguém abrir a listagem. A fila é lida por estado e tem teto de
    tentativas: a edição que falha em definitivo vira terminal, para de render
    PDF todo dia e passa a depender do reenvio pelo painel (issue #434)."""
    from app.services import ouvidoria_relatorio

    agora = datetime.now(tz=ZoneInfo("UTC"))
    try:
        supabase = _supabase()
        periodo = ouvidoria_relatorio.quinzena_encerrada(agora.astimezone(_TZ).date())
        competencia = ouvidoria_relatorio.competencia_de(ouvidoria_relatorio.QUINZENAL, periodo)
        try:
            for atrasado in ouvidoria_relatorio.entregar_atrasados(supabase, agora, exceto=competencia):
                _registrar_entrega(atrasado.registro["competencia"], atrasado, rotulo="Relatório atrasado")
        except Exception as e:
            # A varredura das atrasadas não pode impedir a edição do dia.
            logger.error(f"[Cron] Erro ao reentregar relatórios atrasados: {e}", exc_info=True)
        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, periodo, agora)
        if entrega is not None:
            _registrar_entrega(competencia, entrega)
    except Exception as e:
        logger.error(f"[Cron] Erro em enviar_relatorio_quinzenal: {e}", exc_info=True)


def enviar_relatorio_mensal() -> None:
    """Manda à Diretoria Executiva o relatório do mês que fechou (issue #346).

    Roda TODO DIA às 07h30, e não só no dia 1, pelo mesmo motivo do quinzenal:
    o jobstore do APScheduler é em memória, então um deploy em torno da hora do
    disparo DESCARTA a execução em vez de adiá-la, e o mês seria perdido sem
    outro rastro além da ausência dele. Rodando todo dia, o dia 2 entrega o que
    o dia 1 não entregou, e todo dia do mês fecha o MESMO mês anterior.

    Meia hora depois do quinzenal de propósito: os dois renderizam PDF com
    WeasyPrint, que é pesado, e no dia 1 as duas edições fecham juntas.

    A varredura de atrasados NÃO se repete aqui. A do job quinzenal não filtra
    tipo: uma edição mensal que foi gerada e não saiu já volta para a fila por
    lá, e duas varreduras tentariam a mesma linha duas vezes na mesma manhã.

    Este é o único job do sistema que chama IA externa. Falha dela não impede o
    envio: o relatório sai sem a seção de sugestões, com aviso no lugar."""
    from app.services import ouvidoria_relatorio

    agora = datetime.now(tz=ZoneInfo("UTC"))
    try:
        supabase = _supabase()
        periodo = ouvidoria_relatorio.mes_encerrado(agora.astimezone(_TZ).date())
        competencia = ouvidoria_relatorio.competencia_de(ouvidoria_relatorio.MENSAL, periodo)
        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, periodo, agora, tipo=ouvidoria_relatorio.MENSAL)
        if entrega is not None:
            _registrar_entrega(competencia, entrega, rotulo="Relatório mensal")
    except Exception as e:
        logger.error(f"[Cron] Erro em enviar_relatorio_mensal: {e}", exc_info=True)


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
    scheduler.add_job(
        escalonar_prazos_ouvidoria,
        "interval",
        minutes=10,
        id="escalonamento_ouvidoria",
        replace_existing=True,
    )
    # 04:00: fora da janela dos demais jobs e longe do expediente. A retenção
    # apaga dado em definitivo e não precisa disputar relógio com ninguém.
    scheduler.add_job(
        anonimizar_manifestacoes_antigas,
        "cron",
        hour=4,
        minute=0,
        id="retencao_ouvidoria",
        replace_existing=True,
    )
    # Todo dia às 07h, no fuso do scheduler (America/Sao_Paulo). A quinzena
    # fecha nos dias 1 e 16, e é neles que o email sai; os outros dias existem
    # para a edição não se perder quando o container estiver fora do ar na hora
    # (o jobstore é em memória: disparo perdido não é adiado, é descartado).
    # Repetição é impossível: a guarda é o `enviado_em` da competência.
    scheduler.add_job(
        enviar_relatorio_quinzenal,
        "cron",
        hour=7,
        minute=0,
        id="relatorio_quinzenal_ouvidoria",
        replace_existing=True,
    )
    scheduler.add_job(
        enviar_relatorio_mensal,
        "cron",
        hour=7,
        minute=30,
        id="relatorio_mensal_ouvidoria",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[Scheduler] APScheduler iniciado. Jobs: marcar_atrasadas (06:00), "
        "lembrete_24h_reunioes (a cada 15min), reconciliar_clicksign (05:30), "
        "notificacoes_ouvidoria (a cada 10min), cobranca_prazos_ouvidoria (a cada 10min), "
        "escalonamento_ouvidoria (a cada 10min), retencao_ouvidoria (04:00), "
        "relatorio_quinzenal_ouvidoria (07:00 diário, email nos dias 1 e 16)"
    )


def stop_scheduler() -> None:
    """Para o scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] APScheduler encerrado.")
