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
# A única unidade fora do Calendário útil (RN-56, ADR 0042). Existe para um
# marco só, o acuse de recebimento: ele é promessa ao paciente e corre em
# relógio de parede, então quem manifesta sexta à noite tem o aviso prometido
# para sábado à noite, e não para a terça de manhã. Toda a régua útil deste
# módulo (noite, fim de semana, feriado) fica de fora quando ela é a unidade.
HORAS_CORRIDAS = "horas_corridas"
UNIDADES = (DIAS_UTEIS, HORAS_UTEIS, HORAS_CORRIDAS)

# Teto da prorrogação, contado da entrada da manifestação (PRD #318).
TETO_PRORROGACAO_DIAS_UTEIS = 30


@dataclass(frozen=True)
class Prazo:
    """Uma célula da tabela de prazos por gravidade.

    `valor` None significa "sem prazo" (crítico não tem prazo conclusivo fixo;
    baixo não passa pela área), e o motor devolve vencimento None."""

    valor: int | None
    unidade: str = DIAS_UTEIS


def _e_dia_util(dia: date, feriados: frozenset[date]) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def _dia_util_vizinho(dia: date, feriados: frozenset[date], passo: int) -> date:
    """O primeiro dia útil estritamente adiante (`passo` 1) ou atrás (-1)."""
    vizinho = dia + timedelta(days=passo)
    while not _e_dia_util(vizinho, feriados):
        vizinho += timedelta(days=passo)
    return vizinho


def _proximo_dia_util(dia: date, feriados: frozenset[date]) -> date:
    """O primeiro dia útil estritamente depois de `dia`."""
    return _dia_util_vizinho(dia, feriados, 1)


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


def _vencimento_corrido(inicio: datetime, horas: int) -> datetime:
    """O vencimento de um prazo em horas CORRIDAS, em UTC.

    Nem feriados nem expediente entram aqui, e é esse o ponto: o único marco
    que usa esta régua é o acuse de recebimento, que é promessa ao paciente
    (RN-56, ADR 0042). Passar pelo Calendário útil faria a manifestação de
    sexta 22h ter o aviso prometido para a terça de manhã.

    Zero significa "ainda hoje", e não "já vencido": nas unidades úteis o zero
    quer dizer "sem esperar a próxima abertura do expediente", porque ali
    existe uma janela a esperar; no relógio de parede não existe janela
    nenhuma, e o que resta do dia é o prazo. É assim que a linha do crítico
    ("mesmo dia") cabe na mesma tabela editável, sem uma unidade só para ela.
    Quem manifesta 23h50 tem dez minutos, e não mais um dia: a promessa é o
    mesmo dia, e esticá-la seria o sistema prometendo em nome de outro."""
    momento = _em_sao_paulo(inicio)
    if horas == 0:
        fim_do_dia = datetime.combine(momento.date(), time(23, 59, 59), tzinfo=FUSO)
        return fim_do_dia.astimezone(UTC)
    return (momento + timedelta(hours=horas)).astimezone(UTC)


def calcular_vencimento(inicio: datetime, prazo: Prazo, feriados: frozenset[date]) -> datetime | None:
    """O vencimento do prazo, em UTC. None quando a gravidade não tem prazo."""
    if prazo.valor is None:
        return None
    if prazo.unidade not in UNIDADES:
        raise ValueError(f"Unidade de prazo desconhecida: {prazo.unidade}")

    if prazo.unidade == HORAS_CORRIDAS:
        return _vencimento_corrido(inicio, prazo.valor)

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


def minutos_do_prazo(prazo: Prazo) -> int | None:
    """O prazo inteiro traduzido para minutos de expediente. None quando a
    gravidade não tem prazo, como no resto do motor."""
    if prazo.valor is None:
        return None
    if prazo.unidade not in UNIDADES:
        raise ValueError(f"Unidade de prazo desconhecida: {prazo.unidade}")
    if prazo.unidade == HORAS_CORRIDAS:
        # Não existe conversão honesta: 24 horas corridas valem 9 horas de
        # expediente numa sexta e nenhuma num feriado. Quem chama aqui está
        # dando meio prazo à área ou medindo espera, e essas contas são todas
        # em tempo ÚTIL. Devolver um número aproximado seria pior que recusar,
        # porque a régua errada não denuncia a si mesma.
        raise ValueError("Prazo em horas corridas não vira minutos de expediente")
    por_unidade = MINUTOS_POR_DIA_UTIL if prazo.unidade == DIAS_UTEIS else 60
    return prazo.valor * por_unidade


