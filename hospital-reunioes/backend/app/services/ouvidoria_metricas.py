"""Módulo de métricas do período da Ouvidoria (issue #341, PRD #319).

A interface de agregação que responde, para qualquer intervalo de datas, os
números de gestão da Ouvidoria. O painel (fatia I2) e os relatórios (fatias I3
e I5) consomem esta MESMA função: é isso, e não disciplina de quem escreve as
telas, que impede o número do painel de divergir do número do PDF.

Duas camadas, de propósito:

* `agregar` é **pura**: recebe as linhas já lidas e devolve os números. Não
  conhece banco, HTTP nem relógio (o instante da medição entra por parâmetro).
* `metricas_do_periodo` é a casca fina que lê o banco e chama a pura. É por ela
  que o job do relatório entra, sem passar por HTTP.

Nenhum número é recalculado a partir de regra própria: o cumprimento do prazo
da área sai de `cumprimento_da_area`, o tempo útil sai de `minutos_uteis_entre`
e o vencimento sai de `calcular_vencimento`, os mesmos que o painel e a escada
de cobrança usam. Métrica com régua própria é métrica que discorda da operação.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from dataclasses import dataclass

from app.services.ouvidoria_prazos import (
    CUMPRIDO,
    EM_PRAZO,
    ESTOURADO,
    FUSO,
    MINUTOS_POR_DIA_UTIL,
    SEM_PRAZO,
    Prazo,
    calcular_vencimento,
    cumprimento_da_area,
    esta_vencido,
    minutos_uteis_entre,
)
from app.services.ouvidoria_prorrogacao import AGUARDANDO_AREA, entrada_da_manifestacao
from app.services.ouvidoria_responsaveis import escolher_destinatario

logger = logging.getLogger(__name__)

# Quantos itens entram nos "mais frequentes" (PRD #319, história 3).
TOPO = 5

# As colunas que a agregação lê. Fechada campo a campo como o resto do módulo:
# nada de dado pessoal do manifestante entra numa métrica.
CAMPOS_TUPLA = (
    "id",
    "protocolo",
    "data_abertura",
    "contato_em",
    "status",
    "categoria",
    "tipo_manifestacao",
    "setor",
    "canal",
    "gravidade",
    "prazo_area_em",
    "area_estourou_em",
    "validada_em",
    "respondida_em",
    "encerrada_em",
    "pausada_em",
    "minutos_pausados",
    "reincidencia",
    "reaberta_em",
)
CAMPOS = ", ".join(CAMPOS_TUPLA)


@dataclass(frozen=True)
class Periodo:
    """O intervalo medido, em datas do calendário civil (fuso do hospital).

    A régua é `data_abertura`, o dia do T0: é o dia em que a manifestação
    entrou, não o dia em que alguém a digitou."""

    inicio: dt.date
    fim: dt.date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    def anterior(self) -> Periodo:
        """O período de mesmo tamanho imediatamente antes deste. É contra ele
        que a variação é medida: comparar agosto com um julho parcial diria
        que a escuta cresceu quando só a janela encolheu."""
        fim = self.inicio - dt.timedelta(days=1)
        return Periodo(inicio=fim - dt.timedelta(days=self.dias - 1), fim=fim)

    def como_dict(self) -> dict:
        return {"inicio": self.inicio.isoformat(), "fim": self.fim.isoformat()}


def _instante(bruto) -> dt.datetime | None:
    return dt.datetime.fromisoformat(str(bruto)) if bruto else None


def _variacao_pct(atual: int, anterior: int) -> float | None:
    """A variação percentual frente ao período anterior. None quando o período
    anterior foi zero: dividir por zero ali viraria "infinito por cento", que
    não diz nada a quem lê o relatório."""
    if anterior == 0:
        return None
    return round((atual - anterior) * 100 / anterior, 1)


def _contagem(casos: list[dict], campo: str, anteriores: list[dict] | None = None) -> list[dict]:
    """A quebra de um campo em linhas ordenadas da maior para a menor. Valor
    ausente vira `nao_informado` em vez de sumir: caso sem tipo é o que falta
    classificar, e ele precisa aparecer."""
    atual = Counter(str(c.get(campo) or "nao_informado") for c in casos)
    passado = Counter(str(c.get(campo) or "nao_informado") for c in (anteriores or []))
    # A união das duas quebras, e não só as chaves do período atual: o canal que
    # existia antes e sumiu agora é notícia (caiu a zero), e listar apenas o
    # presente esconderia justamente a queda.
    linhas = [
        {
            "chave": chave,
            "total": atual.get(chave, 0),
            "anterior": passado.get(chave, 0),
            "variacao_pct": _variacao_pct(atual.get(chave, 0), passado.get(chave, 0)),
        }
        for chave in set(atual) | set(passado)
    ]
    return sorted(linhas, key=lambda linha: (-linha["total"], linha["chave"]))


def _volume(casos: list[dict], anteriores: list[dict]) -> dict:
    """O volume do período (PRD #319, histórias 2 e 16).

    `novos` tira os reincidentes: o caso reaberto é eco de um problema que já
    foi contado, e somá-lo de novo faria o número medir barulho em vez de
    problema. O total continua exposto ao lado, porque a operação precisa saber
    quanta tramitação houve."""
    reincidentes = [c for c in casos if c.get("reincidencia")]
    novos = len(casos) - len(reincidentes)
    novos_antes = len([c for c in anteriores if not c.get("reincidencia")])
    return {
        "total": len(casos),
        "anterior": len(anteriores),
        "variacao_pct": _variacao_pct(len(casos), len(anteriores)),
        "novos": novos,
        "novos_anterior": novos_antes,
        "novos_variacao_pct": _variacao_pct(novos, novos_antes),
        "reincidentes": len(reincidentes),
        "por_canal": _contagem(casos, "canal", anteriores),
        "por_tipo": _contagem(casos, "tipo_manifestacao", anteriores),
    }


# Os três trechos medidos (RN-21, ADR 0034 decisão 6). `marco` é a célula da
# tabela de prazos; `de` e `ate` são os marcos que o trecho separa; `responsavel`
# é de quem é o prazo, que é o que a Diretoria quer saber ao ver o número.
#
# Quem a issue #341 quer medir separadamente são a Ouvidoria e a área, e são os
# dois PRIMEIROS trechos que fazem isso: a triagem é da Ouvidoria e o T1→T2 é
# do setor. O conclusivo é o caso INTEIRO, e o rótulo diz isso com todas as
# letras (`T0`→`T3`, responsável `caso`) porque a régua dele é essa: a célula
# conclusiva da migration 065 é o total do caso ("conclusiva (T0 ate T3)"), não
# um orçamento que começa na resposta da área. Ler os 7 dias úteis do "médio"
# como tempo a partir do T2 daria à Ouvidoria mais prazo para fechar do que o
# caso inteiro tem para durar; e carimbar esse total como falha "da Ouvidoria"
# cobraria dela o atraso que a área causou. Por isso `de`/`ate`/`responsavel`
# viajam na resposta: quem desenha a tela lê a régua do dado, sem adivinhar.
TRECHOS = (
    {"trecho": "triagem", "marco": "triagem", "de": "T0", "ate": "T1", "responsavel": "ouvidoria"},
    {"trecho": "area", "marco": "area_resposta", "de": "T1", "ate": "T2", "responsavel": "area"},
    {"trecho": "conclusiva", "marco": "conclusiva", "de": "T0", "ate": "T3", "responsavel": "caso"},
)


def _medido_em(caso: dict, agora: dt.datetime) -> dt.datetime:
    """O instante contra o qual o caso ainda aberto é medido.

    Caso parado aguardando o manifestante mede tudo no instante em que parou, a
    mesma régua do painel (`_projetar_prazo`): medir contra o relógio de parede
    carimbaria falha contra a área por uma espera que não é dela."""
    return _instante(caso.get("pausada_em")) or agora


def _cumprimento_do_trecho(
    vencimento: dt.datetime | None,
    marco_em: dt.datetime | None,
    medido_em: dt.datetime,
    estouro_consumado_em: dt.datetime | None = None,
) -> str:
    """Como o caso entra no indicador daquele trecho.

    Delega ao motor de prazos de propósito: a regra de cumprimento (vencimento
    vigente, vencido em silêncio conta estouro, gravidade sem prazo fica fora)
    é a mesma nos três trechos, e ela vive num lugar só. O nome do motor fala
    da área porque foi ali que a regra nasceu (PRD #318); o que ele calcula é o
    trecho, não o setor."""
    return cumprimento_da_area(vencimento, marco_em, medido_em, estouro_consumado_em=estouro_consumado_em)


def _vencimento_do_trecho(
    caso: dict, trecho: dict, prazos: dict[tuple[str, str], Prazo], feriados: frozenset[dt.date]
) -> dt.datetime | None:
    """O vencimento daquele trecho para aquele caso.

    O trecho da área lê o vencimento PERSISTIDO (`prazo_area_em`) em vez de
    recalcular: ele já carrega a prorrogação aprovada e a devolução do tempo
    parado, e é o mesmo número que o setor recebeu por email. Recalcular aqui
    faria a métrica cobrar um prazo que ninguém comunicou.

    Triagem e conclusiva não têm coluna própria (o motor nunca precisou
    persisti-las), então saem da tabela de prazos contada a partir do T0.
    Gravidade ainda não decidida não tem célula: sem gravidade não há prazo, e
    o caso fica fora da conta em vez de entrar como acerto."""
    if trecho["marco"] == "area_resposta":
        return _instante(caso.get("prazo_area_em"))
    entrada = entrada_da_manifestacao(caso)
    prazo = prazos.get((str(caso.get("gravidade") or ""), trecho["marco"]))
    if entrada is None or prazo is None:
        return None
    return calcular_vencimento(entrada, prazo, feriados)


# O marco que fecha cada trecho.
_MARCO_QUE_FECHA = {"triagem": "validada_em", "area_resposta": "respondida_em", "conclusiva": "encerrada_em"}

ENCERRADO = "encerrado"


def _marco_que_fecha(caso: dict, trecho: dict) -> dt.datetime | None:
    """O instante em que o trecho fechou NESTE caso, ou None se ainda não fechou.

    O T3 só vale enquanto o caso está encerrado. A reabertura por reincidência
    preserva `encerrada_em` de propósito (é o marco da tramitação anterior, que
    os relatórios leem), mas o caso voltou a tramitar: lido cru, aquele carimbo
    faria o trecho conclusivo declarar CUMPRIDO um caso que está aberto agora, e
    reabrir viraria um jeito de fechar o indicador."""
    marco = _instante(caso.get(_MARCO_QUE_FECHA[trecho["marco"]]))
    if trecho["marco"] == "conclusiva" and caso.get("status") != ENCERRADO:
        return None
    return marco


def _prazo(
    casos: list[dict],
    prazos: dict[tuple[str, str], Prazo],
    feriados: frozenset[dt.date],
    agora: dt.datetime,
) -> dict:
    """O cumprimento de prazo separado por trecho (PRD #319, história 5).

    `percentual_cumprido` divide pelos MEDIDOS (cumpridos mais estourados), não
    pelo total de casos: quem ainda está dentro do prazo não é acerto nem erro,
    e contá-lo de qualquer um dos lados mentiria sobre o número."""
    linhas = []
    for trecho in TRECHOS:
        contagem = Counter()
        for caso in casos:
            vencimento = _vencimento_do_trecho(caso, trecho, prazos, feriados)
            marco_em = _marco_que_fecha(caso, trecho)
            estouro = _instante(caso.get("area_estourou_em")) if trecho["marco"] == "area_resposta" else None
            contagem[_cumprimento_do_trecho(vencimento, marco_em, _medido_em(caso, agora), estouro)] += 1
        medidos = contagem[CUMPRIDO] + contagem[ESTOURADO]
        linhas.append(
            {
                "trecho": trecho["trecho"],
                "de": trecho["de"],
                "ate": trecho["ate"],
                "responsavel": trecho["responsavel"],
                "medidos": medidos,
                "cumpridos": contagem[CUMPRIDO],
                "estourados": contagem[ESTOURADO],
                "em_andamento": contagem[EM_PRAZO],
                "sem_prazo": contagem[SEM_PRAZO],
                "percentual_cumprido": round(contagem[CUMPRIDO] * 100 / medidos, 1) if medidos else None,
            }
        )
    return {"trechos": linhas}


def _dias_uteis(minutos: float) -> float:
    """Minutos de expediente traduzidos para dias úteis, com uma casa. O dia
    útil tem 9 horas (RN-22), e é essa a régua que a Diretoria lê."""
    return round(minutos / MINUTOS_POR_DIA_UTIL, 1)


def _esta_com_a_area(caso: dict) -> bool:
    """O caso ainda deve resposta do setor. É o `status`, e não a ausência do
    marco T2, que decide: o caso pausado aguardando o manifestante e o já
    encerrado não são cobrança de ninguém."""
    return caso.get("status") == AGUARDANDO_AREA and not caso.get("respondida_em")


def _pendencias_por_area(
    casos: list[dict],
    responsaveis: list[dict],
    feriados: frozenset[dt.date],
    agora: dt.datetime,
) -> list[dict]:
    """O que cada área ainda deve, com nome e atraso (PRD #319, história 6).

    `dias_uteis_de_atraso` do setor é o do caso MAIS atrasado, não a soma nem a
    média: é o pior caso que mede o quanto aquela área já passou do combinado.

    O universo é o mesmo do resto do módulo, os casos abertos no período: quem
    quiser a fila viva pede um período que a alcance."""
    # A vigência de quem responde pelo setor é lida no dia do HOSPITAL: perto da
    # meia-noite o dia em UTC já é o seguinte, e o titular que entra amanhã
    # apareceria hoje.
    hoje = agora.astimezone(FUSO).date()
    por_setor: dict[str, list[dict]] = {}
    for caso in casos:
        if _esta_com_a_area(caso):
            por_setor.setdefault(str(caso.get("setor") or "nao_informado"), []).append(caso)

    linhas = []
    for setor, pendentes in por_setor.items():
        destinatario = escolher_destinatario([r for r in responsaveis if r.get("setor") == setor], hoje)
        atrasos = []
        for caso in pendentes:
            vencimento = _instante(caso.get("prazo_area_em"))
            medido_em = _medido_em(caso, agora)
            if vencimento is None or not esta_vencido(vencimento, medido_em):
                continue
            atrasos.append(
                {
                    "protocolo": caso.get("protocolo"),
                    "dias_uteis_de_atraso": _dias_uteis(minutos_uteis_entre(vencimento, medido_em, feriados)),
                }
            )
        linhas.append(
            {
                "setor": setor,
                "responsavel": destinatario.nome if destinatario else None,
                "pendentes": len(pendentes),
                "vencidas": len(atrasos),
                "dias_uteis_de_atraso": max((a["dias_uteis_de_atraso"] for a in atrasos), default=0.0),
                "casos_vencidos": sorted(atrasos, key=lambda a: -a["dias_uteis_de_atraso"]),
            }
        )
    return sorted(linhas, key=lambda linha: (-linha["dias_uteis_de_atraso"], -linha["pendentes"], linha["setor"]))


def _minutos_de_resposta(caso: dict, feriados: frozenset[dt.date]) -> int | None:
    """O tempo útil que a área levou entre o acionamento (T1) e a resposta
    (T2), JÁ SEM o tempo em que o caso esteve parado aguardando o manifestante
    (PRD #319, história 15).

    O desconto é a razão de ser deste cálculo: somar a espera ao tempo da área
    faria o ranking acusar de lenta a área que só ficou esperando o
    manifestante voltar. O tempo pausado é relatado à parte, nunca aqui.

    O relógio começa na reabertura quando ela existe, e não no T1 original: o
    caso reaberto recebeu prazo INTEIRO novo e zerou o acumulado de pausa, então
    medir do acionamento antigo entregaria à área o ciclo anterior inteiro, sem
    desconto nenhum, por uma resposta que ela deu em horas."""
    inicio = _instante(caso.get("reaberta_em")) or _instante(caso.get("validada_em"))
    fim = _instante(caso.get("respondida_em"))
    if inicio is None or fim is None:
        return None
    return max(minutos_uteis_entre(inicio, fim, feriados) - int(caso.get("minutos_pausados") or 0), 0)


def _ranking_areas(casos: list[dict], feriados: frozenset[dt.date]) -> list[dict]:
    """As áreas ordenadas da mais lenta para a mais rápida (PRD #319, história
    8). Só entra área que respondeu: média sobre nenhuma resposta não é zero,
    é ausência de número."""
    por_setor: dict[str, list[int]] = {}
    for caso in casos:
        minutos = _minutos_de_resposta(caso, feriados)
        if minutos is not None:
            por_setor.setdefault(str(caso.get("setor") or "nao_informado"), []).append(minutos)

    linhas = [
        {
            "setor": setor,
            "respondidas": len(medidas),
            "minutos_uteis_medios": round(sum(medidas) / len(medidas)),
            "dias_uteis_medios": _dias_uteis(sum(medidas) / len(medidas)),
        }
        for setor, medidas in por_setor.items()
    ]
    return sorted(linhas, key=lambda linha: (-linha["minutos_uteis_medios"], linha["setor"]))


def _prorrogacao(casos: list[dict], prorrogacoes: list[dict]) -> dict:
    """A taxa de prorrogação, geral e por área (PRD #319, história 7).

    Só pedido APROVADO conta: o negado e o pendente não moveram prazo nenhum, e
    contá-los diria que a área empurrou um prazo que ela não empurrou. O
    denominador é o trabalho que a área recebeu no período, e não os pedidos: a
    pergunta é que fatia dele precisou de mais tempo.

    "Recebeu" quer dizer ter vencimento de área (`prazo_area_em`). Caso ainda em
    classificação nunca chegou ao setor, e gravidade `baixo` não passa pela área
    por definição (a célula dela na tabela de prazos é nula): os dois no
    denominador diluiriam a taxa com trabalho que a área nunca teve como
    prorrogar."""
    aprovadas = {str(p.get("manifestacao_id")) for p in prorrogacoes if p.get("status") == "aprovada"}
    com_a_area = [caso for caso in casos if caso.get("prazo_area_em")]
    por_setor: dict[str, dict] = {}
    for caso in com_a_area:
        setor = str(caso.get("setor") or "nao_informado")
        linha = por_setor.setdefault(setor, {"setor": setor, "casos": 0, "prorrogados": 0})
        linha["casos"] += 1
        if str(caso.get("id")) in aprovadas:
            linha["prorrogados"] += 1

    for linha in por_setor.values():
        linha["taxa_pct"] = round(linha["prorrogados"] * 100 / linha["casos"], 1) if linha["casos"] else 0.0

    prorrogados = sum(linha["prorrogados"] for linha in por_setor.values())
    return {
        "casos": prorrogados,
        "com_a_area": len(com_a_area),
        "taxa_pct": round(prorrogados * 100 / len(com_a_area), 1) if com_a_area else 0.0,
        "por_area": sorted(por_setor.values(), key=lambda linha: (-linha["taxa_pct"], linha["setor"])),
    }


def _reincidencia(casos: list[dict]) -> dict:
    """A taxa de reincidência do período (PRD #319, história 8). Mede quanto do
    que chegou já tinha chegado antes."""
    reincidentes = len([c for c in casos if c.get("reincidencia")])
    return {
        "casos": reincidentes,
        "taxa_pct": round(reincidentes * 100 / len(casos), 1) if casos else 0.0,
    }


def _tempo_pausado(casos: list[dict], feriados: frozenset[dt.date], agora: dt.datetime) -> dict:
    """O tempo aguardando o manifestante, computado À PARTE (PRD #319, história
    15). Misturá-lo ao tempo de resposta esconderia lentidão real: o desconto já
    está dentro do vencimento, e sem este número ao lado a Diretoria veria o
    prazo esticado sem enxergar a espera que o esticou.

    O caso AINDA parado entra com a espera corrente, que não está no acumulado
    da coluna: sem ela, a pausa em curso apareceria como zero justo enquanto
    corre."""
    esperas = []
    for caso in casos:
        acumulado = int(caso.get("minutos_pausados") or 0)
        parada = _instante(caso.get("pausada_em"))
        corrente = minutos_uteis_entre(parada, agora, feriados) if parada else 0
        if acumulado + corrente > 0:
            esperas.append(acumulado + corrente)
    total = sum(esperas)
    return {
        "casos_com_pausa": len(esperas),
        "minutos_uteis_totais": total,
        "minutos_uteis_medios": round(total / len(esperas)) if esperas else 0,
        "dias_uteis_medios": _dias_uteis(total / len(esperas)) if esperas else 0.0,
    }


def _mais_frequentes(casos: list[dict], campo: str) -> list[dict]:
    """Os cinco mais frequentes daquele campo (PRD #319, história 3)."""
    return _contagem(casos, campo)[:TOPO]


def agregar(
    casos: list[dict],
    anteriores: list[dict],
    periodo: Periodo,
    agora: dt.datetime,
    prazos: dict[tuple[str, str], Prazo] | None = None,
    feriados: frozenset[dt.date] = frozenset(),
    responsaveis: list[dict] | None = None,
    prorrogacoes: list[dict] | None = None,
) -> dict:
    """Os números do período. Função pura: mesmas linhas, mesmos números."""
    return {
        "periodo": periodo.como_dict(),
        "periodo_anterior": periodo.anterior().como_dict(),
        "volume": _volume(casos, anteriores),
        "prazo": _prazo(casos, prazos or {}, feriados, agora),
        "pendencias_por_area": _pendencias_por_area(casos, responsaveis or [], feriados, agora),
        "ranking_areas": _ranking_areas(casos, feriados),
        "prorrogacao": _prorrogacao(casos, prorrogacoes or []),
        "reincidencia": _reincidencia(casos),
        "tempo_pausado": _tempo_pausado(casos, feriados, agora),
        "top_temas": _mais_frequentes(casos, "categoria"),
        "top_areas": _mais_frequentes(casos, "setor"),
    }


def _casos_do_periodo(supabase, periodo: Periodo) -> list[dict]:
    resultado = (
        supabase.table("ouvidoria_protocolos")
        .select(CAMPOS)
        .gte("data_abertura", periodo.inicio.isoformat())
        .lte("data_abertura", periodo.fim.isoformat())
        .execute()
    )
    return resultado.data or []


def _tabela_de_prazos(supabase) -> dict[tuple[str, str], Prazo]:
    """A tabela de prazos inteira, indexada por (gravidade, marco). Falha na
    leitura devolve tabela vazia, e aí todo trecho sem coluna própria fica sem
    prazo: melhor um indicador que se declara sem régua do que um número
    inventado."""
    try:
        resultado = supabase.table("ouvidoria_prazos").select("gravidade, marco, valor, unidade").execute()
    except Exception:
        logger.warning("Falha ao ler a tabela de prazos: os trechos sem coluna própria ficam sem régua")
        return {}
    return {
        (str(linha.get("gravidade")), str(linha.get("marco"))): Prazo(
            valor=linha.get("valor"), unidade=linha.get("unidade") or "dias_uteis"
        )
        for linha in (resultado.data or [])
    }


def _feriados(supabase) -> frozenset[dt.date]:
    """O calendário útil (RN-22). Como no painel, falha aqui não derruba o
    número: sem a lista o motor conta feriado como dia útil, o que erra para
    menos (cobra antes)."""
    try:
        resultado = supabase.table("ouvidoria_feriados").select("data").execute()
        linhas = resultado.data or []
        return frozenset(dt.date.fromisoformat(str(linha["data"])) for linha in linhas if linha.get("data"))
    except Exception:
        logger.warning("Falha ao carregar feriados: as métricas contam sem eles")
        return frozenset()


def _responsaveis(supabase) -> list[dict]:
    """O cadastro de quem responde por cada setor. É de onde sai o nome ao lado
    da pendência: cobrar setor não cobra ninguém."""
    try:
        resultado = (
            supabase.table("ouvidoria_setor_responsaveis")
            .select("id, setor, papel, nome, email, vigencia_inicio, vigencia_fim")
            .execute()
        )
        return resultado.data or []
    except Exception:
        logger.warning("Falha ao ler os responsáveis: as pendências saem sem nome")
        return []


def _prorrogacoes(supabase, casos: list[dict]) -> list[dict]:
    """Os pedidos de prorrogação dos casos do período. Sem casos não há o que
    perguntar, e um `in` de lista vazia é uma ida ao banco por nada."""
    ids = [str(caso.get("id")) for caso in casos if caso.get("id")]
    if not ids:
        return []
    try:
        resultado = (
            supabase.table("ouvidoria_prorrogacoes")
            .select("manifestacao_id, status")
            .in_("manifestacao_id", ids)
            .execute()
        )
        return resultado.data or []
    except Exception:
        logger.warning("Falha ao ler as prorrogações: a taxa do período sai zerada")
        return []


def metricas_do_periodo(supabase, periodo: Periodo, agora: dt.datetime) -> dict:
    """Lê o que a agregação precisa e devolve os números do período.

    É esta a porta do módulo: a rota HTTP e o job do relatório entram por aqui,
    e por isso leem exatamente o mesmo número."""
    casos = _casos_do_periodo(supabase, periodo)
    return agregar(
        casos=casos,
        anteriores=_casos_do_periodo(supabase, periodo.anterior()),
        periodo=periodo,
        agora=agora,
        prazos=_tabela_de_prazos(supabase),
        feriados=_feriados(supabase),
        responsaveis=_responsaveis(supabase),
        prorrogacoes=_prorrogacoes(supabase, casos),
    )
