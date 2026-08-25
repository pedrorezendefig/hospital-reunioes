"""Escada de escalonamento da Ouvidoria (issue #336, PRD #318, ADR 0034 decisão 12).

A cobrança sobe sozinha quando ninguém responde. São quatro degraus sobre o
calendário útil, calculados pelo motor de prazos (issue #331):

1. **Véspera** do vencimento: lembra o titular do setor.
2. **Vencimento**: cobra titular e substituto. Este degrau mora ao lado, em
   `ouvidoria_cobranca` (issue #327), porque foi entregue antes e tem o próprio
   carimbo (`prazo_rompido_em`). Os outros três moram aqui.
3. **+24h úteis** sem resposta: o gestor da área. Setor sem gestor cadastrado
   não faz o degrau sumir: ele vira o alerta à Diretoria Executiva.
4. **+48h úteis** sem resposta: a Diretoria Executiva.

Fora da escada de prazo, um quinto aviso: **caso crítico validado** notifica a
Diretoria Executiva na hora, sem esperar vencimento nenhum. Quem chama esse é a
validação (a rota), não o job.

Cada degrau tem coluna própria de carimbo em `ouvidoria_protocolos`, gravada
por update condicional (`IS NULL`) antes de qualquer email sair: rodar o job
duas vezes, ou duas rodadas concorrentes, não duplicam degrau. A ordem dos
passos protege o caso de ficar sem cobrança para sempre, no mesmo desenho da
issue #327: os destinatários são carregados ANTES do carimbo, e um carimbo cuja
notificação não gravou é desfeito.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio e os
feriados; aqui vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from app.services.ouvidoria_notificacoes import (
    GATILHO_CRITICO_IMEDIATO,
    GATILHO_ESCALONAMENTO_DIRETORIA,
    GATILHO_ESCALONAMENTO_GESTOR,
    GATILHO_VESPERA_VENCIMENTO,
    carregar_diretoria_executiva,
    despachar_agora_se_puder,
    quando_enviar,
    registrar,
)
from app.services.ouvidoria_prazos import FUSO, gatilhos_de_escalonamento
from app.services.ouvidoria_responsaveis import (
    CADEIA_DA_VESPERA,
    CADEIA_DO_GESTOR,
    Destinatario,
    destinatarios_nos_papeis,
)

logger = logging.getLogger(__name__)

AGUARDANDO_AREA = "aguardando_area"
PAPEL_DIRETORIA = "diretoria_executiva"

# Teto de degraus por rodada, no mesmo espírito do lote da issue #327: o
# primeiro tick depois do deploy acha todo o histórico vencido de uma vez, e o
# provedor de email não precisa engolir a rajada. O job roda de novo em 10
# minutos.
LOTE_POR_RODADA = 25

# Quantos casos a varredura lê. Folga grande de propósito: caso de setor sem
# ninguém para cobrar não é carimbado, volta na consulta a cada rodada e, por
# ser o mais antigo, vem sempre primeiro.
LEITURA_POR_RODADA = 200

# Até onde a varredura olha para frente. A véspera é um dia útil antes do
# vencimento, então um caso cujo degrau vence agora tem prazo a poucos dias de
# distância; a folga cobre feriado emendado sem ler a fila inteira.
HORIZONTE_DIAS = 15

_CAMPOS_DO_ESCALONAMENTO = (
    "id, protocolo, setor, gravidade, prazo_area_em, validada_em, "
    "vespera_avisada_em, escalonado_gestor_em, escalonado_diretoria_em"
)


@dataclass(frozen=True)
class Degrau:
    """Um degrau da escada: quando dispara, quem cobra e o que fica gravado.

    `carimbo` é a coluna de idempotência em `ouvidoria_protocolos`. `atributo` é
    o campo do resultado do motor de prazos que diz a hora do disparo."""

    nome: str
    carimbo: str
    atributo: str
    gatilho: str
    papeis: tuple[str, ...]
    observacao: str
    # Degrau que perde o sentido depois que o prazo estoura. Só a véspera é
    # assim: ela avisa que o prazo ESTÁ para vencer.
    caduca_no_vencimento: bool = False


VESPERA = Degrau(
    nome="véspera do vencimento",
    carimbo="vespera_avisada_em",
    atributo="vespera",
    gatilho=GATILHO_VESPERA_VENCIMENTO,
    papeis=CADEIA_DA_VESPERA,
    observacao="Véspera do vencimento: lembrete enviado ao titular do setor.",
    caduca_no_vencimento=True,
)

GESTOR = Degrau(
    nome="gestor da área",
    carimbo="escalonado_gestor_em",
    atributo="mais_24h",
    gatilho=GATILHO_ESCALONAMENTO_GESTOR,
    papeis=CADEIA_DO_GESTOR,
    observacao="Escalonamento: 24 horas úteis sem resposta, cobrança enviada ao gestor da área.",
)

DIRETORIA = Degrau(
    nome="Diretoria Executiva",
    carimbo="escalonado_diretoria_em",
    atributo="mais_48h",
    gatilho=GATILHO_ESCALONAMENTO_DIRETORIA,
    # A Diretoria não sai do cadastro de responsáveis do setor: ela vem do
    # perfil da Ouvidoria, como no alerta de setor sem titular do núcleo.
    papeis=(),
    observacao="Escalonamento: 48 horas úteis sem resposta, caso levado à Diretoria Executiva.",
)

# Na ordem em que a escada sobe. Caso abandonado desde a véspera sobe os três
# degraus na mesma rodada, cada um uma vez: o job não inventa história, ele
# conta o que já deveria ter acontecido.
DEGRAUS = (VESPERA, GESTOR, DIRETORIA)

# O que a Diretoria lê quando o degrau chegou nela um dia antes do previsto.
SEM_GESTOR = "O setor {setor} não tem gestor cadastrado na Ouvidoria, então este degrau subiu direto à Diretoria."


def escalar_prazos(supabase, agora: dt.datetime, feriados: frozenset[dt.date]) -> int:
    """Varre os casos aguardando área e sobe os degraus que já venceram.

    Devolve quantos degraus subiram nesta rodada."""
    horizonte = (agora + dt.timedelta(days=HORIZONTE_DIAS)).isoformat()
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DO_ESCALONAMENTO)
            .eq("status", AGUARDANDO_AREA)
            # A Diretoria é o último degrau: com ele subido, a escada acabou e
            # o caso sai da varredura. Sem este filtro, caso abandonado em
            # aguardando área ficaria ocupando a janela de leitura para sempre
            # e, passando do teto, nenhum caso novo entraria (mesmo cuidado do
            # `is_("prazo_rompido_em", "null")` da issue #327).
            #
            # A contrapartida: casa sem ninguém no perfil `diretoria_executiva`
            # nunca carimba o último degrau, e o caso segue sendo lido. É de
            # propósito, para não perder a cobrança por buraco de cadastro, e o
            # `logger.warning` de `_subir_degrau` é o rastro disso.
            .is_(DIRETORIA.carimbo, "null")
            .lte("prazo_area_em", horizonte)
            .order("prazo_area_em")
            .limit(LEITURA_POR_RODADA)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos aguardando área para o escalonamento")
        return 0

    subidos = 0
    for caso in result.data or []:
        if subidos >= LOTE_POR_RODADA:
            break
        pendentes = [d for d in DEGRAUS if caso.get(d.carimbo) is None]
        if not pendentes:
            continue
        gatilhos = _gatilhos_do_caso(caso, feriados)
        if gatilhos is None:
            continue
        for degrau in pendentes:
            if subidos >= LOTE_POR_RODADA:
                break
            quando = getattr(gatilhos, degrau.atributo)
            if quando is None or agora < quando:
                continue
            if degrau.caduca_no_vencimento and agora >= gatilhos.vencimento:
                # O primeiro tick depois do deploy acha o histórico vencido
                # inteiro sem carimbo nenhum, e o job parado por qualquer
                # motivo produz o mesmo efeito. Mandar "o prazo vence amanhã"
                # para quem já estourou seria mentira; quem cobra o vencido é o
                # degrau do vencimento (issue #327).
                continue
            if _subir_degrau(supabase, caso, degrau, agora, feriados):
                subidos += 1
    return subidos


def _gatilhos_do_caso(caso: dict, feriados: frozenset[dt.date]):
    """Os quatro instantes da escada para este caso, ou None quando não dá para
    calcular (caso sem prazo, sem marco de validação ou com data ilegível). Um
    caso torto não pode calar o escalonamento dos demais."""
    bruto = caso.get("prazo_area_em")
    inicio = caso.get("validada_em")
    if not bruto or not inicio:
        return None
    try:
        return gatilhos_de_escalonamento(
            dt.datetime.fromisoformat(str(inicio)),
            dt.datetime.fromisoformat(str(bruto)),
            feriados,
        )
    except ValueError:
        logger.error(
            "[Ouvidoria] Caso %s com prazo ou validação ilegível: %r / %r",
            caso.get("protocolo"),
            bruto,
            inicio,
        )
        return None


def _subir_degrau(supabase, caso: dict, degrau: Degrau, agora: dt.datetime, feriados: frozenset[dt.date]) -> bool:
    """Sobe um degrau: carimbo, notificações, movimento na trilha e entrega do
    que a janela comercial permitir. Devolve se o degrau subiu."""
    alvo = _destinatarios_do_degrau(supabase, caso, degrau, agora)
    if alvo is None:
        # Sem ninguém para cobrar hoje. Sem carimbo: quando o cadastro tiver
        # gente, a rodada seguinte sobe o degrau.
        logger.warning(
            "[Ouvidoria] Caso %s sem destinatário para o degrau %s (setor %s)",
            caso.get("protocolo"),
            degrau.nome,
            caso.get("setor"),
        )
        return False
    destinatarios, gatilho, detalhe = alvo

    if not _reivindicar_degrau(supabase, caso["id"], degrau, agora):
        return False

    quando = quando_enviar(agora, caso.get("gravidade"), feriados)
    criadas = []
    for destinatario in destinatarios:
        notificacao = registrar(
            supabase,
            manifestacao_id=caso["id"],
            gatilho=gatilho,
            destinatario_nome=destinatario.nome,
            destinatario_email=destinatario.email,
            papel_destinatario=destinatario.papel,
            enviar_a_partir_de=quando,
            detalhe=detalhe,
        )
        if notificacao:
            criadas.append(notificacao)

    if not criadas:
        # Nenhuma notificação gravou (ex.: schema de produção atrás do código).
        # Sem linha na fila não há cobrança nem botão de reenvio: devolve o
        # degrau para a próxima rodada em vez de queimá-lo em silêncio.
        logger.error("[Ouvidoria] Caso %s: nenhuma notificação do degrau %s gravou", caso.get("protocolo"), degrau.nome)
        _devolver_degrau(supabase, caso["id"], degrau, agora.isoformat())
        return False

    registrar_movimento(supabase, caso["id"], degrau.observacao)
    for notificacao in criadas:
        despachar_agora_se_puder(supabase, notificacao, agora, feriados)
    return True


def _destinatarios_do_degrau(
    supabase, caso: dict, degrau: Degrau, agora: dt.datetime
) -> tuple[list[Destinatario], str, str | None] | None:
    """Quem recebe este degrau, com que gatilho e com que contexto extra.

    None significa que não há ninguém hoje, que não é a mesma coisa que uma
    leitura falha: os dois adiam o degrau, e nenhum dos dois o queima."""
    if degrau is DIRETORIA:
        diretores = _diretoria(supabase)
        return (diretores, degrau.gatilho, None) if diretores else None

    responsaveis = _carregar_responsaveis(supabase, caso.get("setor") or "")
    if responsaveis is None:
        return None
    hoje = agora.astimezone(FUSO).date()
    destinatarios = destinatarios_nos_papeis(responsaveis, hoje, degrau.papeis)
    if destinatarios:
        return (destinatarios, degrau.gatilho, None)

    if degrau is not GESTOR:
        return None

    # Sem gestor cadastrado o degrau não some: vira o alerta à Diretoria, com o
    # motivo escrito, porque ela precisa saber por que o caso chegou nela um
    # dia antes do previsto.
    diretores = _diretoria(supabase)
    if not diretores:
        return None
    return (diretores, GATILHO_ESCALONAMENTO_DIRETORIA, SEM_GESTOR.format(setor=caso.get("setor") or ""))


def _diretoria(supabase) -> list[Destinatario]:
    return [
        Destinatario(
            nome=d.get("nome_completo") or d["email"],
            email=d["email"],
            papel=PAPEL_DIRETORIA,
            alerta_diretoria=True,
        )
        for d in carregar_diretoria_executiva(supabase)
    ]


def _carregar_responsaveis(supabase, setor: str) -> list[dict] | None:
    """O cadastro de quem responde pelo setor. None significa que a leitura
    falhou, que não é a mesma coisa que setor sem ninguém."""
    try:
        result = (
            supabase.table("ouvidoria_setor_responsaveis")
            .select("setor, papel, nome, email, vigencia_inicio, vigencia_fim")
            .eq("setor", setor)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carregar os responsáveis do setor %s", setor)
        return None
    return result.data or []


def _reivindicar_degrau(supabase, manifestacao_id: str, degrau: Degrau, agora: dt.datetime) -> bool:
    """Carimba a coluna do degrau antes de cobrar. O update é condicional
    (`IS NULL`): a segunda rodada do job, ou uma rodada concorrente, não acha
    caso para carimbar e não cobra de novo."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({degrau.carimbo: agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", AGUARDANDO_AREA)
            .is_(degrau.carimbo, "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o degrau %s do caso %s", degrau.nome, manifestacao_id)
        return False
    return bool(result.data)


