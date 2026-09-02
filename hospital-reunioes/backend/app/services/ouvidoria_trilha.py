"""A linha do tempo do caso, lida da trilha de movimentos (issue #485,
PRD #470, RN-63 a RN-65, diagnóstico da Diretoria D-08).

A trilha (`ouvidoria_movimentos`, migration 064) é gravada desde o primeiro dia
do módulo e nunca foi lida por tela nenhuma: o caso guardava a própria história
e não a mostrava. Este módulo é o tradutor entre o que o banco guarda (um par
de estados, um autor e uma observação) e o que o ouvidor lê (o que aconteceu,
quem fez, quando, e quanto tempo passou desde o marco anterior).

Módulo fundo e **puro**, no molde de `ouvidoria_marcos`: recebe os movimentos e
os feriados, e devolve os eventos prontos. Não lê banco, não consulta o relógio
e não conhece HTTP.

**O que decide o que cada evento É são os dois estados, não o texto.** Poderia
ser mais simples reconhecer a devolução pela frase que a rota escreve na
observação, mas a Retenção zera essa observação depois de cinco anos (issue
#375): o caso anonimizado passaria a exibir a devolução como um acionamento
novo, um fato que nunca aconteceu. O caminho no grafo é o que sobrevive à LGPD,
e é dele que sai a descrição. O texto entra depois, e só como conteúdo.

**Descrição em uma linha, texto integral à parte** (RN-63 e RN-64). Evento com
rótulo próprio (as transições) diz o rótulo na descrição e leva a observação
como `texto`, inteiro, porque ali a observação é o que alguém ESCREVEU: a
resposta da área, o motivo da devolução, o desfecho ao manifestante. Evento sem
mudança de estado (classificação, lembrete, escalonamento, prorrogação) não tem
rótulo próprio, e a observação que o sistema escreveu já É a descrição de uma
linha. Uma regra, dois lados.
"""

from __future__ import annotations

import datetime as dt

from app.services import ouvidoria_respostas
from app.services.ouvidoria_estados import e_devolucao, e_pausa, e_reabertura, e_retomada
from app.services.ouvidoria_prazos import FUSO, minutos_uteis_entre

CAMPOS_MOVIMENTO = "ocorrido_em, estado_anterior, estado_novo, autor_id, autor_nome, observacao"

# O rótulo que a devolução por insuficiência escreve na frente do motivo. Ele
# existe porque a trilha é lida por humano no banco, onde não há descrição
# nenhuma ao lado; na linha do tempo a descrição já diz o que aconteceu, e o
# rótulo repetido roubaria a primeira linha do que o ouvidor escreveu. Quem
# escreve e quem lê usam esta mesma constante: em palavras separadas, mudar a
# frase de um lado faria o outro passar a mostrar o rótulo de novo, em silêncio.
PREFIXO_DA_DEVOLUCAO = "Resposta devolvida por insuficiência. Motivo: "

# Os quatro marcos, com os mesmos nomes de `ouvidoria_marcos`: a página do caso
# mostra o bloco dos marcos e a linha do tempo lado a lado, e chamar a mesma
# etapa de dois nomes na mesma tela seria a tela contra si mesma.
ROTULO_DO_MARCO = {
    "T0": "Entrada",
    "T1": "Validação",
    "T2": "Resposta da área",
    "T3": "Conclusão",
}

# O que a tela diz quando não sobrou nem observação nem rótulo próprio. Acontece
# no caso anonimizado e no movimento antigo gravado sem texto: o FATO existiu, e
# calar sobre ele seria pior do que dizê-lo sem detalhe.
MOVIMENTO_SEM_TEXTO = "Movimento registrado na trilha"

ENTRADA = "Manifestação registrada"
ACIONAMENTO = "Caso validado e área acionada"
RESPOSTA_DA_AREA = "Resposta da área recebida"
DEVOLUCAO = "Resposta devolvida à área por insuficiência"
PAUSA = "Caso pausado, aguardando o manifestante"
RETOMADA = "Manifestante respondeu, caso retomado"
REABERTURA = "Caso reaberto por reincidência"
ENCERRAMENTO = "Caso encerrado"

