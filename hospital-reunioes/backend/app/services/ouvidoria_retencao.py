"""Retenção da Ouvidoria: anonimização após cinco anos (issue #343, ADR 0034) e
a porta antecipada da Diretoria (issue #595, ADR 0047).

A manifestação encerrada há mais de cinco anos perde o Dossiê e vira estatística.
O que sai é o que identifica ou narra o caso; o que fica é o que os relatórios
contam. A separação é explícita de propósito: uma anonimização por lista de
exclusão erra sempre que uma coluna nova nasce, então aqui a lista é a das
colunas que SAEM, e cada coluna nova precisa de uma decisão consciente.

O Dossiê não mora só na manifestação. O relato e a resposta da área se
espalham por cinco lugares, e a retenção varre os cinco:

  1. `ouvidoria_protocolos`, as colunas de texto e identificação;
  2. `ouvidoria_anexos`, metadados aqui e binário no bucket privado;
  3. `ouvidoria_movimentos.observacao`, que carrega a resposta INTEIRA da área
     (issue #374) e é servida pela rota do histórico de respostas;
  4. `ouvidoria_tentativas_contato.observacao` e as duas justificativas de
     `ouvidoria_prorrogacoes`, texto livre sobre o caso;
  5. `ouvidoria_notificacoes.detalhe`, onde viajam o motivo da devolução
     (migration 074) e o da reabertura (migration 075), escritos à mão pelo
     ouvidor.

Ordem das operações: o movimento da trilha vem PRIMEIRO, e o carimbo por
ÚLTIMO. Tudo o que destrói fica no meio, entre os dois. O motivo está em
`_anonimizar_caso`.

**O destino das outras tabelas do módulo, por decisão consciente.** A lista
acima é de colunas, então uma tabela que ninguém decidiu simplesmente não
aparece em lugar nenhum, e o silêncio lê igual a "preservar de propósito" e a
"esquecemos". Por isso cada uma ganha uma linha aqui:

  - `ouvidoria_relatorios` (issue #435): **PRESERVADA inteira**, e sem nada a
    anonimizar. O que ela guarda são números agregados do período, o nome do
    titular de cada setor e o email de quem recebeu cada edição: dado
    funcional de gestão do hospital, não dado de manifestante. Nenhuma coluna
    dela carrega protocolo, relato ou identificação de quem manifestou, de
    propósito (migration 080, RN-40, ADR 0034 decisão 8). Apagá-la destruiria
    o histórico de prestação de contas da Ouvidoria sem devolver privacidade a
    ninguém.

**Duas portas, uma política.** O cron dos cinco anos (`anonimizar_encerradas
_antigas`) e o ato da Diretoria (`apagar_caso`, chamado pela rota de
apagamento) terminam no mesmo estado, porque são o mesmo serviço: o que muda
entre eles é a CHAVE que abre a política sobre aquele caso, e ela é o
`Apagamento` que o chamador monta. Ali estão também quem assina o movimento da
trilha e o motivo escrito, que só a porta da Diretoria tem.

A chave não é decoração: ela é a mesma régua que a guarda de UPDATE da trilha
confere no banco (migrations 079 e 100), e é reconferida por leitura antes de
cada passo destrutivo. Serviço e banco dizendo coisas diferentes aqui seria a
varredura destruindo os registros filhos para só então esbarrar no gatilho.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio, e a
rota `POST /manifestacoes/{id}/apagamento`; aqui vive a lógica, testável com um
Supabase falso.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging

from app.config import settings
from app.services import storage
from app.services.ouvidoria_contato import PAPEL_MANIFESTANTE

logger = logging.getLogger(__name__)

ENCERRADO = "encerrado"

# O prazo de retenção da ADR 0034: cinco anos contados do encerramento (T3).
# O mesmo prazo está escrito na guarda de UPDATE da trilha (migration 079).
# Mudar aqui exige mudar lá.
ANOS_DE_RETENCAO = 5

# Teto de casos por rodada. O job roda uma vez por dia e nasce dormindo (nenhum
# caso tem cinco anos ainda), mas o dia em que a fila acumular não pode virar
# uma varredura infinita segurando o scheduler.
LOTE_POR_RODADA = 100

# Quem assina o movimento quando quem apaga é o cron dos cinco anos. A porta
# antecipada assina com o nome de quem pediu, que é gente do hospital.
AUTOR_DA_RETENCAO = "Sistema (retenção)"

# A marca que abre a observação do movimento do apagamento, nas DUAS portas.
#
# É por ela que a rodada seguinte reconhece um movimento já gravado (e não grava
# outro), e é por ela que a linha do tempo sabe qual movimento apagou o caso
# para creditar o autor no aviso (issue #593). Era o `autor_nome` que fazia os
# dois papéis, e ele deixou de servir no dia em que a Diretoria passou a assinar
# com nome de pessoa: a marca no texto reconhece as duas portas, o nome de quem
# assinou continua onde sempre esteve, no `autor_nome`.
#
# Quem escreve e quem lê usam esta mesma constante: em palavras separadas, mudar
# a frase de um lado faria o outro parar de reconhecer o ato, em silêncio.
#
# Não há movimento antigo a converter: até esta fatia, o único que gravava o
# movimento do apagamento era o cron dos cinco anos, e nenhum caso chegou lá (o
# módulo é de 2026, e o próprio ADR 0047 conta com isso). Movimento gravado com
# a frase anterior, se um dia existir, deixa de ser reconhecido: a rodada
# seguinte gravaria um segundo movimento e o aviso da tela perderia o autor. É
# por isso que a marca é PREFIXO, e não a frase inteira: o texto depois dela
# pode mudar sem quebrar quem lê.
MARCA_DO_APAGAMENTO = "Apagamento do Dossiê"
_SEPARADOR = ": "

# O que a observação diz, e por que ela descreve o ato EM CURSO e não um serviço
# já feito: o movimento é gravado antes de qualquer coisa ser apagada, e a
# trilha é append-only. Uma frase no pretérito viraria afirmação falsa e
# permanente sobre um Dossiê ainda inteiro, se a rodada morresse logo depois
# daqui. Quem atesta a conclusão é o carimbo `anonimizada_em`.
_O_QUE_SAI = (
    "A anonimização começa aqui e retira do caso o relato, a identificação do manifestante, "
    "os anexos e o conteúdo dos demais registros, preservando os campos estatísticos. "
    "O carimbo `anonimizada_em` na manifestação é o que atesta a conclusão."
)


def observacao_do_apagamento(motivo: str | None) -> str:
    """O texto do movimento que entra na trilha, nas duas portas.

    Este é o único movimento do caso que sobrevive à limpeza de observações,
    então o que se escreve aqui fica para sempre. Pela porta dos cinco anos ele
    não cita nada do Dossiê, de propósito: um nome escrito ali seria dado
    pessoal que a retenção nunca mais apagaria.

    Pela porta da Diretoria o motivo entra, e essa é uma escolha consciente da
    ADR 0047: sem ele, o caso apagado não teria como explicar o próprio buraco.
    Quem escreve o motivo é a Diretoria, avisada na tela de que ele fica."""
    if motivo is None:
        abertura = f"caso alcançado pela política de retenção de {ANOS_DE_RETENCAO} anos. {_O_QUE_SAI}"
        return f"{MARCA_DO_APAGAMENTO}{_SEPARADOR}{abertura}"
    return f"{MARCA_DO_APAGAMENTO}{_SEPARADOR}pedido pela Diretoria Executiva. {_O_QUE_SAI} Motivo: {motivo}"


def e_movimento_de_apagamento(observacao: str | None) -> bool:
    """O movimento é o do apagamento do caso?

    A resposta sai da marca, e não do autor nem do par de estados: a Diretoria
    assina com nome de pessoa, e o par `encerrado` para `encerrado` também serve
    a atos de job que não apagaram nada."""
    return str(observacao or "").startswith(MARCA_DO_APAGAMENTO)


@dataclasses.dataclass(frozen=True)
class Apagamento:
    """Quem apaga, por quê, e por qual das duas chaves da política.

    `corte` é a chave dos cinco anos (o instante a partir do qual o
    encerramento ainda está dentro do prazo); `pedido_em` é a chave da porta
    antecipada (o carimbo do pedido que a rota gravou). Exatamente uma delas
    vem preenchida, e é ela que filtra a reconferência de cada passo
    destrutivo. As construtoras abaixo são as duas únicas formas legítimas de
    montar isto, e existem para que a exclusividade não dependa de quem chama
    lembrar dela."""

    autor: str
    autor_id: str | None = None
    motivo: str | None = None
    corte: dt.datetime | None = None
    pedido_em: str | None = None


def pelos_cinco_anos(agora: dt.datetime) -> Apagamento:
    """A porta do cron: autor de sistema, sem motivo, chave do prazo."""
    return Apagamento(autor=AUTOR_DA_RETENCAO, corte=data_de_corte(agora))


def pela_diretoria(autor: str, autor_id: str, motivo: str, pedido_em: str) -> Apagamento:
    """A porta antecipada (ADR 0047): quem assinou, o motivo escrito, e o
    carimbo do pedido como chave.

    A chave é o carimbo DESTE pedido, e não "existe algum pedido": assim a
    reconferência de cada passo destrutivo recusa também o caso cujo pedido foi
    reescrito no meio da rodada."""
    return Apagamento(autor=autor, autor_id=autor_id, motivo=motivo, pedido_em=pedido_em)


# O Dossiê na manifestação: o que a retenção apaga. Cada campo é texto livre
# sobre o caso ou identificação de quem manifestou.
CAMPOS_DO_DOSSIE: dict[str, str | None] = {
    "relato_integral": None,
    "manifestante_nome": None,
    "manifestante_contato": None,
    # Cópias e derivados do relato, espalhados pela tramitação.
    "extrato_para_o_setor": None,
    "resposta_da_area": None,
    "desfecho_descricao": None,
    "classificacao_ia": None,
    # Ponte para a conversa da Ana, onde o relato original continua inteiro.
    "conversa_id": "",
    # O lugar exato do cartaz que a pessoa leu ("Poltrona 12"). A migration 067
    # o descreve como rótulo do cartaz, e por isso ele parece dado do hospital;
    # a 084 é posterior e diz o contrário com todas as letras (issue #375,
    # decisão 5): cruzado com o registro de atendimento daquele dia naquele
    # ponto, ele reidentifica quem manifestou. A 084 chegou a zerar a coluna
    # nos casos anônimos por backfill e escreveu lá que "a retencao da 079 nao
    # alcanca esta coluna, entao o conserto e aqui"; o conserto do caso NÃO
    # anônimo é este. Nenhuma estatística o lê, então apagar não custa
    # relatório nenhum, e o `canal_setor` (área inteira) segue preservado.
    "canal_ponto": None,
}

# `resumo` é NOT NULL com CHECK anti-vazio desde a migration 063: não pode ir a
# NULL, então vira marcador. O texto some do mesmo jeito. Mesma história para
# `justificativa` da prorrogação (migration 073).
MARCADOR_ANONIMIZADO = "[anonimizado pela retenção]"

# O que fica, e por quê: é disto que o módulo de métricas tira volume, prazo
# cumprido, ranking por área e reincidência. A lista não é usada pelo código
# (o update só toca no Dossiê); ela existe para o teste de retenção afirmar,
# campo a campo, o que a anonimização não pode ter mexido.
CAMPOS_ESTATISTICOS: tuple[str, ...] = (
    "numero",
    "protocolo",
    "status",
    "data_abertura",
    "contato_em",
    "validada_em",
    "respondida_em",
    "encerrada_em",
    "prazo_area_em",
    "tipo_manifestacao",
    "categoria",
    "setor",
    "gravidade",
    "canal",
    "desfecho",
    "minutos_pausados",
    "reincidencia",
    "anonimo",
    "sigilo_reforcado",
    "manifestante_vinculo",
    # Os três abaixo entram por dependência declarada do módulo de métricas
    # (issue #341), que os lê para calcular cumprimento de prazo e ranking de
    # tempo de resposta. Eles já sobreviviam, porque a lista de apagados não os
    # inclui, mas estar aqui muda a natureza disso: deixa de ser acidente e
    # passa a ser contrato entre as duas fatias, defendido por teste.
    #
    # O que aconteceria se um dia caíssem no Dossiê apagado:
    #   - `area_estourou_em` é a memória do estouro que a área já consumou
    #     (issue #374); zerada, um caso que atrasou volta a ler "cumprido" e o
    #     percentual de prazo da área SOBE retroativamente, mexendo em número
    #     de relatório já publicado;
    #   - `reaberta_em` é o T1 do ciclo corrente de um caso reincidente;
    #     zerada, o ranking de tempo médio volta a medir do T1 original e a
    #     área leva o ciclo anterior inteiro na conta;
    #   - `pausada_em` é da mesma família (num caso encerrado há cinco anos ela
    #     é nula de qualquer jeito, mas a razão para preservá-la é a mesma).
    #
    # Nenhum dos três carrega dado de quem manifestou: são marcos de relógio.
    "area_estourou_em",
    "reaberta_em",
    "pausada_em",
    # E daqui para baixo, o resto da tabela (issue #397, item 2). A lista
    # prometia afirmação campo a campo e cobria metade das colunas de
    # `ouvidoria_protocolos`; o que faltava foi conferido uma a uma e nenhuma
    # carrega dado de quem manifestou:
    #   - `dados_incompletos` é o sinal de cadastro incompleto do caso;
    #   - `prazo_rompido_em`, `vespera_avisada_em`, `escalonado_gestor_em`,
    #     `escalonado_diretoria_em`, `critico_avisado_em` e
    #     `escalonamento_impossivel_em` são carimbos dos jobs de prazo e da
    #     escada de escalonamento (migrations 071, 072 e 078): marcos de
    #     relógio do hospital, e é deles que sai a contagem de estouro;
    #   - `canal_setor` é o setor de ORIGEM do cartaz de QR (migration 067),
    #     área inteira do hospital, não pessoa. O `canal_ponto`, que fica no
    #     mesmo par, NÃO está aqui: ele é reidentificador e sai com o Dossiê;
    #   - `registrado_por`, `validada_por` e `respondida_por_nome` são gente do
    #     HOSPITAL (quem digitou, quem validou, quem respondeu pela área);
    #   - `prazo_resposta` é coluna gerada de `data_abertura` (migration 063).
    "dados_incompletos",
    "prazo_rompido_em",
    "vespera_avisada_em",
    "escalonado_gestor_em",
    "escalonado_diretoria_em",
    "critico_avisado_em",
    "escalonamento_impossivel_em",
    "canal_setor",
    "registrado_por",
    "validada_por",
    "respondida_por_nome",
    "prazo_resposta",
    # O Arquivo (issue #592, ADR 0047). Ficam, e a decisão é consciente: são
    # gente do HOSPITAL e relógio do hospital, como `validada_por`, e não dizem
    # nada sobre quem manifestou. Apagá-los devolveria à lista, cinco anos
    # depois, um caso que a Ouvidoria já tinha guardado.
    "arquivada_em",
    "arquivada_por",
    # O pedido de apagamento (issue #595, ADR 0047). Ficam, e é o ponto da
    # decisão: eles são o REGISTRO DO ATO, e sobrevivem junto do protocolo e da
    # trilha. Apagados com o Dossiê, o caso apagado pela Diretoria não saberia
    # dizer quem mandou apagar nem por quê, e o aviso na tela do caso ficaria
    # sem a metade que explica o buraco.
    #
    # `apagamento_motivo` é o único texto livre que a política preserva, e isso
    # é consciente: quem o escreve é a Diretoria, na tela que avisa que ele
    # fica. No caso apagado pelos cinco anos os três continuam nulos, porque ali
    # ninguém pediu nada, o prazo venceu.
    "apagamento_pedido_em",
    "apagamento_pedido_por",
    "apagamento_motivo",
)

# O que o job precisa do caso para decidir e anonimizar.
_CAMPOS_DA_RETENCAO = "id, status, encerrada_em, anonimizada_em"


def data_de_corte(agora: dt.datetime) -> dt.datetime:
    """O instante a partir do qual o encerramento ainda está dentro da retenção.

    Encerramento anterior ou igual ao corte já passou dos cinco anos. Feito por
    subtração de ano (não por 365 dias) para o aniversário cair no mesmo dia;
    29 de fevereiro recua para 28."""
    try:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO)
    except ValueError:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO, day=28)


def anonimizar_encerradas_antigas(supabase, agora: dt.datetime) -> int:
    """Anonimiza as manifestações encerradas há mais de cinco anos.

    Devolve quantas foram anonimizadas nesta rodada. Com o freio puxado
    (`OUVIDORIA_RETENCAO_ATIVA=false`), devolve 0 sem tocar em nada."""
    if not settings.ouvidoria_retencao_ativa:
        logger.info("[Ouvidoria] Retenção desligada por configuração; nenhum caso será anonimizado.")
        return 0

    corte = data_de_corte(agora)
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DA_RETENCAO)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            # Caso com `encerrada_em` nulo (encerrado antes do marco T3 existir,
            # ou vindo do import histórico do NocoDB) fica de fora: sem saber
            # quando fechou, não dá para dizer que os cinco anos passaram.
            .lte("encerrada_em", corte.isoformat())
            .order("encerrada_em")
            .limit(LOTE_POR_RODADA)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos encerrados para a retenção")
        return 0

    anonimizadas = 0
    apagamento = pelos_cinco_anos(agora)
    for caso in result.data or []:
        if apagar_caso(supabase, caso, agora, apagamento):
            anonimizadas += 1
    return anonimizadas


def apagar_caso(supabase, caso: dict, agora: dt.datetime, apagamento: Apagamento) -> bool:
    """Anonimiza um caso inteiro, na ordem que sobrevive a uma falha no meio.

    O movimento da trilha vem PRIMEIRO: ele é o registro que prova a
    legalidade do ato, e gravá-lo depois do carimbo significaria que uma falha
    ali destruiria o Dossiê sem deixar rastro, para sempre, porque nenhuma
    rodada seguinte volta em caso carimbado. Gravado antes, o pior caso é um
    movimento em pé com o Dossiê ainda inteiro, e a rodada seguinte termina o
    serviço reaproveitando o mesmo movimento.

    O carimbo vem por ÚLTIMO pelo mesmo motivo, do outro lado: enquanto ele não
    existe, o caso volta na varredura e a limpeza recomeça. Cada passo é
    idempotente, então recomeçar não custa nada; no dos anexos essa
    idempotência depende de cada binário sair junto com o próprio ponteiro,
    e o `_apagar_anexos` explica por quê.

    Qualquer passo que falhe interrompe o caso e devolve False: um caso
    contado como anonimizado com metade do Dossiê em pé seria pior que um caso
    que voltou para a fila.

    E entre a varredura e a gravação o mundo pode mudar: cada passo destrutivo
    reconfere antes de agir que a política ainda cobre o caso
    (`_caso_ainda_anonimizavel`), para que um caso reaberto (ou reaberto e
    reencerrado dentro do prazo) no meio da rodada não perca os registros
    filhos e só então esbarre na guarda do `_apagar_dossie`.

    É a entrada pública, e é por ela que as duas portas passam: o cron, um caso
    por vez dentro da varredura, e a rota da Diretoria, no caso que ela pediu.
    O `apagamento` diz quem assina, o motivo e por qual chave da política aquele
    caso é alcançado."""
    movimento_id = _garantir_movimento(supabase, caso["id"], apagamento)
    if movimento_id is None:
        return False
    if not _limpar_observacoes_da_trilha(supabase, caso["id"], exceto=movimento_id):
        return False
    if not _limpar_tentativas_de_contato(supabase, caso["id"], apagamento):
        return False
    if not _limpar_prorrogacoes(supabase, caso["id"], apagamento):
        return False
    if not _limpar_notificacoes(supabase, caso["id"], apagamento):
        return False
    if not _apagar_anexos(supabase, caso["id"], apagamento):
        return False
    return _apagar_dossie(supabase, caso["id"], agora)


def _garantir_movimento(supabase, manifestacao_id: str, apagamento: Apagamento) -> str | None:
    """O ato entra na trilha do caso, uma vez só. Devolve o id do movimento, ou
    None quando não foi possível garantir que ele existe.

    Não é transição de estado (o caso segue encerrado), então o insert é
    direto, no molde do movimento de prazo rompido. A idempotência não vem do
    carimbo da manifestação (que ainda não existe neste ponto) e sim da MARCA
    da observação: um movimento de apagamento já gravado é reaproveitado.

    A marca substituiu a assinatura desde a issue #595. Reconhecer o movimento
    pelo `autor_nome` funcionava enquanto só o cron apagava; com a Diretoria
    assinando com nome de pessoa, a régua por autor deixaria de casar e a
    segunda chamada gravaria um movimento novo (e o aviso da tela perderia o
    crédito de quem apagou, issue #593).

    O filtro é feito aqui, e não no PostgREST, de propósito: um `like` com
    curinga é mais uma sintaxe para errar em silêncio, e a trilha de um caso
    cabe folgadamente na memória. Quem decide o que é movimento de apagamento é
    `e_movimento_de_apagamento`, a mesma função que a linha do tempo usa.

    A observação vem de `observacao_do_apagamento`, que explica o que fica
    escrito ali para sempre."""
    try:
        existentes = (
            supabase.table("ouvidoria_movimentos")
            .select("id, observacao")
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao conferir o movimento de anonimização do caso %s", manifestacao_id)
        return None
    for movimento in existentes.data or []:
        if e_movimento_de_apagamento(movimento.get("observacao")):
            return str(movimento["id"])

    try:
        gravado = (
            supabase.table("ouvidoria_movimentos")
            .insert(
                {
                    "manifestacao_id": manifestacao_id,
                    "estado_anterior": ENCERRADO,
                    "estado_novo": ENCERRADO,
                    "autor_id": apagamento.autor_id,
                    "autor_nome": apagamento.autor,
                    "observacao": observacao_do_apagamento(apagamento.motivo),
                }
            )
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao gravar o movimento de anonimização do caso %s", manifestacao_id)
        return None
    if not gravado.data:
        logger.error("[Ouvidoria] Movimento de anonimização do caso %s não gravou", manifestacao_id)
        return None
    return str(gravado.data[0]["id"])


def _limpar_observacoes_da_trilha(supabase, manifestacao_id: str, exceto: str) -> bool:
    """Zera a `observacao` dos movimentos do caso, menos a do movimento da
    própria retenção.

    É aqui que o texto da resposta da área morre de verdade: o portal do setor
    grava a resposta INTEIRA na trilha (issue #374), e a rota do histórico de
    respostas serve esse texto sem olhar a anonimização. Apagar
    `resposta_da_area` sem apagar isto não anonimizaria nada.

    O resto do movimento (quem, quando, de que estado para qual) fica: a trilha
    continua provando o que aconteceu. Quem permite este único UPDATE é a
    guarda da migration 079, que confere na própria linha do caso que a
    política de cinco anos o cobre.

    Esse "resto" tem consumidor declarado, e não é só a prova histórica: o
    módulo de métricas conta as devoluções por insuficiência lendo
    `estado_anterior` e `estado_novo` desta tabela (`ouvidoria_metricas`, issue
    #431). É o mesmo papel que `CAMPOS_ESTATISTICOS` faz pelas colunas do caso
    (issue #397), aqui do lado da trilha: zerar os estados junto com a
    observação faria a contagem de períodos antigos cair para zero em silêncio,
    que é o modo de falha que aquele módulo inteiro existe para impedir. Quem
    ampliar esta limpeza mexe primeiro naquela leitura."""
    try:
        (
            supabase.table("ouvidoria_movimentos")
            .update({"observacao": None})
            .eq("manifestacao_id", manifestacao_id)
            .neq("id", exceto)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as observações da trilha do caso %s", manifestacao_id)
        return False
    return True


def _caso_ainda_anonimizavel(supabase, manifestacao_id: str, apagamento: Apagamento) -> bool:
    """Confere na linha do caso que a política de retenção ainda o cobre:
    encerrado, sem carimbo, e alcançado pela chave daquele apagamento (o corte
    dos cinco anos, ou o pedido que a Diretoria gravou).

    As tabelas filhas não têm `status` nem `anonimizada_em`, e o PostgREST não
    filtra UPDATE por coluna de outra tabela: a guarda que o `_apagar_dossie`
    faz dentro do próprio UPDATE (atômica, no banco) só existe lá. Aqui ela é
    feita por leitura, imediatamente antes de cada passo destrutivo.

    Não é atômica e não promete ser: sobra o intervalo de uma ida ao banco
    entre a conferência e a escrita. O que ela fecha é a janela larga, a dos
    vários passos entre a varredura e a gravação, em que um caso reaberto
    perdia tentativas, prorrogações, notificações e anexos e ainda assim via o
    `_apagar_dossie` recusar, ficando meio triturado com o Dossiê em pé.

    A chave entra junto com o estado, e não só o estado: um caso que reabriu e
    foi reencerrado no meio da rodada volta a ter `status = encerrado` e
    passaria por uma guarda que só olhasse isso, e aí o Dossiê de um caso
    encerrado ontem seria triturado dentro do prazo. É a mesma condição que a
    varredura usa e que o gatilho das migrations 079 e 100 confere no banco.

    Pela porta antecipada a chave é o carimbo daquele pedido, e não o prazo:
    exigir os cinco anos aqui faria o serviço recusar tudo o que a Diretoria
    apagasse, e exigir só "algum pedido gravado" deixaria passar o caso cujo
    pedido foi reescrito no meio da rodada.

    Falha ao ler também é não: sem confirmação, nada é destruído."""
    consulta = (
        supabase.table("ouvidoria_protocolos")
        .select("id")
        .eq("id", manifestacao_id)
        .eq("status", ENCERRADO)
        .is_("anonimizada_em", "null")
    )
    if apagamento.pedido_em is not None:
        consulta = consulta.eq("apagamento_pedido_em", apagamento.pedido_em)
    else:
        consulta = consulta.lte("encerrada_em", apagamento.corte.isoformat())
    try:
        atual = consulta.execute()
    except Exception:
        logger.error("[Ouvidoria] Falha ao reconferir o estado do caso %s antes de anonimizar", manifestacao_id)
        return False
    if not atual.data:
        logger.info(
            "[Ouvidoria] Caso %s deixou de estar anonimizável no meio da rodada; nada foi apagado",
            manifestacao_id,
        )
        return False
    return True


def _limpar_tentativas_de_contato(supabase, manifestacao_id: str, apagamento: Apagamento) -> bool:
    """Zera a `observacao` das tentativas de contato do caso.

    É o que o ouvidor escreveu ao tentar falar com quem manifestou, tipicamente
    o telefone discado e o que foi dito. As linhas ficam, e com elas `canal` e
    `tentada_em`: quantas vezes e por onde a Ouvidoria tentou é estatística do
    encerramento por sem retorno, não relato de ninguém."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, apagamento):
        return False
    try:
        (
            supabase.table("ouvidoria_tentativas_contato")
            .update({"observacao": None})
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as tentativas de contato do caso %s", manifestacao_id)
        return False
    return True


def _limpar_prorrogacoes(supabase, manifestacao_id: str, apagamento: Apagamento) -> bool:
    """Zera as duas justificativas da prorrogação do caso.

    `justificativa` é NOT NULL com CHECK anti-vazio (migration 073), então vira
    marcador. Dias pedidos, prazos e o status da decisão ficam: é deles que sai
    a taxa de prorrogação por área do PRD #319."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, apagamento):
        return False
    try:
        (
            supabase.table("ouvidoria_prorrogacoes")
            .update({"justificativa": MARCADOR_ANONIMIZADO, "decisao_justificativa": None})
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as prorrogações do caso %s", manifestacao_id)
        return False
    return True


def _limpar_notificacoes(supabase, manifestacao_id: str, apagamento: Apagamento) -> bool:
    """Zera o `detalhe` de todas as notificações do caso, e a identificação das
    que foram para o MANIFESTANTE.

    São dois UPDATEs porque são dois públicos, e misturá-los apagaria prova.

    **O `detalhe`, em todas as linhas.** O comentário da migration 068 descreve
    `detalhe` como "o nome do gestor a quem a demanda subiu", e por isso ele
    parece registro do hospital. Duas migrations depois reaproveitaram a coluna
    para texto do caso, e disseram isso por escrito: o motivo da devolução viaja
    aqui (074) e o da reabertura também (075). Desde a issue #494 o desfecho
    enviado ao manifestante também. Os três são escritos à mão pelo ouvidor.

    **O nome e o endereço, só nas linhas do manifestante.** Até a issue #493
    todo gatilho da casa falava para DENTRO do hospital, e esta função dizia por
    escrito que `destinatario_nome` e `destinatario_email` eram "o titular ou o
    substituto do setor". Essa premissa caiu: o acuse (#493) e o aviso de
    encerramento (#494) gravam o nome e o email pessoais de quem manifestou.
    Sem esta limpeza, o caso saía da anonimização sem nome, sem contato, sem
    relato e sem desfecho, e duas linhas desta tabela continuavam dizendo "Joana
    da Silva / joana@exemplo.com" amarradas ao mesmo `manifestacao_id`, que
    ainda tem protocolo, data, setor, tipo e desfecho: qualquer perfil da
    Ouvidoria reidentificava o caso pela porta `GET .../notificacoes`.

    O filtro por papel é a parte que NÃO pode sumir. As linhas do setor guardam
    a quem a Ouvidoria cobrou, e são elas que provam a cobrança (ADR 0034,
    decisão 7): apagá-las junto trocaria um vazamento por uma prova destruída.

    Marcador em vez de `NULL` porque as duas colunas são `NOT NULL`, e o email
    ainda carrega `CHECK (btrim(...) <> '')` (migration 068). O endereço marcado
    não é reenviável, e é assim que deve ser: caso anonimizado não tem mais a
    quem escrever.

    O resto da linha fica: `gatilho`, `status` e as datas são o rastro de
    entrega, e `ultimo_erro` é mensagem do provedor de email."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, apagamento):
        return False
    try:
        (
            supabase.table("ouvidoria_notificacoes")
            .update({"detalhe": None})
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
        (
            supabase.table("ouvidoria_notificacoes")
            .update(
                {
                    "destinatario_nome": MARCADOR_ANONIMIZADO,
                    "destinatario_email": MARCADOR_ANONIMIZADO,
                }
            )
            .eq("manifestacao_id", manifestacao_id)
            # O `.eq` descarta NULL em silêncio no PostgREST (issue #175), e
            # aqui isso é DE PROPÓSITO, ao contrário da guarda do log: lá a
            # linha sem papel é tratada como manifestante e tem o endereço
            # omitido, aqui ela não é apagada. As duas pontas escolhem lados
            # opostos porque o custo de errar é oposto: no log, imprimir demais
            # vaza; aqui, apagar demais destrói a prova da cobrança ao setor
            # (ADR 0034, decisão 7), e o apagado não volta.
            #
            # A divergência não alcança linha nenhuma hoje: `papel_destinatario`
            # nasceu junto com a tabela (migration 068) e nenhum chamador grava
            # sem papel. Se um dia gravar, a MESMA linha ficaria com o endereço
            # fora do log e com nome e email do manifestante no banco depois dos
            # cinco anos, e é essa linha que este comentário existe para
            # denunciar: quem a criar conserta o gravador, não este filtro.
            .eq("papel_destinatario", PAPEL_MANIFESTANTE)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as notificações do caso %s", manifestacao_id)
        return False
    return True


def _apagar_anexos(supabase, manifestacao_id: str, apagamento: Apagamento) -> bool:
    """Apaga os anexos do caso um a um: o binário primeiro, a linha dele em
    seguida, e só então o próximo anexo.

    Binário primeiro porque a linha é o único ponteiro para o arquivo, e
    apagá-la antes deixaria o arquivo órfão no bucket para sempre.

    Anexo a anexo porque é o que mantém a retomada convergente. Desde que o
    `delete_file` passou a exigir confirmação do Storage (issue #397, item 1),
    um arquivo que já não está no bucket também não é confirmado: o Storage
    responde 200 com lista vazia e não há como separar "não estava lá" de "não
    consegui remover". Se este passo removesse todos os binários e só depois
    apagasse todas as linhas de uma vez, uma falha no meio deixaria linhas de
    pé apontando para binários que já saíram, e a rodada seguinte travaria
    logo no primeiro deles, todo dia, para sempre: o caso nunca completaria a
    anonimização e o Dossiê ficaria no banco além dos cinco anos, que é o
    oposto do que a política manda. Pareado, cada anexo que sai leva o próprio
    ponteiro junto, e a rodada seguinte só enxerga anexo cujo binário ainda
    está no bucket.

    O que sobra de janela: se a remoção do binário der certo e o apagamento da
    linha dele falhar logo depois, aquele anexo trava o caso e precisa de
    humano. É um passo do tamanho de uma linha, contra os dois passos e todos
    os anexos de antes."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, apagamento):
        return False
    try:
        result = (
            supabase.table("ouvidoria_anexos")
            .select("id, storage_path")
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao listar os anexos do caso %s para a retenção", manifestacao_id)
        return False

    for anexo in result.data or []:
        caminho = anexo.get("storage_path")
        if caminho and not storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, caminho):
            logger.error("[Ouvidoria] Falha ao remover o anexo %s do bucket; retenção adiada", caminho)
            return False
        try:
            supabase.table("ouvidoria_anexos").delete().eq("id", anexo["id"]).execute()
        except Exception:
            logger.error(
                "[Ouvidoria] Falha ao apagar os metadados do anexo %s do caso %s", anexo["id"], manifestacao_id
            )
            return False
    return True


def _apagar_dossie(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    """Zera o Dossiê da manifestação e carimba a anonimização no mesmo update.

    O update é condicional (`status = 'encerrado'` e `anonimizada_em IS NULL`):
    a segunda rodada do job, uma rodada concorrente, ou um caso que reabriu
    entre a varredura e a gravação não acham o que anonimizar."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update(dict(CAMPOS_DO_DOSSIE) | {"resumo": MARCADOR_ANONIMIZADO, "anonimizada_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao apagar o Dossiê do caso %s", manifestacao_id)
        return False
    return bool(result.data)
