"""Motor de prazos da Ouvidoria em calendário útil (issue #322, ADR 0034 decisão 6).

Módulo fundo e **puro**: recebe o instante de início, o prazo da gravidade e o
conjunto de feriados, e devolve o vencimento e o rótulo em linguagem natural.
Não lê banco, não consulta o relógio e não conhece HTTP. Quem carrega a tabela
de prazos e os feriados é a camada de rota; quem grava o vencimento é quem
valida a manifestação.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# RN-22 da especificação da Diretoria: expediente de segunda a sexta, 08h às
# 17h, no fuso de São Paulo. O prazo é persistido em UTC.
FUSO = ZoneInfo("America/Sao_Paulo")
UTC = ZoneInfo("UTC")
ABERTURA = time(8, 0)
FECHAMENTO = time(17, 0)
# Derivado do expediente de propósito: mexer no horário acima não pode deixar a
# conversão de minutos para dias úteis dizendo outra coisa.
MINUTOS_POR_DIA_UTIL = (FECHAMENTO.hour - ABERTURA.hour) * 60 + (FECHAMENTO.minute - ABERTURA.minute)

DIAS_UTEIS = "dias_uteis"
HORAS_UTEIS = "horas_uteis"
UNIDADES = (DIAS_UTEIS, HORAS_UTEIS)


@dataclass(frozen=True)
class Prazo:
    """Uma célula da tabela de prazos por gravidade.

    `valor` None significa "sem prazo" (crítico não tem prazo conclusivo fixo;
    baixo não passa pela área), e o motor devolve vencimento None."""

    valor: int | None
    unidade: str = DIAS_UTEIS


def _e_dia_util(dia: date, feriados: frozenset[date]) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def _proximo_dia_util(dia: date, feriados: frozenset[date]) -> date:
    """O primeiro dia útil estritamente depois de `dia`."""
    seguinte = dia + timedelta(days=1)
    while not _e_dia_util(seguinte, feriados):
        seguinte += timedelta(days=1)
    return seguinte


def _em_sao_paulo(instante: datetime) -> datetime:
    if instante.tzinfo is None:
        raise ValueError("O motor de prazos só aceita instante com fuso: prazo sem fuso vence na hora errada")
    return instante.astimezone(FUSO)


def _abertura_de(dia: date) -> datetime:
    return datetime.combine(dia, ABERTURA, tzinfo=FUSO)


def _fechamento_de(dia: date) -> datetime:
    return datetime.combine(dia, FECHAMENTO, tzinfo=FUSO)


def inicio_da_contagem(instante: datetime, feriados: frozenset[date]) -> datetime:
    """Quando o relógio de horas úteis começa a andar (RN-23).

    Dentro do expediente, é o próprio instante. Fora dele (noite, fim de
    semana, feriado), é a próxima abertura: quem manifesta às 22h de sábado não
    consome prazo de madrugada."""
    momento = _em_sao_paulo(instante)
    dia = momento.date()
    if _e_dia_util(dia, feriados):
        if momento < _abertura_de(dia):
            return _abertura_de(dia)
        if momento < _fechamento_de(dia):
            return momento
    return _abertura_de(_proximo_dia_util(dia, feriados))


def _avancar_tempo_util(inicio: datetime, duracao: timedelta, feriados: frozenset[date]) -> datetime:
    """Soma tempo útil andando pelo expediente, pulando noites e feriados."""
    momento = inicio
    restante = duracao
    while restante > timedelta(0):
        fim_do_dia = _fechamento_de(momento.date())
        disponivel = fim_do_dia - momento
        if restante <= disponivel:
            return momento + restante
        restante -= disponivel
        momento = _abertura_de(_proximo_dia_util(momento.date(), feriados))
    return momento


def _vencimento_em_dias_uteis(primeiro_dia: date, dias: int, feriados: frozenset[date]) -> datetime:
    """Dia útil é dia inteiro: vence no fechamento do enésimo dia útil contado
    a partir de `primeiro_dia`, que é o dia 1."""
    dia = primeiro_dia
    for _ in range(dias - 1):
        dia = _proximo_dia_util(dia, feriados)
    return _fechamento_de(dia)


def calcular_vencimento(inicio: datetime, prazo: Prazo, feriados: frozenset[date]) -> datetime | None:
    """O vencimento do prazo, em UTC. None quando a gravidade não tem prazo."""
    if prazo.valor is None:
        return None
    if prazo.unidade not in UNIDADES:
        raise ValueError(f"Unidade de prazo desconhecida: {prazo.unidade}")

    abertura = inicio_da_contagem(inicio, feriados)
    if prazo.valor == 0:
        # "Imediato" na spec (triagem de caso crítico). Vale nas duas unidades:
        # zero dia útil não é o mesmo que um dia útil.
        return abertura.astimezone(UTC)
    if prazo.unidade == HORAS_UTEIS:
        vencimento = _avancar_tempo_util(abertura, timedelta(hours=prazo.valor), feriados)
    else:
        # Dia útil não conta o dia do fato: o dia 1 é o dia útil seguinte ao do
        # fato, contado a partir da data real da entrada e não da abertura da
        # contagem. Pular a partir da abertura pularia duas vezes para quem
        # chega fora do expediente, e sexta 17h30 ganharia um dia útil a menos
        # que sexta 16h50 (critério de aceite da #322).
        primeiro_dia = _proximo_dia_util(_em_sao_paulo(inicio).date(), feriados)
        vencimento = _vencimento_em_dias_uteis(primeiro_dia, prazo.valor, feriados)
    return vencimento.astimezone(UTC)


def _minutos_do_prazo(prazo: Prazo) -> int:
    """O prazo inteiro traduzido para minutos de expediente."""
    if prazo.unidade not in UNIDADES:
        raise ValueError(f"Unidade de prazo desconhecida: {prazo.unidade}")
    por_unidade = MINUTOS_POR_DIA_UTIL if prazo.unidade == DIAS_UTEIS else 60
    return prazo.valor * por_unidade


def vencimento_apos_devolucao(devolucao: datetime, prazo_original: Prazo, feriados: frozenset[date]) -> datetime | None:
    """O vencimento novo quando a resposta volta por insuficiência, em UTC.

    A área ganha metade do prazo original da gravidade contada da devolução em
    diante: o prazo total vira o tempo já corrido mais essa metade, sem zerar
    o relógio (PRD #318, história 7). Gravidade sem prazo segue sem prazo."""
    if prazo_original.valor is None:
        return None
    metade = timedelta(minutes=_minutos_do_prazo(prazo_original) / 2)
    inicio = inicio_da_contagem(devolucao, feriados)
    return _avancar_tempo_util(inicio, metade, feriados).astimezone(UTC)


TETO_PRORROGACAO_DIAS_UTEIS = 30


def prorrogacao_permitida(entrada: datetime, vencimento_proposto: datetime, feriados: frozenset[date]) -> bool:
    """A prorrogação respeita o teto: o vencimento proposto não pode passar do
    trigésimo dia útil contado da entrada da manifestação (PRD #318). A mesma
    régua de dias úteis do vencimento comum: o dia 1 é o dia útil seguinte ao
    da entrada, e cada dia útil fecha às 17h."""
    teto = calcular_vencimento(entrada, Prazo(TETO_PRORROGACAO_DIAS_UTEIS), feriados)
    return _em_sao_paulo(vencimento_proposto) <= _em_sao_paulo(teto)


def minutos_uteis_entre(inicio: datetime, fim: datetime, feriados: frozenset[date]) -> int:
    """Quantos minutos de expediente separam dois instantes. Zero quando `fim`
    não é depois de `inicio`: o motor não devolve tempo negativo."""
    momento = inicio_da_contagem(inicio, feriados)
    limite = _em_sao_paulo(fim)
    total = 0
    while momento < limite:
        fim_do_dia = _fechamento_de(momento.date())
        pedaco = min(fim_do_dia, limite) - momento
        total += int(pedaco.total_seconds() // 60)
        if fim_do_dia >= limite:
            break
        momento = _abertura_de(_proximo_dia_util(momento.date(), feriados))
    return max(total, 0)


def minutos_uteis_pausados(pausas: Sequence[tuple[datetime, datetime]], feriados: frozenset[date]) -> int:
    """Quanto tempo de expediente o caso passou aguardando o manifestante.

    Cada pausa é um par (início, retomada). O acumulado é a soma dos minutos
    úteis de cada intervalo: madrugada, fim de semana e feriado não contam,
    pelo mesmo calendário do resto do motor (PRD #318, issue #331)."""
    return sum(minutos_uteis_entre(inicio, fim, feriados) for inicio, fim in pausas)


def minutos_uteis_da_area(
    inicio: datetime,
    fim: datetime,
    pausas: Sequence[tuple[datetime, datetime]],
    feriados: frozenset[date],
) -> int:
    """O tempo útil que conta contra a área no cálculo de cumprimento: o
    corrido entre `inicio` e `fim`, menos o acumulado aguardando o
    manifestante. Nunca negativo."""
    corrido = minutos_uteis_entre(inicio, fim, feriados)
    return max(corrido - minutos_uteis_pausados(pausas, feriados), 0)


def _dia_util_anterior(dia: date, feriados: frozenset[date]) -> date:
    """O primeiro dia útil estritamente antes de `dia`."""
    anterior = dia - timedelta(days=1)
    while not _e_dia_util(anterior, feriados):
        anterior -= timedelta(days=1)
    return anterior


@dataclass(frozen=True)
class GatilhosEscalonamento:
    """Os quatro momentos da escada de cobrança (PRD #318): véspera avisa o
    titular; vencimento, titular + substituto; +24h, o gestor da área; +48h,
    a Diretoria Executiva. Todos em UTC."""

    vespera: datetime
    vencimento: datetime
    mais_24h: datetime
    mais_48h: datetime


def gatilhos_de_escalonamento(vencimento: datetime, feriados: frozenset[date]) -> GatilhosEscalonamento:
    """Onde cada degrau da escada cai no calendário útil.

    Cada degrau anda um dia útil e mantém a hora do vencimento: fim de semana
    e feriado não contam como as 24h/48h da spec, senão o gestor de um caso
    vencido na sexta seria cobrado no sábado, com o setor fechado."""
    momento = _em_sao_paulo(vencimento)

    def _no_dia(dia: date) -> datetime:
        return datetime.combine(dia, momento.timetz())

    um_depois = _proximo_dia_util(momento.date(), feriados)
    dois_depois = _proximo_dia_util(um_depois, feriados)
    return GatilhosEscalonamento(
        vespera=_no_dia(_dia_util_anterior(momento.date(), feriados)).astimezone(UTC),
        vencimento=momento.astimezone(UTC),
        mais_24h=_no_dia(um_depois).astimezone(UTC),
        mais_48h=_no_dia(dois_depois).astimezone(UTC),
    )


def esta_vencido(vencimento: datetime | None, agora: datetime) -> bool:
    """O prazo estourou. Gravidade sem prazo nunca estoura."""
    if vencimento is None:
        return False
    return _em_sao_paulo(agora) >= _em_sao_paulo(vencimento)


def _quantia_por_extenso(minutos: int) -> str:
    if minutos < 60:
        return "menos de 1 hora útil"
    if minutos < MINUTOS_POR_DIA_UTIL:
        horas = minutos // 60
        return f"{horas} hora útil" if horas == 1 else f"{horas} horas úteis"
    dias = minutos // MINUTOS_POR_DIA_UTIL
    return f"{dias} dia útil" if dias == 1 else f"{dias} dias úteis"


def rotular_vencimento(vencimento: datetime | None, agora: datetime, feriados: frozenset[date]) -> str:
    """A contagem regressiva em português que vai no painel e no email do setor
    (RN-35). Sempre em tempo útil: dizer "vence em 2 dias" quando o meio são
    dois fins de semana enganaria quem precisa responder."""
    if vencimento is None:
        return "sem prazo definido"
    if esta_vencido(vencimento, agora):
        return f"vencido há {_quantia_por_extenso(minutos_uteis_entre(vencimento, agora, feriados))}"
    return f"vence em {_quantia_por_extenso(minutos_uteis_entre(agora, vencimento, feriados))}"
