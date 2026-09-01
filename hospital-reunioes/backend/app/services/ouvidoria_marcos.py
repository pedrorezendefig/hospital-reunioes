"""Os quatro marcos do caso e o tempo decorrido em cada trecho (issue #480,
PRD #468, RN-55, diagnóstico da Diretoria D-05 e D-10).

Módulo fundo e **puro**, no molde do motor de prazos de onde ele tira a régua:
recebe o caso, o instante da medição e os feriados, e devolve o que a página do
caso mostra. Não lê banco, não consulta o relógio e não conhece HTTP.

A pergunta que a página responde é "onde este caso emperrou": entrada (T0),
validação (T1), resposta da área (T2) e conclusão (T3), com o tempo de
EXPEDIENTE que separa cada par. Dias corridos serviriam para nada aqui, porque
o prazo que a Diretoria cobra corre no Calendário útil: dizer "o setor levou 3
dias" onde a área teve 1 dia de mesa acusaria de lentidão quem respondeu na
segunda um caso de sexta.

QUAL PRAZO CONCLUSIVO MANDA NESTA TELA (a decisão que a fatia #479 deixou em
aberto). Existem duas fontes, e elas divergem de propósito:

1. `ouvidoria_protocolos.prazo_conclusivo_em`, congelado na validação e sem
   nenhum crédito de prorrogação ou de pausa (migration 091);
2. o conclusivo recalculado em `ouvidoria_metricas._vencimento_do_trecho`, que
   soma ao vencimento o crédito já concedido ao prazo da área.

**Esta tela lê a coluna congelada (1).** Três motivos, nesta ordem:

* o PRD #468 crava. A história 11 pede o conclusivo "congelado na validação,
  para mudança futura na tabela de prazos não recalcular caso já despachado", e
  a história 12 pede que gravidade sem célula conclusiva "simplesmente não
  exiba esse prazo". A coluna nasceu na fatia #479 para esta página ler;
* a página do caso e o relatório respondem perguntas diferentes. Aqui a
  pergunta é "o que foi prometido a ESTE manifestante", e a resposta é o
  compromisso assumido no despacho. No relatório a pergunta é "quanto o
  hospital cumpre", e ali dar ao conclusivo o mesmo crédito do prazo da área é
  o que impede o PDF de acusar de atraso uma prorrogação que a própria
  Diretoria concedeu. As duas leituras estão certas, cada uma no seu lugar;
* recalcular na leitura faria editar a tabela de prazos mudar o passado, que é
  exatamente o que o Motor de prazos proíbe (CONTEXT.md).

O preço da escolha é que o número pode ficar visualmente incoerente: em caso
prorrogado, o conclusivo congelado cai ANTES do prazo da área, e em caso
reaberto ele já nasce vencido. A tela não conserta nem esconde o número, ela o
NOMEIA: as duas notas abaixo dizem, em português, por que o relógio do
manifestante e o da área estão onde estão.
"""

from __future__ import annotations

import datetime as dt

from app.services.ouvidoria_prazos import (
    FUSO,
    esta_vencido,
    minutos_uteis_entre,
    rotular_vencimento,
)
from app.services.ouvidoria_prorrogacao import entrada_da_manifestacao

ENCERRADO = "encerrado"

