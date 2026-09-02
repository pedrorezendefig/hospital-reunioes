"""Novidade na fila da Ouvidoria (issue #484, PRD #470, RN-66).

Um caso tem novidade quando a última movimentação da trilha é mais recente que
o carimbo de visto da Ouvidoria, ou quando o carimbo é nulo. Nada disso é
guardado: o carimbo mora no protocolo (`vista_pela_ouvidoria_em`, migration
092) e o outro lado da comparação é derivado da trilha na hora da leitura.

A leitura da trilha é uma só para a fila inteira, e falha nela não derruba a
fila: sem o ponto o ouvidor ainda trabalha; sem a lista, não. Mas ela também
não pode virar silêncio, e é aí que mora a armadilha desta fatia: "sem
novidade" e "não consegui ler a trilha" desenham a MESMA lista, e a segunda
apagaria justamente o sinal que a fatia existe para dar. Por isso a falha volta
NOMEADA, no mesmo formato do `degradado` do calendário (issue #449), para a
tela poder dizer que o marcador está fora do ar em vez de deixar o ouvidor ler
"nada mexeu".
"""

from __future__ import annotations

import datetime as dt
import logging

from httpx import HTTPError
from postgrest.exceptions import APIError

from app.services.paginacao import ler_paginado

logger = logging.getLogger(__name__)

# A função de agregação da migration 092: um par (caso, instante) por caso com
# pelo menos um movimento na trilha.
RPC_ULTIMO_MOVIMENTO = "ouvidoria_ultimo_movimento"

# O nome da leitura que falhou, do jeito que a resposta diz isso. Mesmo
# vocabulário do `degradado` do calendário (`feriados`): a tela lê uma lista só
# e traduz cada nome em uma frase.
LEITURA_DA_TRILHA = "movimentos"

# As mesmas falhas que o fail-open do calendário cobre, e pelos mesmos motivos
# (ver `FALHAS_DE_LEITURA_DO_CALENDARIO` em `routers/ouvidoria.py`):
# `HTTPError` é o transporte, e é o que `APIError` NÃO pega, porque `APIError`
# só nasce depois que a resposta HTTP chega; `APIError` é o PostgREST
# respondendo e recusando; `OSError` é o socket embaixo dos dois; `ValueError`
# é o timestamp malformado que a conversão encontra.
#
# `AttributeError` e `TypeError` ficam DE FORA de propósito: erro de
# programação não é indisponibilidade de infraestrutura, e um `except` largo
# aqui deixaria a suíte verde rodando com a trilha vazia.
FALHAS_DE_LEITURA_DA_TRILHA = (HTTPError, APIError, OSError, ValueError)

# A ordem da leitura em páginas. Precisa ser única e estável, senão a janela de
# uma página repete ou pula linha entre uma ida e outra ao banco. A função
# agrega POR caso, então `manifestacao_id` é único no resultado por construção.
ORDEM_DO_AGREGADO = "manifestacao_id"

# O outro lado da conta do contador (issue #487): os casos e o carimbo de cada
# um. As mesmas falhas de infraestrutura da trilha, porque é o mesmo PostgREST
# do outro lado do fio.
FALHAS_DE_LEITURA_DOS_CASOS = FALHAS_DE_LEITURA_DA_TRILHA
LEITURA_DOS_CASOS = "casos"

# O contador lê do caso só o que a régua consome: o id, que casa com a chave do
# agregado, e o carimbo. Nada mais sai do banco para virar um número.
CAMPOS_DO_CONTADOR = "id, vista_pela_ouvidoria_em"