def vencimento_apos_devolucao(devolucao: datetime, prazo_original: Prazo, feriados: frozenset[date]) -> datetime | None:
    """O vencimento novo quando a resposta volta por insuficiência, em UTC.

    A área ganha metade do prazo original da gravidade contada da devolução em
    diante: o prazo total vira o tempo já corrido mais essa metade, sem zerar
    o relógio (PRD #318, história 7). Gravidade sem prazo segue sem prazo."""
    minutos = minutos_do_prazo(prazo_original)
    if minutos is None:
        return None
    inicio = inicio_da_contagem(devolucao, feriados)
    return _avancar_tempo_util(inicio, timedelta(minutes=minutos / 2), feriados).astimezone(UTC)


def prorrogacao_dentro_do_teto(entrada: datetime, vencimento_proposto: datetime, feriados: frozenset[date]) -> bool:
    """Só o teto: o vencimento proposto não passa do trigésimo dia útil contado
    da entrada da manifestação (PRD #318).

    As outras duas regras da prorrogação (única e pedida antes de vencer)
    dependem do histórico do caso e não deste motor puro: quem decide o pedido
    checa as três, não só esta. A régua de dias úteis é a do vencimento comum:
    o dia 1 é o dia útil seguinte ao da entrada, e cada dia útil fecha às 17h."""
    teto = calcular_vencimento(entrada, Prazo(TETO_PRORROGACAO_DIAS_UTEIS), feriados)
    if teto is None:
        raise ValueError("Teto de prorrogação sem data: o motor não sabe decidir o pedido")
    return _em_sao_paulo(vencimento_proposto) <= _em_sao_paulo(teto)


def vencimento_prorrogado(
    entrada: datetime,
    prazo_atual: datetime,
    dias_uteis: int,
    feriados: frozenset[date],
) -> datetime | None:
    """O vencimento novo de uma prorrogação, em UTC, já limitado ao teto.

    Soma `dias_uteis` ao vencimento vigente mantendo a hora dele, e corta no
    trigésimo dia útil contado da entrada (PRD #318). None quando o teto não
    deixa espaço: caso cujo prazo já alcançou o limite não tem o que prorrogar,
    e devolver o teto ali encolheria ou repetiria o vencimento.

    Quem decide se o pedido é admissível (único e antes de vencer) é a rota,
    que conhece o histórico do caso: aqui mora só o calendário."""
    if dias_uteis <= 0:
        raise ValueError("Prorrogação sem dias úteis a somar: o motor não inventa prazo")
    atual = _em_sao_paulo(prazo_atual)
    dia = atual.date()
    for _ in range(dias_uteis):
        dia = _proximo_dia_util(dia, feriados)
    proposto = datetime.combine(dia, atual.timetz())

    teto = calcular_vencimento(entrada, Prazo(TETO_PRORROGACAO_DIAS_UTEIS), feriados)
    if teto is None:
        raise ValueError("Teto de prorrogação sem data: o motor não sabe prorrogar")
    proposto = min(proposto, _em_sao_paulo(teto))
    if proposto <= atual:
        return None
    return proposto.astimezone(UTC)


# O esforço mínimo antes de encerrar por abandono (PRD #318, história 11):
# duas tentativas de contato registradas e cinco dias úteis de espera desde a
# primeira delas.
TENTATIVAS_MINIMAS_DE_CONTATO = 2
ESPERA_DE_CONTATO_DIAS_UTEIS = 5