# Os quatro marcos, na ordem em que o caso os atravessa (RN-55). Cada um a
# partir do T1 fecha o trecho que o anterior abriu, e `responsavel` é de quem é
# o tempo daquele trecho: é o que responde "onde emperrou, e com quem".
#
# O T2 ao T3 é da Ouvidoria, e não da área: depois que o setor responde, quem
# fecha o caso com quem manifestou é a Ouvidoria. Sem esse trecho separado, o
# gargalo da própria Ouvidoria ficaria escondido dentro do total (D-05).
#
# O T0 não sai de coluna própria: a entrada é o instante REAL do contato
# (`contato_em`), com `data_abertura` de fallback nos casos antigos. Quem sabe
# ler os dois é `entrada_da_manifestacao`, o mesmo T0 que o teto da prorrogação
# usa: dois T0 diferentes no mesmo caso seriam dois processos diferentes.
MARCOS = (
    {"chave": "T0", "rotulo": "Entrada", "coluna": None, "trecho": None, "responsavel": None},
    {
        "chave": "T1",
        "rotulo": "Validação",
        "coluna": "validada_em",
        "trecho": "Triagem da Ouvidoria",
        "responsavel": "ouvidoria",
    },
    {
        "chave": "T2",
        "rotulo": "Resposta da área",
        "coluna": "respondida_em",
        "trecho": "Resposta da área",
        "responsavel": "area",
    },
    {
        "chave": "T3",
        "rotulo": "Conclusão",
        "coluna": "encerrada_em",
        "trecho": "Desfecho pela Ouvidoria",
        "responsavel": "ouvidoria",
    },
)

# Os dois prazos que andam junto dos marcos: o da área (T1 ate T2) e o do caso
# inteiro (T0 ate T3, o compromisso com quem manifestou, D-10).
PRAZOS = (
    {"chave": "area", "rotulo": "Prazo da área", "coluna": "prazo_area_em"},
    {"chave": "conclusivo", "rotulo": "Prazo conclusivo", "coluna": "prazo_conclusivo_em"},
)

# As três situações de um prazo, que a coluna nula sozinha não separa.
DEFINIDO = "definido"
# Nulo porque o despacho ainda não aconteceu: o prazo sai da validação.
AGUARDANDO_VALIDACAO = "aguardando_validacao"
# Nulo porque a gravidade não tem aquela célula na tabela (o crítico não tem
# conclusiva fixa; o baixo não passa pela área). Aqui não existe prazo, e a
# tela não mostra linha nenhuma em vez de inventar data (PRD #468, história 12).
SEM_PRAZO = "sem_prazo"

NOTA_CREDITO_SO_DA_AREA = (
    "A prorrogação e a espera pelo manifestante movem o prazo da área, nunca o conclusivo: "
    "este é o compromisso assumido com quem manifestou, na validação."
)