# A transição que nenhuma das regras acima nomeia. Existe porque o grafo pode
# ganhar arestas, e evento novo tem que chegar à tela como fato datado, e não
# desaparecer dela em silêncio.
ROTULO_DO_ESTADO = {
    "novo": "Caso aberto",
    "em_classificacao": "Caso em classificação",
    "aguardando_area": "Caso encaminhado à área",
    "aguardando_manifestante": "Caso aguardando o manifestante",
    "respondido": "Caso respondido",
    "encerrado": "Caso encerrado",
}


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto. Instante sem fuso vale
    como hora de parede do hospital, a mesma leitura de `ouvidoria_marcos`."""
    if not bruto:
        return None
    momento = dt.datetime.fromisoformat(str(bruto))
    return momento if momento.tzinfo else momento.replace(tzinfo=FUSO)


def _marco(anterior: str | None, novo: str) -> str | None:
    """Qual dos quatro marcos esta transição fecha, se é que fecha algum.

    A régua é a mesma de `ouvidoria_marcos`, dita agora em cima do caminho e
    não das colunas carimbadas: o T1 é o acionamento (a validação despacha), o
    T2 é a chegada da resposta e o T3 é o encerramento.

    O T1 exige a ORIGEM, e não só o destino. Três caminhos diferentes chegam a
    `aguardando_area`: o acionamento, a devolução por insuficiência e a
    reabertura por reincidência. Só o primeiro fecha o trecho da triagem; os
    outros dois DESFAZEM marco já fechado (a devolução apaga o T2, a reabertura
    tira o caso do T3). Perguntar só pelo destino faria a linha do tempo contar
    a triagem de novo, meses depois, a cada volta do caso à área."""
    if anterior is None:
        return "T0"
    if anterior == novo:
        return None
    if novo == "encerrado":
        return "T3"
    if novo == "respondido":
        return "T2"
    if anterior == "em_classificacao" and novo == "aguardando_area":
        return "T1"
    return None


def _rotulo(anterior: str | None, novo: str) -> str | None:
    """A descrição de uma linha desta transição, ou None quando o movimento não
    é transição nenhuma (e aí a observação do sistema é que descreve).

    A ordem das perguntas é a ordem em que elas são específicas: a reabertura e
    a devolução chegam ao mesmo estado que o acionamento, e perguntar primeiro
    pelo destino apagaria as duas."""
    if anterior is None:
        return ENTRADA
    if anterior == novo:
        return None
    if e_reabertura(anterior, novo):
        return REABERTURA
    if e_devolucao(anterior, novo):
        return DEVOLUCAO
    if e_pausa(anterior, novo):
        return PAUSA
    if e_retomada(anterior, novo):
        return RETOMADA
    if novo == "encerrado":
        return ENCERRAMENTO
    if novo == "respondido":
        return RESPOSTA_DA_AREA
    if anterior == "em_classificacao" and novo == "aguardando_area":
        return ACIONAMENTO
    return ROTULO_DO_ESTADO.get(novo, MOVIMENTO_SEM_TEXTO)


def _uma_linha(texto: str) -> str:
    """A observação do sistema como descrição. Ela nasce de uma linha só, e o
    corte existe para o dia em que alguém gravar duas: a linha do tempo não
    pode virar um bloco de texto no lugar da descrição (RN-63)."""
    return texto.strip().splitlines()[0].strip()


def _sem_rotulo_interno(observacao: str) -> str:
    """O conteúdo escrito por gente, sem a marca que a trilha usa por dentro.

    A resposta do portal do setor entra prefixada (`ouvidoria_respostas.MARCA`)
    para que o histórico de ciclos a separe de uma transição qualquer para
    "respondido", e o motivo da devolução entra prefixado pelo rótulo do ato.
    Esses prefixos são vocabulário da trilha, não do ouvidor, e mostrá-los na
    tela seria repetir a descrição dentro do próprio texto."""
    if observacao.startswith(PREFIXO_DA_DEVOLUCAO):
        return observacao[len(PREFIXO_DA_DEVOLUCAO) :]
    texto = ouvidoria_respostas.texto_do_movimento(observacao)
    return texto if texto is not None else observacao


def _evento(movimento: dict) -> dict:
    """Um movimento traduzido em evento da linha do tempo, sem o tempo
    decorrido (que depende do movimento anterior e entra depois)."""
    anterior = movimento.get("estado_anterior")
    novo = movimento.get("estado_novo") or ""
    observacao = (movimento.get("observacao") or "").strip()
    rotulo = _rotulo(anterior, novo)

    if rotulo is None:
        # Movimento sem mudança de estado: a observação É a descrição.
        descricao, texto = (_uma_linha(observacao) if observacao else MOVIMENTO_SEM_TEXTO), None
    else:
        descricao, texto = rotulo, (_sem_rotulo_interno(observacao) if observacao else None)

    marco = _marco(anterior, novo)
    return {
        "ocorrido_em": movimento.get("ocorrido_em"),
        "autor": movimento.get("autor_nome") or "Sistema",
        # Quem agiu sem estar logado: os jobs, a Retenção e o canal aberto. É o
        # `autor_id` nulo que os separa, e não o nome, que é texto livre.
        "sistema": movimento.get("autor_id") is None,
        "marco": marco,
        "marco_rotulo": ROTULO_DO_MARCO.get(marco) if marco else None,
        "descricao": descricao,
        "texto": texto,
        "desde_marco": None,
        "desde_marco_rotulo": None,
        "minutos_uteis": None,
    }


def linha_do_tempo(movimentos: list[dict], feriados: frozenset[dt.date]) -> list[dict]:
    """Os eventos do caso, do mais novo para o mais antigo (RN-63).

    `movimentos` chega na ordem que o banco devolveu, em qualquer sentido: a
    ordenação é refeita aqui porque a conta do tempo depende do sentido
    cronológico e ler a ordem do chamador seria confiar em quem não sabe disso.

    O tempo entre marcos é contado em minutos de EXPEDIENTE, pelo mesmo
    calendário do motor de prazos (RN-65). Dias corridos acusariam de lentidão
    quem respondeu na segunda um caso de sexta. O primeiro marco não recebe
    tempo, e não recebe zero: antes da entrada não havia caso."""
    ordenados = sorted(movimentos, key=lambda m: str(m.get("ocorrido_em") or ""))
    eventos = [_evento(m) for m in ordenados]

    marco_anterior: dict | None = None
    for evento in eventos:
        if evento["marco"] is None:
            continue
        quando = _instante(evento["ocorrido_em"])
        if marco_anterior is not None and quando is not None:
            desde = _instante(marco_anterior["ocorrido_em"])
            if desde is not None:
                evento["desde_marco"] = marco_anterior["marco"]
                evento["desde_marco_rotulo"] = marco_anterior["marco_rotulo"]
                evento["minutos_uteis"] = minutos_uteis_entre(desde, quando, feriados)
        marco_anterior = evento

    return list(reversed(eventos))