# A ordem da leitura dos casos, pelo mesmo motivo da ordem do agregado. `numero`
# é UNIQUE, e é a mesma chave por onde a fila pagina.
ORDEM_DOS_CASOS = "numero"


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto, ou None quando vazio."""
    return dt.datetime.fromisoformat(str(bruto)) if bruto else None


def ultimo_movimento_ou_degradado(supabase) -> tuple[dict[str, dt.datetime], list[str]]:
    """O instante da última movimentação de cada caso, por id, e a lista do que
    não pôde ser lido.

    Em páginas até esgotar, como a listagem que a chama (issue #430): um
    `PGRST_DB_MAX_ROWS` configurado no PostgREST cortaria o agregado no teto com
    HTTP 200, e o ponto de novidade sumiria da parte da fila que ficou de fora,
    sem erro nenhum. Ler em páginas exige ordem estável, e a ordem é a chave do
    agregado.

    Falha devolve o mapa vazio E o nome da leitura. Quem chama junta esse nome
    ao `degradado` da resposta: sem isso o ouvidor veria uma fila sem ponto
    nenhum e concluiria que nada mexeu."""
    try:
        linhas, completa = ler_paginado(
            lambda: supabase.rpc(RPC_ULTIMO_MOVIMENTO, {}).order(ORDEM_DO_AGREGADO), rotulo=LEITURA_DA_TRILHA
        )
        # A conversão entra no try junto da leitura, como no calendário: um
        # timestamp malformado é dado ruim, e a promessa aqui é a fila abrir.
        mapa: dict[str, dt.datetime] = {}
        for linha in linhas:
            quando = _instante(linha.get("ultimo_movimento_em"))
            if quando is not None:
                mapa[str(linha.get("manifestacao_id"))] = quando
        # Leitura que parou no teto de voltas vale como leitura que falhou: o
        # mapa saiu menor, e todo caso que ficou de fora dele perde o ponto na
        # fila e sai do total no contador. Menos linhas do que existem é uma
        # resposta errada, não uma resposta parcial.
        return mapa, [] if completa else [LEITURA_DA_TRILHA]
    except FALHAS_DE_LEITURA_DA_TRILHA:
        # `exc_info` pelo mesmo motivo do calendário: sem ele o log diz que
        # faltou a trilha e não diz se foi o banco fora do ar ou bug.
        logger.warning(
            "Falha ao derivar a última movimentação dos casos: a fila sai sem marcador de novidade",
            exc_info=True,
        )
        return {}, [LEITURA_DA_TRILHA]


def tem_novidade(vista_em, ultimo_movimento_em: dt.datetime | None) -> bool:
    """A regra do ponto (RN-66).

    Carimbo nulo é novidade mesmo sem nenhum movimento na trilha: é o estado em
    que todo caso já existente entra na migration, e ninguém pode afirmar que a
    Ouvidoria o leu.

    O empate cai do lado de "já vi": quem abriu o caso no mesmo instante do
    movimento leu o movimento. Do outro lado o ponto nunca apagaria nos casos
    em que a própria abertura coincide com o último movimento gravado.
    """
    vista = _instante(vista_em)
    if vista is None:
        return True
    if ultimo_movimento_em is None:
        return False
    return ultimo_movimento_em > vista


def contar_novidades(supabase) -> tuple[int | None, list[str]]:
    """Quantos casos têm novidade agora, e a lista do que não pôde ser lido
    (issue #487, RN-69).

    É o mesmo número que a fila desenha em pontos, contado pela MESMA função
    (`tem_novidade`) e sobre o MESMO universo: todos os casos, sem recorte de
    status nem de sigilo, porque quem chama já passou pelo gate do Perfil da
    Ouvidoria e enxerga a fila inteira. Uma segunda definição de novidade aqui
    faria o menu anunciar um número que a fila não consegue explicar.

    O total é `None` quando alguma das duas leituras falhou, e nunca zero:
    contador que não carregou não é contador zerado. Zero manda o distintivo
    sumir, e sumir é exatamente a tela de "nada novo" que a fatia existe para
    não mentir. A falha viaja NOMEADA, no mesmo `degradado` da fila.

    A trilha vem primeiro e decide sozinha: sem ela, nenhum caso com carimbo
    pode ser julgado, e ler os casos seria uma ida ao banco para um número que
    já se sabe impossível."""
    ultimos, degradado = ultimo_movimento_ou_degradado(supabase)
    if degradado:
        return None, degradado
    try:
        # Em páginas até esgotar, como a fila ao lado (issue #430). Aqui o corte
        # silencioso do `PGRST_DB_MAX_ROWS` seria pior do que na listagem: uma
        # fila curta se nota na tela, um total menor não se nota em lugar
        # nenhum, e o menu passaria a esconder casos com cara de contado.
        linhas, completa = ler_paginado(
            lambda: supabase.table("ouvidoria_protocolos").select(CAMPOS_DO_CONTADOR).order(ORDEM_DOS_CASOS),
            rotulo=LEITURA_DOS_CASOS,
        )
    except FALHAS_DE_LEITURA_DOS_CASOS:
        logger.warning(
            "Falha ao ler os casos para o contador de novidades: o menu sai sem número",
            exc_info=True,
        )
        return None, [LEITURA_DOS_CASOS]
    # Mesma régua da trilha: lista cortada no teto de voltas conta menos casos
    # do que existem, e um total menor é indistinguível de um total certo.
    if not completa:
        logger.warning(
            "A leitura dos casos parou no teto de páginas: o contador de novidades sai sem número",
        )
        return None, [LEITURA_DOS_CASOS]
    total = sum(
        1 for linha in linhas if tem_novidade(linha.get("vista_pela_ouvidoria_em"), ultimos.get(str(linha.get("id"))))
    )
    return total, []