def contato_suficiente_para_encerrar(
    tentativas: Sequence[datetime],
    agora: datetime,
    feriados: frozenset[date],
) -> bool:
    """Se o ouvidor já pode encerrar por "sem retorno do manifestante".

    Duas condições, e as duas juntas: existem pelo menos duas tentativas de
    contato registradas, e a primeira delas tem pelo menos cinco dias úteis de
    idade. A espera é o que dá dente à regra: só contar tentativas deixaria
    duas ligações no mesmo minuto liberarem o encerramento, e o caso fecharia
    antes de o manifestante ter chance real de voltar.

    A régua é de dias ÚTEIS, como o resto do motor: quem tenta contato na
    sexta não ganha a espera de graça no fim de semana."""
    if len(tentativas) < TENTATIVAS_MINIMAS_DE_CONTATO:
        return False
    espera = minutos_uteis_entre(min(tentativas), agora, feriados)
    return espera >= ESPERA_DE_CONTATO_DIAS_UTEIS * MINUTOS_POR_DIA_UTIL


# O indicador de cumprimento do prazo da área (PRD #318). O consumo (painel,
# relatórios) é do PRD 3; aqui nasce o dado correto.
CUMPRIDO = "cumprido"
ESTOURADO = "estourado"
EM_PRAZO = "em_prazo"
SEM_PRAZO = "sem_prazo"


def cumprimento_da_area(
    vencimento: datetime | None,
    respondida_em: datetime | None,
    agora: datetime,
    estouro_consumado_em: datetime | None = None,
) -> str:
    """Como este caso entra no indicador de prazo da área.

    A régua é o vencimento VIGENTE, não o original: prorrogação aprovada move
    `prazo_area_em`, e por isso conta como cumprido sem caso especial nenhum.
    Vencido em silêncio conta como estouro, que é a outra metade da regra
    (PRD #318, história 5). Gravidade sem prazo fica fora da conta em vez de
    entrar como cumprida: contar como acerto inflaria o indicador.

    `respondida_em` é a resposta do ciclo CORRENTE. A devolução por
    insuficiência (#334) limpa o marco T2 justamente por isso: sem limpar, este
    cálculo diria "cumprido" para um caso que ainda deve resposta.

    `estouro_consumado_em` é a memória do estouro que a área já cometeu num
    ciclo anterior, e ela manda em tudo (issue #374). Sem ela, a mesma limpeza
    do marco T2 apagava o estouro junto: quem respondeu ATRASADO e mal voltava
    a ler "em_prazo" no ciclo seguinte, e responder mal virava um jeito de
    limpar a ficha. Gravidade sem prazo continua fora do indicador mesmo com
    estouro herdado: sem vencimento não há régua que o meça."""
    if vencimento is None:
        return SEM_PRAZO
    if estouro_consumado_em is not None:
        return ESTOURADO
    if respondida_em is not None:
        return CUMPRIDO if _em_sao_paulo(respondida_em) <= _em_sao_paulo(vencimento) else ESTOURADO
    return ESTOURADO if esta_vencido(vencimento, agora) else EM_PRAZO