NOTA_REABERTURA = (
    "Prazo da primeira tramitação: a reabertura por reincidência dá prazo novo à área, "
    "e não compra prazo novo com quem manifestou."
)


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto, ou None quando vazio.

    Valor sem fuso vale como hora de parede do hospital, a mesma leitura que
    `entrada_da_manifestacao` já faz com `contato_em`. As colunas são
    `timestamptz` e chegam com fuso, então isto é cinto de segurança: o motor
    recusa instante ingênuo de propósito, e um `ValueError` subindo daqui
    derrubaria a página inteira do caso por causa de um dado torto."""
    if not bruto:
        return None
    momento = dt.datetime.fromisoformat(str(bruto))
    return momento if momento.tzinfo else momento.replace(tzinfo=FUSO)


def _medido_em(caso: dict, agora: dt.datetime) -> dt.datetime:
    """O instante contra o qual o que ainda está aberto é medido.

    Caso parado aguardando o manifestante mede no instante em que parou, a
    mesma régua do painel (`_projetar_prazo`) e das métricas: medir contra o
    relógio de parede cobraria da área uma espera que não é dela."""
    return _instante(caso.get("pausada_em")) or agora


def _marco_em(caso: dict, marco: dict) -> dt.datetime | None:
    """Quando aquele marco aconteceu NESTE caso, ou None se ainda não aconteceu.

    O T3 só vale enquanto o caso está encerrado. A reabertura por reincidência
    preserva `encerrada_em` de propósito (é o marco da tramitação anterior, que
    os relatórios leem), mas o caso voltou a tramitar: lido cru, aquele carimbo
    apresentaria como concluído um caso que está aberto agora. É a mesma guarda
    de `ouvidoria_metricas._marco_que_fecha`."""
    if marco["coluna"] is None:
        return entrada_da_manifestacao(caso)
    if marco["chave"] == "T3" and caso.get("status") != ENCERRADO:
        return None
    return _instante(caso.get(marco["coluna"]))


def _nota_do_prazo(
    caso: dict, chave: str, vencimento: dt.datetime | None, prazo_area: dt.datetime | None
) -> str | None:
    """Por que o relógio do manifestante está onde está.

    Só o conclusivo tem nota, e só nos dois casos em que o número congelado
    contraria a leitura ingênua da tela. Fora deles a nota seria ruído."""
    if chave != "conclusivo" or vencimento is None:
        return None
    if caso.get("reaberta_em"):
        return NOTA_REABERTURA
    if prazo_area is not None and prazo_area > vencimento:
        return NOTA_CREDITO_SO_DA_AREA
    return None


def marcos_do_caso(caso: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> dict:
    """Os quatro marcos com o tempo decorrido, e os dois prazos ao lado deles.

    Devolve as duas listas na ordem em que a página as mostra. Marco que não
    aconteceu vem `pendente`, com `em` nulo: preencher com o marco anterior ou
    com o relógio faria a tela inventar um fato do caso.

    Trecho cujo marco de ABERTURA ainda não aconteceu não tem tempo, e não tem
    zero: zero diria que a área respondeu na hora quando ela nem foi acionada.
    Trecho aberto conta até a medição e se declara `em_curso`, que é como o
    caso parado na fila mostra o tempo que já queimou."""
    instantes = {marco["chave"]: _marco_em(caso, marco) for marco in MARCOS}
    medido_em = _medido_em(caso, agora)

    linhas = []
    abertura: dt.datetime | None = None
    for marco in MARCOS:
        em = instantes[marco["chave"]]
        if marco["coluna"] is None or abertura is None:
            minutos, em_curso = None, False
        elif em is not None:
            minutos, em_curso = minutos_uteis_entre(abertura, em, feriados), False
        else:
            minutos, em_curso = minutos_uteis_entre(abertura, medido_em, feriados), True
        linhas.append(
            {
                "chave": marco["chave"],
                "rotulo": marco["rotulo"],
                "em": em.isoformat() if em else None,
                "pendente": em is None,
                "trecho": marco["trecho"],
                "responsavel": marco["responsavel"],
                "minutos_uteis": minutos,
                "em_curso": em_curso,
                # O encerramento que a reabertura preservou. Fica dito pelo que
                # é, em vez de sumir da tela ou passar por conclusão do ciclo
                # corrente.
                "tramitacao_anterior_em": (
                    _instante(caso.get("encerrada_em")).isoformat()
                    if marco["chave"] == "T3" and em is None and caso.get("encerrada_em")
                    else None
                ),
            }
        )
        abertura = em

    prazo_area = _instante(caso.get("prazo_area_em"))
    prazos = []
    for prazo in PRAZOS:
        vencimento = _instante(caso.get(prazo["coluna"]))
        # O prazo da área congela a medida na pausa porque o vencimento dele é
        # empurrado na retomada; o conclusivo nunca é empurrado, e congelar a
        # medida dele daria ao caso um crédito que ninguém concedeu.
        medida = medido_em if prazo["chave"] == "area" else agora
        prazos.append(
            {
                "chave": prazo["chave"],
                "rotulo": prazo["rotulo"],
                "em": vencimento.isoformat() if vencimento else None,
                "situacao": (
                    DEFINIDO if vencimento else (AGUARDANDO_VALIDACAO if not caso.get("validada_em") else SEM_PRAZO)
                ),
                # A mesma frase do painel e do email do setor: painel, email e
                # página do caso nunca dizem prazos diferentes.
                "rotulo_prazo": rotular_vencimento(vencimento, medida, feriados) if vencimento else None,
                "estourado": esta_vencido(vencimento, medida),
                "nota": _nota_do_prazo(caso, prazo["chave"], vencimento, prazo_area),
            }
        )

    return {"marcos": linhas, "prazos": prazos}