def _devolver_degrau(supabase, manifestacao_id: str, degrau: Degrau, carimbo: str) -> None:
    """Desfaz o carimbo de um degrau cuja cobrança não chegou a existir, para a
    próxima rodada tentar de novo. Só apaga o carimbo desta execução, nunca o
    de outra rodada."""
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update({degrau.carimbo: None})
            .eq("id", manifestacao_id)
            .eq(degrau.carimbo, carimbo)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao devolver o degrau %s do caso %s", degrau.nome, manifestacao_id)


def registrar_movimento(supabase, manifestacao_id: str, observacao: str) -> None:
    """O degrau entra na trilha do caso. Não é transição de estado (o caso
    segue aguardando área), então o insert é direto, no molde do movimento de
    prazo rompido. O carimbo do degrau garante a vez única."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "estado_anterior": AGUARDANDO_AREA,
                "estado_novo": AGUARDANDO_AREA,
                "autor_id": None,
                "autor_nome": "Sistema (escalonamento)",
                "observacao": observacao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de escalonamento do caso %s", manifestacao_id)


# =====================================================================
# Caso crítico validado: a Diretoria sabe na hora (PRD #318, história 18)
# =====================================================================

OBSERVACAO_CRITICO = "Caso crítico validado: Diretoria Executiva avisada imediatamente."


def alertar_diretoria_caso_critico(
    supabase, manifestacao_id: str, agora: dt.datetime, feriados: frozenset[dt.date]
) -> None:
    """Avisa a Diretoria Executiva de um caso crítico recém validado.

    Não passa pela escada nem pela janela comercial: crítico é justamente o
    caso que não espera o expediente abrir, e `quando_enviar` já sabe disso. O
    carimbo `critico_avisado_em` garante um aviso só por caso, mesmo que a
    validação aconteça de novo depois de uma reabertura.

    Melhor esforço, como o alerta de setor sem titular: o acionamento da área
    já aconteceu quando esta função roda, e falhar aqui não pode desfazê-lo."""
    diretores = _diretoria(supabase)
    if not diretores:
        logger.warning("[Ouvidoria] Caso crítico %s sem Diretoria Executiva com email cadastrado", manifestacao_id)
        return

    if not _reivindicar_aviso_critico(supabase, manifestacao_id, agora):
        return

    criadas = []
    for diretor in diretores:
        notificacao = registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=GATILHO_CRITICO_IMEDIATO,
            destinatario_nome=diretor.nome,
            destinatario_email=diretor.email,
            papel_destinatario=PAPEL_DIRETORIA,
            enviar_a_partir_de=quando_enviar(agora, "critico", feriados),
        )
        if notificacao:
            criadas.append(notificacao)

    if not criadas:
        logger.error("[Ouvidoria] Caso crítico %s: nenhum aviso à Diretoria gravou", manifestacao_id)
        _desfazer_aviso_critico(supabase, manifestacao_id, agora.isoformat())
        return

    registrar_movimento(supabase, manifestacao_id, OBSERVACAO_CRITICO)
    for notificacao in criadas:
        despachar_agora_se_puder(supabase, notificacao, agora, feriados)


def _reivindicar_aviso_critico(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({"critico_avisado_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .is_("critico_avisado_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o aviso de caso crítico %s", manifestacao_id)
        return False
    return bool(result.data)


def _desfazer_aviso_critico(supabase, manifestacao_id: str, carimbo: str) -> None:
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update({"critico_avisado_em": None})
            .eq("id", manifestacao_id)
            .eq("critico_avisado_em", carimbo)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao devolver o aviso de caso crítico %s", manifestacao_id)