def estouro_consumado(
    vencimento: datetime | None,
    respondida_em: datetime | None,
    agora: datetime,
    ja_consumado: datetime | None = None,
) -> datetime | None:
    """A memória do estouro depois de fechar um ciclo de resposta da área.

    Chamada quando o ciclo corrente termina e outro começa (a devolução por
    insuficiência), com o vencimento e a resposta que valiam ANTES de o prazo
    novo entrar. Devolve o instante do PRIMEIRO estouro do caso, que é o que
    `cumprimento_da_area` lê depois (issue #374).

    O instante é o VENCIMENTO que a área furou, não a hora em que a resposta
    atrasada chegou: são dois fatos diferentes, e é o primeiro que o nome da
    coluna promete. Guardar a hora da resposta faria os relatórios do PRD 3
    responderem "quando a área estourou" com um instante horas adiante do
    estouro, e `area_estourou_em - prazo_area_em` daria um número sem sentido
    (o prazo já foi empurrado pela devolução quando o relatório lê).

    Estouro que já estava gravado nunca é reescrito: a segunda devolução não
    pode empurrar o carimbo para frente, senão o último atraso passaria por
    primeiro. Ciclo cumprido não carimba nada, e é isso que impede a devolução
    de punir quem respondeu no prazo."""
    if ja_consumado is not None:
        return ja_consumado
    if cumprimento_da_area(vencimento, respondida_em, agora) != ESTOURADO:
        return None
    return vencimento


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

    Cada pausa é um par (início, retomada). O acumulado é o que a união dos
    intervalos cobre em minutos úteis: madrugada, fim de semana e feriado não
    contam, pelo mesmo calendário do resto do motor (PRD #318, issue #331).
    Intervalos sobrepostos (pausa registrada duas vezes sem a retomada do
    meio) contam uma vez só: descontar em dobro entregaria prazo de graça à
    área."""
    return sum(minutos_uteis_entre(inicio, fim, feriados) for inicio, fim in _unir(pausas))


def _unir(intervalos: Sequence[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Os intervalos fundidos onde se sobrepõem, em ordem cronológica."""
    unidos: list[tuple[datetime, datetime]] = []
    for inicio, fim in sorted(intervalos):
        if unidos and inicio <= unidos[-1][1]:
            anterior_inicio, anterior_fim = unidos[-1]
            unidos[-1] = (anterior_inicio, max(anterior_fim, fim))
        else:
            unidos.append((inicio, fim))
    return unidos


def minutos_uteis_da_area(
    inicio: datetime,
    fim: datetime,
    pausas: Sequence[tuple[datetime, datetime]],
    feriados: frozenset[date],
) -> int:
    """O tempo útil que conta contra a área no cálculo de cumprimento: o
    corrido entre `inicio` e `fim`, menos o acumulado aguardando o
    manifestante. Pausa que atravessa a janela (caso ainda pausado na hora da
    medição) só desconta o trecho dentro dela. Nunca negativo."""
    corrido = minutos_uteis_entre(inicio, fim, feriados)
    recortadas = [(max(p_inicio, inicio), min(p_fim, fim)) for p_inicio, p_fim in pausas]
    return max(corrido - minutos_uteis_pausados(recortadas, feriados), 0)


def adiar_vencimento(vencimento: datetime, minutos_uteis: int, feriados: frozenset[date]) -> datetime:
    """O vencimento empurrado para frente por `minutos_uteis` de expediente.

    Quem passa por aqui, e quem NÃO passa, porque este módulo rege todo
    vencimento em produção e um mapa errado custa caro:

    * `vencimento_apos_retomada` usa: a pausa aguardando o manifestante devolve
      à área exatamente o expediente que ela esperou.
    * As métricas do PRD #319 usam, para dar ao prazo conclusivo (que não tem
      coluna própria) o mesmo crédito que a operação já concedeu ao prazo da
      área.
    * `vencimento_apos_devolucao` **não** usa: ela tem régua própria (metade do
      prazo original da gravidade, contada da devolução).
    * `vencimento_prorrogado` **não** usa: a régua dela é outra (soma dias
      úteis mantendo a hora do vencimento vigente, e nem passa por minutos),
      além de cortar no teto de 30 dias úteis da entrada.

    Ou seja: corrigir um problema de calendário AQUI não corrige a devolução
    nem a prorrogação. As três portas de crédito são independentes.

    Crédito zero ou negativo devolve o vencimento intacto: não existe empurrar
    para trás."""
    if minutos_uteis <= 0:
        return _em_sao_paulo(vencimento).astimezone(UTC)
    inicio = inicio_da_contagem(vencimento, feriados)
    return _avancar_tempo_util(inicio, timedelta(minutes=minutos_uteis), feriados).astimezone(UTC)


def vencimento_apos_retomada(
    vencimento_atual: datetime,
    pausa_inicio: datetime,
    pausa_fim: datetime,
    feriados: frozenset[date],
) -> datetime:
    """O vencimento novo quando o caso volta de `aguardando_manifestante`.

    A área recebe de volta exatamente o expediente que passou esperando o
    manifestante: o vencimento anda para frente esse tanto de tempo útil, nem
    um minuto a mais (PRD #318, história 9). Empurrar o vencimento, em vez de
    descontar só na hora de medir o cumprimento, é o que faz a escada de
    cobrança parar de cobrar durante e depois da pausa: todo degrau lê
    `prazo_area_em`, e um deles cobraria a área por uma espera que não é dela.

    O tempo parado fora do expediente não conta, pelo mesmo calendário do resto
    do motor. Pausa inteira fora do expediente devolve o vencimento intacto."""
    return adiar_vencimento(vencimento_atual, minutos_uteis_pausados([(pausa_inicio, pausa_fim)], feriados), feriados)


@dataclass(frozen=True)
class GatilhosEscalonamento:
    """Os quatro momentos da escada de cobrança (PRD #318): véspera avisa o
    titular; vencimento, titular + substituto; +24h, o gestor da área; +48h,
    a Diretoria Executiva. Todos em UTC. `vespera` None quando o prazo é curto
    demais para ter véspera."""

    vespera: datetime | None
    vencimento: datetime
    mais_24h: datetime
    mais_48h: datetime


def gatilhos_de_escalonamento(
    inicio: datetime, vencimento: datetime | None, feriados: frozenset[date]
) -> GatilhosEscalonamento | None:
    """Onde cada degrau da escada cai no calendário útil. None quando a
    gravidade não tem prazo: sem vencimento não há o que cobrar.

    Cada degrau anda um dia útil e mantém a hora do vencimento: fim de semana
    e feriado não contam como as 24h/48h da spec, senão o gestor de um caso
    vencido na sexta seria cobrado no sábado, com o setor fechado. A véspera
    some quando cairia antes de `inicio`, o momento em que o relógio do caso
    começou: prazo de horas (crítico) não tem "vence amanhã" a avisar."""
    if vencimento is None:
        return None
    momento = _em_sao_paulo(vencimento)

    def _no_dia(dia: date) -> datetime:
        return datetime.combine(dia, momento.timetz())

    vespera = _no_dia(_dia_util_vizinho(momento.date(), feriados, -1))
    um_depois = _proximo_dia_util(momento.date(), feriados)
    dois_depois = _proximo_dia_util(um_depois, feriados)
    return GatilhosEscalonamento(
        vespera=vespera.astimezone(UTC) if vespera > _em_sao_paulo(inicio) else None,
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


# A frase que substitui o prazo quando a gravidade do caso não define nenhum.
# Uma só, e nos dois lugares: o rótulo e a data saem juntos na mesma linha da
# tela do responsável, e duas frases diferentes ali diriam a mesma coisa de
# dois jeitos (issue #513).
SEM_PRAZO_DEFINIDO = "sem prazo definido"


def rotular_vencimento(vencimento: datetime | None, agora: datetime, feriados: frozenset[date]) -> str:
    """A contagem regressiva em português que vai no painel e no email do setor
    (RN-35). Sempre em tempo útil: dizer "vence em 2 dias" quando o meio são
    dois fins de semana enganaria quem precisa responder."""
    if vencimento is None:
        return SEM_PRAZO_DEFINIDO
    if esta_vencido(vencimento, agora):
        return f"vencido há {_quantia_por_extenso(minutos_uteis_entre(vencimento, agora, feriados))}"
    return f"vence em {_quantia_por_extenso(minutos_uteis_entre(agora, vencimento, feriados))}"


def formatar_vencimento(vencimento: datetime | str | None) -> str:
    """A data e a hora do vencimento no fuso de quem lê, do jeito que o
    responsável de setor as lê.

    Ponto único das duas superfícies do mesmo prazo (issue #513): o email de
    acionamento e a tela do portal do setor chamam esta função, e por isso nunca
    formatam o mesmo vencimento de dois jeitos. A tela recebe o texto pronto
    porque o navegador não tem o fuso do hospital nem o calendário útil dele.

    Aceita o instante já lido ou o texto cru do banco: quem chama vem tanto da
    projeção do prazo (que já converteu) quanto do email (que tem a coluna na
    mão)."""
    if not vencimento:
        return SEM_PRAZO_DEFINIDO
    instante = vencimento if isinstance(vencimento, datetime) else datetime.fromisoformat(str(vencimento))
    return instante.astimezone(FUSO).strftime("%d/%m/%Y às %Hh%M")
