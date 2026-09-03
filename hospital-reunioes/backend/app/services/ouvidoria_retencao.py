"""Retenção da Ouvidoria: anonimização após cinco anos (issue #343, ADR 0034).

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

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio; aqui
vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

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

# Quem assina o movimento da retenção. É por este nome que a rodada seguinte
# reconhece um movimento já gravado e não grava outro.
AUTOR_DA_RETENCAO = "Sistema (retenção)"

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
    for caso in result.data or []:
        if _anonimizar_caso(supabase, caso, agora):
            anonimizadas += 1
    return anonimizadas


def _anonimizar_caso(supabase, caso: dict, agora: dt.datetime) -> bool:
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
    filhos e só então esbarre na guarda do `_apagar_dossie`."""
    # O mesmo corte da varredura: `data_de_corte` é determinística e `agora` é
    # o relógio da rodada inteira.
    corte = data_de_corte(agora)
    movimento_id = _garantir_movimento(supabase, caso["id"])
    if movimento_id is None:
        return False
    if not _limpar_observacoes_da_trilha(supabase, caso["id"], exceto=movimento_id):
        return False
    if not _limpar_tentativas_de_contato(supabase, caso["id"], corte):
        return False
    if not _limpar_prorrogacoes(supabase, caso["id"], corte):
        return False
    if not _limpar_notificacoes(supabase, caso["id"], corte):
        return False
    if not _apagar_anexos(supabase, caso["id"], corte):
        return False
    return _apagar_dossie(supabase, caso["id"], agora)


def _garantir_movimento(supabase, manifestacao_id: str) -> str | None:
    """O ato entra na trilha do caso, uma vez só. Devolve o id do movimento, ou
    None quando não foi possível garantir que ele existe.

    Não é transição de estado (o caso segue encerrado), então o insert é
    direto, no molde do movimento de prazo rompido. A idempotência não vem do
    carimbo da manifestação (que ainda não existe neste ponto) e sim da
    assinatura: um movimento da retenção já gravado é reaproveitado.

    A observação não cita nada do Dossiê: este é o único movimento do caso que
    sobrevive à limpeza de observações, e um nome escrito aqui seria dado
    pessoal que a retenção nunca mais apagaria.

    E ela descreve o ato EM CURSO, não um serviço já feito. O movimento é
    gravado antes de qualquer coisa ser apagada, e a trilha é append-only: uma
    frase no pretérito viraria afirmação falsa e permanente sobre um Dossiê
    ainda inteiro, se a rodada morresse logo depois daqui. Quem atesta a
    conclusão é o carimbo `anonimizada_em`, que só existe no fim."""
    try:
        existentes = (
            supabase.table("ouvidoria_movimentos")
            .select("id")
            .eq("manifestacao_id", manifestacao_id)
            .eq("autor_nome", AUTOR_DA_RETENCAO)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao conferir o movimento de anonimização do caso %s", manifestacao_id)
        return None
    if existentes.data:
        return str(existentes.data[0]["id"])

    try:
        gravado = (
            supabase.table("ouvidoria_movimentos")
            .insert(
                {
                    "manifestacao_id": manifestacao_id,
                    "estado_anterior": ENCERRADO,
                    "estado_novo": ENCERRADO,
                    "autor_id": None,
                    "autor_nome": AUTOR_DA_RETENCAO,
                    "observacao": (
                        f"Caso alcançado pela política de retenção de {ANOS_DE_RETENCAO} anos: "
                        "a anonimização começa aqui e retira do caso o relato, a identificação "
                        "do manifestante, os anexos e o conteúdo dos demais registros, "
                        "preservando os campos estatísticos. O carimbo `anonimizada_em` na "
                        "manifestação é o que atesta a conclusão."
                    ),
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


def _caso_ainda_anonimizavel(supabase, manifestacao_id: str, corte: dt.datetime) -> bool:
    """Confere na linha do caso que a política de retenção ainda o cobre:
    encerrado, sem carimbo e encerrado antes do corte dos cinco anos.

    As tabelas filhas não têm `status` nem `anonimizada_em`, e o PostgREST não
    filtra UPDATE por coluna de outra tabela: a guarda que o `_apagar_dossie`
    faz dentro do próprio UPDATE (atômica, no banco) só existe lá. Aqui ela é
    feita por leitura, imediatamente antes de cada passo destrutivo.

    Não é atômica e não promete ser: sobra o intervalo de uma ida ao banco
    entre a conferência e a escrita. O que ela fecha é a janela larga, a dos
    vários passos entre a varredura e a gravação, em que um caso reaberto
    perdia tentativas, prorrogações, notificações e anexos e ainda assim via o
    `_apagar_dossie` recusar, ficando meio triturado com o Dossiê em pé.

    O prazo entra junto com o estado, e não só o estado: um caso que reabriu e
    foi reencerrado no meio da rodada volta a ter `status = encerrado` e
    passaria por uma guarda que só olhasse isso, e aí o Dossiê de um caso
    encerrado ontem seria triturado dentro do prazo. É a mesma condição que a
    varredura usa e que o gatilho da migration 079 confere no banco.

    Falha ao ler também é não: sem confirmação, nada é destruído."""
    try:
        atual = (
            supabase.table("ouvidoria_protocolos")
            .select("id")
            .eq("id", manifestacao_id)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            .lte("encerrada_em", corte.isoformat())
            .execute()
        )
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


def _limpar_tentativas_de_contato(supabase, manifestacao_id: str, corte: dt.datetime) -> bool:
    """Zera a `observacao` das tentativas de contato do caso.

    É o que o ouvidor escreveu ao tentar falar com quem manifestou, tipicamente
    o telefone discado e o que foi dito. As linhas ficam, e com elas `canal` e
    `tentada_em`: quantas vezes e por onde a Ouvidoria tentou é estatística do
    encerramento por sem retorno, não relato de ninguém."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, corte):
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


def _limpar_prorrogacoes(supabase, manifestacao_id: str, corte: dt.datetime) -> bool:
    """Zera as duas justificativas da prorrogação do caso.

    `justificativa` é NOT NULL com CHECK anti-vazio (migration 073), então vira
    marcador. Dias pedidos, prazos e o status da decisão ficam: é deles que sai
    a taxa de prorrogação por área do PRD #319."""
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, corte):
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


def _limpar_notificacoes(supabase, manifestacao_id: str, corte: dt.datetime) -> bool:
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
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, corte):
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
            .eq("papel_destinatario", PAPEL_MANIFESTANTE)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as notificações do caso %s", manifestacao_id)
        return False
    return True


def _apagar_anexos(supabase, manifestacao_id: str, corte: dt.datetime) -> bool:
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
    if not _caso_ainda_anonimizavel(supabase, manifestacao_id, corte):
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
