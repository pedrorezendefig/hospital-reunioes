"""Motor de prazos da Ouvidoria em calendário útil (issue #322, ADR 0034 decisão 6).

Módulo fundo e **puro**: recebe o instante de início, o prazo da gravidade e o
conjunto de feriados, e devolve o vencimento e o rótulo em linguagem natural.
Não lê banco, não consulta o relógio e não conhece HTTP. Quem carrega a tabela
de prazos e os feriados é a camada de rota; quem grava o vencimento é quem
valida a manifestação.
"""

from __future__ import annotations

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


def _vencimento_em_horas_uteis(inicio: datetime, horas: int, feriados: frozenset[date]) -> datetime:
    """Soma horas úteis andando pelo expediente, pulando noites e feriados."""
    momento = inicio
    restante = timedelta(hours=horas)
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
        vencimento = _vencimento_em_horas_uteis(abertura, prazo.valor, feriados)
    else:
        # Dia útil não conta o dia do fato: o dia 1 é o dia útil seguinte ao do
        # fato, contado a partir da data real da entrada e não da abertura da
        # contagem. Pular a partir da abertura pularia duas vezes para quem
        # chega fora do expediente, e sexta 17h30 ganharia um dia útil a menos
        # que sexta 16h50 (critério de aceite da #322).
        primeiro_dia = _proximo_dia_util(_em_sao_paulo(inicio).date(), feriados)
        vencimento = _vencimento_em_dias_uteis(primeiro_dia, prazo.valor, feriados)
    return vencimento.astimezone(UTC)


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
