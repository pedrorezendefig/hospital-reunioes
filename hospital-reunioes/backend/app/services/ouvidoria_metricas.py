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

Duas perguntas diferentes, dois universos, de propósito. Quase tudo aqui
responde "o que entrou no período". `pendencias_por_area` responde "o que está
pendente AGORA", e por isso lê a fila viva inteira, sem recorte de data: a área
com o caso mais atrasado do hospital não pode sumir do painel porque o caso
entrou no mês passado (issue #344, painel em tempo real).

O que não consegue ser lido vira `degradado` na resposta, nunca silêncio: num
módulo cujo propósito é painel e PDF não divergirem, número fabricado por falha
de leitura é o pior modo de falha.

Nenhum número é recalculado a partir de regra própria: o cumprimento do prazo
da área sai de `cumprimento_da_area`, o tempo útil sai de `minutos_uteis_entre`
e o vencimento sai de `calcular_vencimento`, os mesmos que o painel e a escada
de cobrança usam. Métrica com régua própria é métrica que discorda da operação.

Duas ressalvas do contrato, escritas porque as duas parecem defeito e não são
(issue #431, decisões da triagem de 28/08 na #399):

1. **A trilha de `ouvidoria_acessos`: a leitura agregada não registra linha
   nenhuma ali.** Mesma regra da listagem de índice, e decisão consciente, não
   omissão: a agregação não expõe caso individual (sem protocolo, sem relato,
   sem manifestante), então não há acesso a Dossiê para carimbar. Registrar
   cada abertura do painel encheria a tabela de ruído e enterraria a trilha
   que a ADR 0034 quer guardada, que é a do Dossiê. Quem abre o caso continua
   deixando rastro.

   A condição de validade, escrita para a decisão ser reaberta por gatilho e
   não por sorte: ela vale enquanto NENHUM bloco desta resposta identificar
   caso. O gatilho foi puxado na issue #432, e a premissa sobreviveu: os
   críticos abertos entraram como CONTAGEM por área (`pendencias_por_area
   []["criticos"]`), e não listados nominalmente. Contagem não é caso, então
   continua não havendo acesso a Dossiê para carimbar. O gatilho segue armado
   para o próximo bloco que tentar nomear caso.
2. **O universo é por DATA DE ENTRADA, e por isso o mesmo período responde
   números diferentes conforme o dia em que é pedido.** O caso aberto em 30/07
   e respondido em 05/08 entra no ranking de julho, mas só a partir de 05/08:
   o PDF de julho gerado em 01/08 e o painel mostrando julho em 10/08
   discordam, com a mesma fonte. Não é bug, é consequência de medir o que
   entrou na janela enquanto os casos dela continuam tramitando. A promessa de
   que painel e relatório não divergem vale para a mesma leitura no mesmo
   instante, e é por isso que o relatório arquiva os números que imprimiu.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from dataclasses import dataclass

from app.services.ouvidoria_estados import DESTINO_DA_DEVOLUCAO, e_devolucao
from app.services.ouvidoria_prazos import (
    CUMPRIDO,
    EM_PRAZO,
    ESTOURADO,
    FUSO,
    MINUTOS_POR_DIA_UTIL,
    SEM_PRAZO,
    Prazo,
    adiar_vencimento,
    calcular_vencimento,
    cumprimento_da_area,
    esta_vencido,
    minutos_do_prazo,
    minutos_uteis_entre,
)
from app.services.ouvidoria_prorrogacao import AGUARDANDO_AREA, entrada_da_manifestacao
from app.services.ouvidoria_responsaveis import nome_de_quem_responde
from app.services.ouvidoria_taxonomia import NAO_CLASSIFICADO_POR_CAMPO, TIPOS_MANIFESTACAO
from app.services.paginacao import ler_tudo

logger = logging.getLogger(__name__)

# Quantos itens entram nos "mais frequentes" (PRD #319, história 3).
#
# É o teto do eixo de ÁREA, que é texto livre: a lista não tem fim, e cortar em
# cinco é o que faz o ranking caber na página. O que fica de fora ali é cauda
# longa, e a frase do PDF diz quanto ela soma.
TOPO = 5

# O teto do eixo de TEMA é outro, e maior de propósito (issue #490). Tema é
# `tipo_manifestacao`, lista fechada: cortar ali não encurta cauda nenhuma,
# esconde um dos valores possíveis. E como a ordem é por frequência, quem some
# é sempre o menos frequente, que é justamente o tipo recém-criado, sem
# histórico: com `TOPO` nos dois eixos, `informacao` (ADR 0040) nasceria
# invisível no relatório do diretor e no prompt do relatório mensal, por meses.
#
# Derivado da lista, e não escrito à mão, para o sétimo tipo não reabrir o
# mesmo buraco em silêncio.
TETO_TEMAS = len(TIPOS_MANIFESTACAO)

# As colunas que a agregação lê. Fechada campo a campo como o resto do módulo:
# nada de dado pessoal do manifestante entra numa métrica, e campo sem
# consumidor sai da lista (issue #429). `categoria` saiu quando os temas
# passaram a sair de `tipo_manifestacao`.
CAMPOS_TUPLA = (
    "id",
    "data_abertura",
    "contato_em",
    "status",
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

    A régua é o T0 convertido para o fuso do hospital, e não `data_abertura`:
    aquela coluna é DATE com `DEFAULT CURRENT_DATE`, e nos canais automáticos
    (Ana e formulário público, o maior volume) ninguém a escreve. Com o banco em
    UTC, a manifestação feita às 22h de 31/08 nasceria carimbada 01/09 e sumiria
    do relatório de agosto. `contato_em` é TIMESTAMPTZ NOT NULL desde a migration
    066 e carrega o instante real; `data_abertura` fica de reserva para os casos
    antigos, exatamente como `entrada_da_manifestacao` já faz para o prazo."""

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


def dia_da_entrada(caso: dict) -> dt.date | None:
    """O dia do hospital em que a manifestação entrou, que é a régua do período.

    `entrada_da_manifestacao` já resolve a precedência (`contato_em` primeiro,
    `data_abertura` de reserva) e é a mesma função que o teto da prorrogação
    usa: o período e o prazo enxergam o mesmo T0."""
    entrada = entrada_da_manifestacao(caso)
    return entrada.astimezone(FUSO).date() if entrada else None


# A chave de agrupamento do caso que chegou sem área. Ela é CHAVE, e por isso
# é código de sistema: quem agrupa precisa de um valor estável, não de um nome
# bonito. Quem traduz é a apresentação, na tela (`rotuloDoSetor`, issue #437) e
# no PDF (`ouvidoria_relatorio._rotulo_do_setor`, issue #436).
#
# Vive aqui porque quem ESCREVE a chave é este módulo, e o backend inteiro passa
# a lê-la daqui. O frontend continua com a cópia dele da string
# (`lib/ouvidoria/painel.ts`), porque é outra stack: as duas ficam ligadas pela
# palavra que imprimem, não pela constante. Renomear a chave é mexer nos dois.
SETOR_NAO_INFORMADO = "nao_informado"

# A gravidade que a Diretoria quer ver contada à parte (issue #432). Constante
# aqui, e não literal solto no meio da agregação, porque o que ela vale é
# CONTRATO: o dia em que a taxonomia de gravidade mudar de palavra, a contagem
# de críticos precisa quebrar em um lugar só.
GRAVIDADE_CRITICA = "critico"


def _no_periodo(caso: dict, periodo: Periodo) -> bool:
    """O caso entrou nesta janela. Limites inclusivos nas duas pontas.

    Caso sem T0 legível fica de fora em vez de entrar em todo período: contá-lo
    em todos os relatórios seria pior do que não contá-lo em nenhum."""
    dia = dia_da_entrada(caso)
    return dia is not None and periodo.inicio <= dia <= periodo.fim


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
    atual = Counter(str(c.get(campo) or SETOR_NAO_INFORMADO) for c in casos)
    passado = Counter(str(c.get(campo) or SETOR_NAO_INFORMADO) for c in (anteriores or []))
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


def _prazo_da_triagem_nao_feita(prazos: dict[tuple[str, str], Prazo]) -> Prazo | None:
    """A régua do caso que ainda não foi triado: a MAIOR célula de triagem da
    tabela.

    `gravidade` só nasce na validação, no mesmo ato que carimba o T1. Sem uma
    régua aqui, o caso parado na fila cairia em `sem_prazo` e sairia do
    denominador, e o indicador SUBIRIA quanto pior fosse a Ouvidoria: dez casos
    com três triados no prazo e sete abandonados dariam "triagem: 100%", contra
    30% se os sete tivessem sido triados com atraso. O que some do denominador
    é justamente o conjunto das falhas.

    A maior célula é a escolha que não chuta gravidade nenhuma: passou daquilo,
    o caso estourou o prazo de triagem com QUALQUER gravidade que venha a
    receber. Antes disso ele ainda pode estar dentro do prazo de alguma, e fica
    em andamento."""
    celulas = [prazo for (_gravidade, marco), prazo in prazos.items() if marco == "triagem" and prazo.valor is not None]
    if not celulas:
        return None
    # `minutos_do_prazo` é a do motor de prazos, não uma cópia local: ela
    # devolve None para célula vazia, e o filtro acima é a ÚNICA guarda disso,
    # de propósito. Um `or 0` aqui seria uma segunda guarda que esconde a
    # primeira: com as duas, remover qualquer uma passa despercebido. Sem ele,
    # quem tirar o filtro comparará None com int e o `max` estoura na hora, que
    # é o que se quer de uma régua escolhida errado.
    return max(celulas, key=minutos_do_prazo)


def _credito_ja_concedido(caso: dict, prorrogacao: dict | None, feriados: frozenset[dt.date]) -> int:
    """Quantos minutos de expediente a operação JÁ devolveu a este caso.

    Duas fontes, as duas com número durável no banco: o tempo que o caso passou
    aguardando o manifestante (`minutos_pausados`, que a retomada já somou ao
    `prazo_area_em`) e a prorrogação aprovada (a distância entre o prazo
    anterior e o novo, gravada no próprio pedido).

    A devolução por insuficiência NÃO entra: ali ninguém concedeu tempo ao caso,
    a resposta é que teve de ser refeita, e esse tempo é do caso mesmo."""
    credito = int(caso.get("minutos_pausados") or 0)
    if prorrogacao and prorrogacao.get("status") == "aprovada":
        antes = _instante(prorrogacao.get("prazo_anterior"))
        depois = _instante(prorrogacao.get("prazo_novo"))
        if antes and depois:
            credito += minutos_uteis_entre(antes, depois, feriados)
    return credito


def _vencimento_do_trecho(
    caso: dict,
    trecho: dict,
    prazos: dict[tuple[str, str], Prazo],
    feriados: frozenset[dt.date],
    prorrogacao: dict | None = None,
) -> dt.datetime | None:
    """O vencimento daquele trecho para aquele caso.

    O trecho da área lê o vencimento PERSISTIDO (`prazo_area_em`) em vez de
    recalcular: ele já carrega a prorrogação aprovada e a devolução do tempo
    parado, e é o mesmo número que o setor recebeu por email. Recalcular aqui
    faria a métrica cobrar um prazo que ninguém comunicou.

    Triagem e conclusiva não têm coluna própria (o motor nunca precisou
    persisti-las), então saem da tabela de prazos contada a partir do T0.

    O conclusivo recebe DEPOIS o mesmo crédito que a operação já concedeu ao
    prazo da área. Sem isso, prorrogação aprovada pela Diretoria e espera pelo
    manifestante moveriam só `prazo_area_em`, e o mesmo caso sairia CUMPRIDO no
    trecho da área e ESTOURADO no conclusivo: o PDF acusaria de atraso um prazo
    que a própria Diretoria estendeu, e a espera do manifestante viraria falha
    do caso. O empurrão usa `adiar_vencimento`, o mesmo tijolo da retomada da
    pausa, e não uma régua nova.

    Caso ainda não triado não tem gravidade e por isso não tem célula: a
    triagem cai na maior célula da tabela (ver `_prazo_da_triagem_nao_feita`) e
    o conclusivo fica sem régua, porque ali não existe "maior" que sirva (a
    célula do crítico é nula de propósito)."""
    if trecho["marco"] == "area_resposta":
        return _instante(caso.get("prazo_area_em"))
    entrada = entrada_da_manifestacao(caso)
    if entrada is None:
        return None
    gravidade = str(caso.get("gravidade") or "")
    prazo = prazos.get((gravidade, trecho["marco"]))
    if prazo is None and trecho["marco"] == "triagem" and not caso.get("validada_em"):
        prazo = _prazo_da_triagem_nao_feita(prazos)
    if prazo is None:
        return None
    vencimento = calcular_vencimento(entrada, prazo, feriados)
    if vencimento is None or trecho["marco"] != "conclusiva":
        return vencimento
    return adiar_vencimento(vencimento, _credito_ja_concedido(caso, prorrogacao, feriados), feriados)


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
    prorrogacoes: dict[str, dict],
) -> dict:
    """O cumprimento de prazo separado por trecho (PRD #319, história 5).

    `percentual_cumprido` divide pelos MEDIDOS (cumpridos mais estourados), não
    pelo total de casos: quem ainda está dentro do prazo não é acerto nem erro,
    e contá-lo de qualquer um dos lados mentiria sobre o número."""
    linhas = []
    for trecho in TRECHOS:
        contagem = Counter()
        for caso in casos:
            vencimento = _vencimento_do_trecho(caso, trecho, prazos, feriados, prorrogacoes.get(str(caso.get("id"))))
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
    """O que cada área ainda deve AGORA, com nome e atraso (PRD #319, história 6).

    `dias_uteis_de_atraso` do setor é o do caso MAIS atrasado, não a soma nem a
    média: é o pior caso que mede o quanto aquela área já passou do combinado.

    Este é o único bloco com universo próprio: a fila viva inteira, sem recorte
    de data. A pergunta aqui não é "o que entrou no período" e sim "o que está
    pendente agora", e as duas divergem justamente onde dói: o caso aberto em
    julho e vencido desde julho não apareceria no painel de agosto, e a área com
    o caso mais atrasado do hospital sairia com zero pendências. A issue #344
    pede painel em tempo real lendo DESTE módulo; com recorte de período isso
    seria impossível, e a tela acabaria montando régua própria, que é o que esta
    fatia existe para impedir.

    Nenhum caso é identificado na saída: só contagem, o nome de quem responde
    pelo setor e o atraso, que é o que a issue pede. Devolver protocolo aqui
    entregaria caso a caso (denúncia sigilosa inclusive) a um objeto que a fatia
    I5 manda por email a gestor de área, e o gestor cruzaria o protocolo com o
    email de acionamento que ele mesmo recebeu (RN-40, ADR 0034 decisão 8).

    `criticos` conta quantos daqueles pendentes são de gravidade crítica
    (issue #432, decisão 3 da triagem de 28/08 registrada na #399). Ele nasce
    NESTE bloco, e não num universo próprio de "todo caso crítico ainda não
    encerrado", por duas razões:

    * O crítico que já foi respondido, ou que ainda está na triagem sem área
      decidida, não é cobrança de área nenhuma. "Crítico aberto NA ÁREA" é
      exatamente a fila viva, que é o que este bloco já mede.
    * Um terceiro universo na mesma resposta é o defeito que o docstring do
      módulo abre avisando. Aqui ele custaria uma leitura nova, uma nova
      superfície de degradação, e devolveria à Diretoria um número que não
      casa com a coluna ao lado.

    A ressalva 1 do docstring do módulo continua de pé: contagem não é caso, e
    o piso de contagem (k-anonimato) segue fora daqui de propósito, porque o
    recorte por área é decisão da fatia I5. Enquanto o PDF só vai à Diretoria
    Executiva, ele entrega estritamente menos do que a tela já entrega a ela.

    Cada linha carrega `medido_em`, o instante contra o qual aquela fila foi
    medida (issue #431). Quem precisa dele é o painel ao vivo (issue #344), que
    lê esta resposta crua: o relatório já resolveu o problema do lado dele, com
    um `medido_em` no registro que o PDF imprime. Sem o carimbo, uma tela que
    mostra julho embaixo de uma fila de setembro não tem como datar a fila.

    O carimbo vai na LINHA, e não num invólucro em volta da lista, porque a
    forma deste bloco é contrato: os relatórios já arquivados guardam
    `dados["pendencias_por_area"]` como lista congelada, e trocá-la por um
    objeto quebraria a reemissão do PDF deles (issue #345).

    Consequência assumida: fila vazia é lista vazia, e lista vazia não carrega
    instante nenhum. Quem precisar datar a AUSÊNCIA de pendência tem o carimbo
    do registro (no relatório) ou o instante da própria resposta (no painel);
    inventar aqui um segundo `medido_em` no topo criaria um terceiro carimbo
    com um terceiro escopo na mesma família de objetos, que é justamente a
    confusão que o campo existe para desfazer."""
    # A vigência de quem responde pelo setor é lida no dia do HOSPITAL: perto da
    # meia-noite o dia em UTC já é o seguinte, e o titular que entra amanhã
    # apareceria hoje.
    hoje = agora.astimezone(FUSO).date()
    por_setor: dict[str, list[dict]] = {}
    for caso in casos:
        if _esta_com_a_area(caso):
            por_setor.setdefault(str(caso.get("setor") or SETOR_NAO_INFORMADO), []).append(caso)

    linhas = []
    for setor, pendentes in por_setor.items():
        responsavel = nome_de_quem_responde([r for r in responsaveis if r.get("setor") == setor], hoje)
        atrasos = []
        for caso in pendentes:
            vencimento = _instante(caso.get("prazo_area_em"))
            medido_em = _medido_em(caso, agora)
            if vencimento is None or not esta_vencido(vencimento, medido_em):
                continue
            atrasos.append(_dias_uteis(minutos_uteis_entre(vencimento, medido_em, feriados)))
        linhas.append(
            {
                "setor": setor,
                "responsavel": responsavel,
                "pendentes": len(pendentes),
                "criticos": sum(1 for caso in pendentes if caso.get("gravidade") == GRAVIDADE_CRITICA),
                "vencidas": len(atrasos),
                "dias_uteis_de_atraso": max(atrasos, default=0.0),
                "medido_em": agora.isoformat(),
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
            por_setor.setdefault(str(caso.get("setor") or SETOR_NAO_INFORMADO), []).append(minutos)

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


def _prorrogacao(casos: list[dict], prorrogacoes: list[dict], medida: bool = True) -> dict:
    """A taxa de prorrogação, geral e por área (PRD #319, história 7).

    Só pedido APROVADO conta: o negado e o pendente não moveram prazo nenhum, e
    contá-los diria que a área empurrou um prazo que ela não empurrou. O
    denominador é o trabalho que a área recebeu no período, e não os pedidos: a
    pergunta é que fatia dele precisou de mais tempo.

    "Recebeu" quer dizer ter vencimento de área (`prazo_area_em`). Caso ainda em
    classificação nunca chegou ao setor, e gravidade `baixo` não passa pela área
    por definição (a célula dela na tabela de prazos é nula): os dois no
    denominador diluiriam a taxa com trabalho que a área nunca teve como
    prorrogar.

    `medida` falso significa que os pedidos não puderam ser lidos: aí não há
    taxa nenhuma, e não uma taxa de zero. O denominador continua saindo, porque
    ele não depende da leitura que falhou."""
    aprovadas = {str(p.get("manifestacao_id")) for p in prorrogacoes if p.get("status") == "aprovada"}
    com_a_area = [caso for caso in casos if caso.get("prazo_area_em")]
    por_setor: dict[str, dict] = {}
    for caso in com_a_area:
        setor = str(caso.get("setor") or SETOR_NAO_INFORMADO)
        linha = por_setor.setdefault(setor, {"setor": setor, "casos": 0, "prorrogados": 0})
        linha["casos"] += 1
        if str(caso.get("id")) in aprovadas:
            linha["prorrogados"] += 1

    for linha in por_setor.values():
        # `prorrogados` e a taxa da linha caem juntos quando a leitura falhou:
        # o topo admitir que não mediu e cada área imprimir "0,0%" logo abaixo
        # seria a afirmação entrando pela porta dos fundos, no mesmo objeto.
        if not medida:
            linha["prorrogados"] = None
            linha["taxa_pct"] = None
        else:
            linha["taxa_pct"] = round(linha["prorrogados"] * 100 / linha["casos"], 1) if linha["casos"] else None

    prorrogados = sum(linha["prorrogados"] or 0 for linha in por_setor.values())
    return {
        # None, e não zero, quando não houve o que medir: "taxa de prorrogação:
        # 0%" lê como "nenhuma área precisou de mais tempo", que é uma
        # afirmação, e não como "não houve caso na área". Mesma convenção de
        # `percentual_cumprido`, e vale para a contagem tanto quanto para a taxa.
        "casos": prorrogados if medida else None,
        "com_a_area": len(com_a_area),
        "taxa_pct": round(prorrogados * 100 / len(com_a_area), 1) if (com_a_area and medida) else None,
        # A ordenação precisa sobreviver à degradação: `-None` estoura, e sem
        # taxa a única ordem honesta é a alfabética.
        "por_area": sorted(por_setor.values(), key=lambda linha: (-(linha["taxa_pct"] or 0), linha["setor"])),
    }


def _reincidencia(casos: list[dict]) -> dict:
    """A taxa de reincidência do período (PRD #319, história 8). Mede quanto do
    que chegou já tinha chegado antes."""
    reincidentes = len([c for c in casos if c.get("reincidencia")])
    return {
        "casos": reincidentes,
        "taxa_pct": round(reincidentes * 100 / len(casos), 1) if casos else None,
    }


def _devolucoes(casos: list[dict], movimentos: list[dict], medida: bool = True) -> dict:
    """Quantas respostas a Ouvidoria recusou nos casos do período (issue #431).

    É o número que explica uma divergência que sem ele parece defeito: a
    devolução por insuficiência dá à área um `prazo_area_em` inteiro novo e não
    dá nada ao prazo conclusivo (decisão da fatia I1), então o mesmo caso sai
    CUMPRIDO no trecho da área e ESTOURADO no conclusivo, com os dois
    operadores verdes na tela.

    Dois números porque são duas perguntas: `casos` é quantos tiveram a
    resposta recusada ao menos uma vez, e é ele que casa com a divergência dos
    trechos; `total` é quantas vezes a área teve de refazer, que num caso
    devolvido duas vezes é maior.

    O universo é o mesmo dos indicadores de prazo, os casos que ENTRARAM na
    janela, e não as devoluções ocorridas nela: só assim a contagem explica os
    números que estão ao lado dela na resposta.

    `medida` falso significa que a trilha não pôde ser lida: aí não há
    contagem, e não uma contagem de zero. Mesma convenção da prorrogação, e
    aqui ela pesa igual: "nenhuma resposta foi recusada" é elogio à área."""
    if not medida:
        return {"casos": None, "total": None}
    ciclos = Counter()
    for movimento in movimentos:
        if e_devolucao(str(movimento.get("estado_anterior") or ""), str(movimento.get("estado_novo") or "")):
            ciclos[str(movimento.get("manifestacao_id"))] += 1
    # A contagem sai percorrendo os CASOS, e não os movimentos, do mesmo jeito
    # que a taxa de prorrogação: é o que ancora o número no universo do período
    # sem precisar de um filtro à parte, que seria uma segunda guarda escondendo
    # a primeira.
    por_caso = [ciclos.get(str(caso.get("id")), 0) for caso in casos]
    return {"casos": len([devolucoes for devolucoes in por_caso if devolucoes]), "total": sum(por_caso)}


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


def _classificados(casos: list[dict], campo: str) -> list[dict]:
    """Os casos cujo `campo` já foi decidido por alguém.

    O formulário público não pergunta tema nem área, e o caso entra marcado
    como pendente. Contar esses marcadores entre os mais frequentes imprimiria
    "Tema mais frequente: A classificar (40)" no PDF do diretor: isso é o
    tamanho da fila de triagem, não um tema do hospital.

    O marcador é o DAQUELE campo: cada domínio tem o seu, e reconhecer os dois
    em todo campo faria a área chamada com a frase da categoria (ou o inverso)
    sumir do ranking pelo marcador que não é dela (issue #433)."""
    pendentes = NAO_CLASSIFICADO_POR_CAMPO.get(campo, frozenset())
    return [caso for caso in casos if str(caso.get(campo) or "") not in pendentes and caso.get(campo)]


def _mais_frequentes(casos: list[dict], anteriores: list[dict], campo: str, teto: int) -> dict:
    """Os mais frequentes daquele campo, COM o denominador de onde saíram
    (PRD #319, história 3).

    O `teto` vem de fora, e é OBRIGATÓRIO, porque ele é diferente por eixo e um
    default esconderia de qual dos dois se está falando: `TOPO` para área, que
    é texto livre e tem cauda, `TETO_TEMAS` para tema, que é lista fechada e não
    tem (issue #490).

    A janela anterior entra aqui pelo mesmo motivo que entra em `por_canal`: a
    linha tem o mesmo formato das outras, e o consumidor foi informado de que
    `anterior` e `variacao_pct` significam a mesma coisa em todas. Sem passar o
    passado, um tema que caiu de 30 para 12 sairia com `anterior: 0` e seria
    impresso como novidade no mês em que despencou.

    `classificados` e `nao_classificados` viajam junto porque tirar o marcador
    do topo, sozinho, troca um erro por outro: o canal público é o maior volume
    e entra sem tipo e sem área, então uma quinzena de 43 casos com 3
    classificados imprimiria "Área mais frequente: Recepção (3)" ao lado de "43
    manifestações no período", sem nenhum número que explicasse os 40 de fora.
    E com nada classificado a lista vem vazia, indistinguível de "não houve
    tema". Sem o denominador, isto seria ausência de medição apresentada como
    medição, que é o que o resto do módulo combate."""
    decididos = _classificados(casos, campo)
    return {
        "itens": _contagem(decididos, campo, _classificados(anteriores, campo))[:teto],
        "classificados": len(decididos),
        "nao_classificados": len(casos) - len(decididos),
    }


def agregar(
    casos: list[dict],
    anteriores: list[dict],
    periodo: Periodo,
    agora: dt.datetime,
    prazos: dict[tuple[str, str], Prazo] | None = None,
    feriados: frozenset[dt.date] = frozenset(),
    responsaveis: list[dict] | None = None,
    prorrogacoes: list[dict] | None = None,
    movimentos: list[dict] | None = None,
    fila_viva: list[dict] | None = None,
    degradado: list[str] | None = None,
) -> dict:
    """Os números do período. Função pura: mesmas linhas, mesmos números.

    `fila_viva` é o universo das pendências (o que está pendente AGORA), e por
    isso chega separado de `casos` (o que entrou no período). Quem chama sem ela
    recebe as pendências dos casos do período, que é o mesmo conjunto quando a
    janela cobre tudo.

    `degradado` lista o que não pôde ser lido. Ele viaja na resposta para a tela
    poder dizer que aquele número não vale, em vez de imprimir um zero que passa
    por medição."""
    prorrogacoes = prorrogacoes or []
    por_caso = {str(p.get("manifestacao_id")): p for p in prorrogacoes}
    return {
        "periodo": periodo.como_dict(),
        "periodo_anterior": periodo.anterior().como_dict(),
        "degradado": sorted(degradado or []),
        "volume": _volume(casos, anteriores),
        "prazo": _prazo(casos, prazos or {}, feriados, agora, por_caso),
        "pendencias_por_area": _pendencias_por_area(
            casos if fila_viva is None else fila_viva, responsaveis or [], feriados, agora
        ),
        "ranking_areas": _ranking_areas(casos, feriados),
        "prorrogacao": _prorrogacao(casos, prorrogacoes, medida="prorrogacoes" not in (degradado or [])),
        "devolucoes": _devolucoes(casos, movimentos or [], medida="devolucoes" not in (degradado or [])),
        "reincidencia": _reincidencia(casos),
        "tempo_pausado": _tempo_pausado(casos, feriados, agora),
        "top_temas": _mais_frequentes(casos, anteriores, "tipo_manifestacao", TETO_TEMAS),
        "top_areas": _mais_frequentes(casos, anteriores, "setor", TOPO),
    }


# Margem do recorte no banco. A janela é pedida em dias do hospital, mas quem
# filtra é a coluna DATE `data_abertura`, que nos canais automáticos vem do
# relógio do banco: um dia para cada lado cobre qualquer diferença de fuso, e o
# recorte fino acontece depois, em `_no_periodo`.
MARGEM_DE_FUSO = dt.timedelta(days=1)

# Quantos ids cabem num `in_` por vez. O cliente PostgREST joga a lista na
# querystring do GET (cerca de 38 bytes por UUID), e alguns milhares de casos
# estouram o buffer de header do proxy: a leitura falharia inteira e a taxa de
# prorrogação sairia zerada sem ninguém ver.
LOTE_DE_IDS = 100

# Teto da janela pedida. Um período aberto faria duas varreduras integrais da
# tabela a cada requisição.
MAX_DIAS_DO_PERIODO = 366


class LeituraDegradadaError(Exception):
    """Uma das leituras de apoio falhou. Quem chama decide o que fazer; o que
    não pode é o número sair como se tivesse sido medido."""


def _casos_do_periodo(supabase, periodo: Periodo) -> list[dict]:
    """Os casos que entraram na janela, recortados pelo T0 do hospital.

    A query pede uma janela um dia maior de cada lado e o recorte fino é feito
    em Python por `_no_periodo`: assim o número não depende do fuso configurado
    no banco, e o filtro continua batendo numa coluna indexada."""
    linhas = ler_tudo(
        lambda: (
            supabase.table("ouvidoria_protocolos")
            .select(CAMPOS)
            .gte("data_abertura", (periodo.inicio - MARGEM_DE_FUSO).isoformat())
            .lte("data_abertura", (periodo.fim + MARGEM_DE_FUSO).isoformat())
            .order("id")
        ),
        rotulo="casos do período",
    )
    return [caso for caso in linhas if _no_periodo(caso, periodo)]


def _fila_viva(supabase) -> list[dict]:
    """Todo caso que ainda deve resposta da área, sem recorte de data.

    É o universo das pendências: a cobrança é sobre o que está aberto hoje, não
    sobre o que entrou no mês (issue #344, painel em tempo real)."""
    linhas = ler_tudo(
        lambda: supabase.table("ouvidoria_protocolos").select(CAMPOS).eq("status", AGUARDANDO_AREA).order("id"),
        rotulo="fila viva",
    )
    return [caso for caso in linhas if _esta_com_a_area(caso)]


def _tabela_de_prazos(supabase) -> dict[tuple[str, str], Prazo]:
    """A tabela de prazos inteira, indexada por (gravidade, marco)."""
    try:
        linhas = ler_tudo(
            lambda: (
                supabase.table("ouvidoria_prazos")
                .select("gravidade, marco, valor, unidade")
                .order("gravidade")
                .order("marco")
            ),
            rotulo="tabela de prazos",
        )
    except Exception as exc:
        logger.warning("Falha ao ler a tabela de prazos: os trechos sem coluna própria ficam sem régua")
        raise LeituraDegradadaError("prazos") from exc
    return {
        (str(linha.get("gravidade")), str(linha.get("marco"))): Prazo(
            valor=linha.get("valor"), unidade=linha.get("unidade") or "dias_uteis"
        )
        for linha in linhas
    }


def _feriados(supabase) -> frozenset[dt.date]:
    """O calendário útil (RN-22)."""
    try:
        linhas = ler_tudo(lambda: supabase.table("ouvidoria_feriados").select("data").order("data"), rotulo="feriados")
        return frozenset(dt.date.fromisoformat(str(linha["data"])) for linha in linhas if linha.get("data"))
    except Exception as exc:
        logger.warning("Falha ao carregar feriados: as métricas contam sem eles")
        raise LeituraDegradadaError("feriados") from exc


def _responsaveis(supabase) -> list[dict]:
    """O cadastro de quem responde por cada setor. É de onde sai o nome ao lado
    da pendência: cobrar setor não cobra ninguém."""
    try:
        return ler_tudo(
            lambda: (
                supabase.table("ouvidoria_setor_responsaveis")
                .select("setor, papel, nome, vigencia_inicio, vigencia_fim")
                .order("id")
            ),
            rotulo="responsáveis por setor",
        )
    except Exception as exc:
        logger.warning("Falha ao ler os responsáveis: as pendências saem sem nome")
        raise LeituraDegradadaError("responsaveis") from exc


def _prorrogacoes(supabase, casos: list[dict]) -> list[dict]:
    """Os pedidos de prorrogação dos casos do período, lidos em lotes.

    Sem casos não há o que perguntar, e um `in` de lista vazia é uma ida ao
    banco por nada."""
    ids = [str(caso.get("id")) for caso in casos if caso.get("id")]
    if not ids:
        return []
    linhas: list[dict] = []
    try:
        for inicio in range(0, len(ids), LOTE_DE_IDS):
            lote = ids[inicio : inicio + LOTE_DE_IDS]
            linhas.extend(
                ler_tudo(
                    lambda lote=lote: (
                        supabase.table("ouvidoria_prorrogacoes")
                        .select("manifestacao_id, status, prazo_anterior, prazo_novo")
                        .in_("manifestacao_id", lote)
                        .order("id")
                    ),
                    rotulo="prorrogações do período",
                )
            )
    except Exception as exc:
        logger.warning("Falha ao ler as prorrogações: a taxa do período fica sem medição")
        raise LeituraDegradadaError("prorrogacoes") from exc
    return linhas


def _movimentos_de_devolucao(supabase, casos: list[dict]) -> list[dict]:
    """As voltas para a área na trilha dos casos do período, lidas em lotes.

    Só as colunas de estado entram: a `observacao` do movimento carrega a
    resposta INTEIRA do setor (issue #374), que é texto de Dossiê e não tem o
    que fazer dentro de uma agregação. É também por isso que a contagem
    sobrevive à retenção: o job de cinco anos zera a `observacao` e preserva
    quem, quando e de que estado para qual (issue #343).

    O filtro por `estado_novo` é de CUSTO, não de regra: sem ele viria a
    tramitação inteira de cada caso do período (todo movimento, não só as voltas
    à área), e num período de 5000 casos isso é uma ordem de grandeza a mais de
    linha. Quem decide se aquela volta é DEVOLUÇÃO continua sendo `e_devolucao`,
    a mesma função que a rota usa para saber que precisa mexer no prazo.

    Os dois leem `DESTINO_DA_DEVOLUCAO`, e não cada um a sua cópia da string, de
    propósito: como o banco corta antes, uma régua que passasse a aceitar outro
    destino não mudaria número nenhum aqui, e a divergência ficaria invisível.
    Com a mesma constante nos dois lados, mudar a régua arrasta o filtro."""
    ids = [str(caso.get("id")) for caso in casos if caso.get("id")]
    if not ids:
        return []
    linhas: list[dict] = []
    try:
        for inicio in range(0, len(ids), LOTE_DE_IDS):
            lote = ids[inicio : inicio + LOTE_DE_IDS]
            linhas.extend(
                ler_tudo(
                    lambda lote=lote: (
                        supabase.table("ouvidoria_movimentos")
                        .select("manifestacao_id, estado_anterior, estado_novo")
                        .in_("manifestacao_id", lote)
                        .eq("estado_novo", DESTINO_DA_DEVOLUCAO)
                        .order("id")
                    ),
                    rotulo="movimentos de devolução",
                )
            )
    except Exception as exc:
        logger.warning("Falha ao ler a trilha: as devoluções do período ficam sem contagem")
        raise LeituraDegradadaError("devolucoes") from exc
    return linhas


def _ou_degradado(leitura, vazio, degradado: list[str]):
    """Roda uma leitura de apoio e, se ela falhar, registra o nome dela em
    `degradado` em vez de deixar o número sair como se tivesse sido medido."""
    try:
        return leitura()
    except LeituraDegradadaError as exc:
        degradado.append(str(exc))
        return vazio


def metricas_do_periodo(supabase, periodo: Periodo, agora: dt.datetime) -> dict:
    """Lê o que a agregação precisa e devolve os números do período.

    É esta a porta do módulo: a rota HTTP e o job do relatório entram por aqui,
    e por isso leem exatamente o mesmo número.

    As leituras dos casos e da fila viva não têm rede de proteção de propósito:
    sem elas não há métrica nenhuma, e a falha tem que subir. As de apoio
    (prazos, feriados, responsáveis, prorrogações e a trilha das devoluções)
    degradam o indicador que dependia delas e dizem isso em `degradado`."""
    degradado: list[str] = []
    casos = _casos_do_periodo(supabase, periodo)
    return agregar(
        casos=casos,
        anteriores=_casos_do_periodo(supabase, periodo.anterior()),
        periodo=periodo,
        agora=agora,
        prazos=_ou_degradado(lambda: _tabela_de_prazos(supabase), {}, degradado),
        feriados=_ou_degradado(lambda: _feriados(supabase), frozenset(), degradado),
        responsaveis=_ou_degradado(lambda: _responsaveis(supabase), [], degradado),
        prorrogacoes=_ou_degradado(lambda: _prorrogacoes(supabase, casos), [], degradado),
        movimentos=_ou_degradado(lambda: _movimentos_de_devolucao(supabase, casos), [], degradado),
        fila_viva=_fila_viva(supabase),
        degradado=degradado,
    )
