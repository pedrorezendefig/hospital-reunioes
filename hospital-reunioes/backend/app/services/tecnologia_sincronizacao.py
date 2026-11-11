"""A Demanda vinculada relendo o GitHub (issue #678, PRD #673, ADR 0054).

Uma rotina, dois gatilhos. `sincronizar_demanda` le a issue, monta a foto,
compara o cache que ela derivaria com o que ja esta na Demanda e, se mudou,
grava o cache (a Etapa, as partes e O que muda).
Quem a chama e o webhook (em segundos, pelo numero da issue do payload) e o job
de hora em hora (sobre o lote inteiro). O par webhook + reconciliacao e o mesmo
molde da ClickSign, e existe pelo mesmo motivo: o GitHub NAO reentrega webhook
que falhou, e sem a segunda passagem um container reiniciando na hora errada
congelaria a Etapa da conversa ate alguem mexer nela a mao.

Duas invariantes que valem pelos dois caminhos:

- **Cache igual nao escreve NADA.** Nem o `UPDATE`, nem o carimbo da ultima
  sincronizacao. E o que faz a entrega repetida do GitHub e a passagem de hora
  em hora serem inofensivas. "Igual" e sobre o cache DERIVADO, e nao so sobre a
  foto crua (issue #690): a regra que deriva a Etapa e o "O que muda" muda com
  o app, e quem comparasse a foto deixaria a Demanda sem novidade no GitHub com
  o valor da regra velha para sempre.
- **Falha e de UMA Demanda.** No lote, o `except` e por linha e por qualquer
  causa (o GitHub fora do ar e o timeout do PostgREST chegam por portas
  diferentes), e o log guarda o identificador.

Desde a issue #1065 (ADR 0069, decisao 4) quem leva a Demanda Entregue a Em
producao e o webhook de deploy que a Action pos-merge chama
(`marcar_em_producao`), ou a passagem de hora em hora pelo `history.json` da
`main` (`reconciliar_em_producao`).

A devolucao da entrega a quem pediu (o card de volta em Aguardando, a linha
no fio e o e-mail) saiu com o Quadro, a Conversa e o e-mail da aba (issue
#1386, ADR 0077): a Etapa e o que a lista do chat mostra.

O I/O do GitHub e todo do `github_client`; a regra da Etapa e toda do
`tecnologia_vinculo`. Aqui mora so a costura entre os dois e o banco.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.services import github_client
from app.services.registro_do_deploy import subida_de_cada_issue
from app.services.tecnologia import (
    ESTADOS_ABERTOS,
    ESTADOS_FECHADOS,
    TABELA_DEMANDAS,
)
from app.services.tecnologia_vinculo import (
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
    ETAPA_REGISTRADA,
    etapa_da_foto,
    normalizar_github_login,
    o_que_muda_da_foto,
    partes_da_foto,
    partes_para_o_diretor,
)

logger = logging.getLogger(__name__)

# As acoes do evento `issues` que podem mexer na foto (issue #678).
#
# `opened` fica de fora porque uma issue recem-aberta nao tem Demanda vinculada
# ainda: o Vinculo nasce depois, e ja sincroniza na hora em que e criado. A
# troca de dono (`assigned`, `unassigned`) entra desde a issue #1534: o
# Responsavel e derivado do assignee (ADR 0083, decisao 6). As demais acoes
# (`milestoned`, `pinned`) nao tocam em label, estado, corpo nem dono.
ACOES_DE_ISSUE = ("labeled", "unlabeled", "closed", "reopened", "edited", "assigned", "unassigned")

# As acoes do evento `pull_request` que mexem no fato do PR (issue #1064, ADR
# 0069, decisao 6). Abrir e reabrir poem o PR na foto; fechar o tira, e o merge
# ainda grava "fechada por PR". `edited` e `synchronize` (push novo no PR) nao
# mudam se ha PR aberto, e quem corrige a referencia editada e a reconciliacao.
ACOES_DE_PR = ("opened", "reopened", "closed")

# Os dois fatos do PR, gravados DENTRO da foto da issue (issue #1064).
#
# Moram na foto, e nao em coluna propria, porque sao fatos do GitHub sobre a
# issue, e a foto e onde o app guarda o que leu de la. So entram quando dizem
# algo: uma foto sem PR nenhum continua identica a de antes desta fatia, e a
# guarda do cache igual nao regrava todas as Demandas na primeira passagem.
#
# `prs_abertos` e a LISTA dos numeros, e nao um booleano: com dois PRs abertos
# para a mesma raiz, fechar um sem merge nao pode apagar o fato do outro.
# `fechada_por_pr` e o numero do PR mergeado que leva subida (ADR 0069,
# decisao 5).
FATO_PRS_ABERTOS = "prs_abertos"
FATO_FECHADA_POR_PR = "fechada_por_pr"

# Quantas vezes a sincronizacao rele a Demanda e tenta de novo quando outra
# escrita passou na frente (issue #1064). O merge manda dois eventos no mesmo
# segundo, e com o lote de hora em hora sao, no pior caso, tres escritores.
TENTATIVAS_DA_ESCRITA = 3

# Quais Demandas o lote de hora em hora rele.
#
# A lista e a POSITIVA, e nao "tudo menos concluida e cancelada", porque no
# PostgREST um filtro de negacao sobre coluna com NULL descarta as linhas nulas
# em silencio. O teste amarra esta tupla ao complemento de `ESTADOS_FECHADOS`:
# um estado novo que ficasse de fora sumiria da reconciliacao sem erro nenhum.
ESTADOS_DA_RECONCILIACAO = ESTADOS_ABERTOS


def mudanca_da_foto(foto: dict[str, Any], *, versao_em_producao: str | None = None) -> dict[str, Any]:
    """O cache da Demanda para esta foto: Etapa, partes, "O que muda" e carimbo.

    Um lugar so para o SHAPE do cache. Ele e escrito por tres caminhos (vincular,
    webhook e reconciliacao), e montar o dicionario a mao em cada um deles faria
    uma coluna nova nascer preenchida num caminho e parada nos outros dois. Foi
    o que quase aconteceu com o `o_que_muda` da issue #676, que entrou pelo
    `vincular`: sem esta funcao, o bloco que o diretor le congelaria no texto do
    dia do Vinculo e a edicao dele no GitHub nunca chegaria ao card.

    `versao_em_producao` e o fato do app que segura Em producao (issue #1065):
    quem chama passa a versao so quando a Demanda JA esta Em producao
    (`_versao_que_segura`), e nunca a que sobrou de uma subida anterior.
    """
    entregues, total = partes_da_foto(foto)
    return {
        "etapa": etapa_da_foto(foto, versao_em_producao=versao_em_producao, pr_aberto=bool(foto.get(FATO_PRS_ABERTOS))),
        "partes_entregues": entregues,
        "partes_total": total,
        # O texto que o diretor le, lido do GitHub e nunca digitado no app
        # (issue #676, ADR 0054, decisao 7). Em coluna propria, e nao so dentro
        # da foto, porque e dado de leitura da tela: a foto existe para a
        # sincronizacao seguinte saber se algo mudou.
        "o_que_muda": o_que_muda_da_foto(foto),
        "partes": partes_para_o_diretor(foto),
        "github_foto": foto,
        "github_sincronizado_em": datetime.now(UTC).isoformat(),
    }


# A unica coluna do cache que muda a cada leitura, e por isso fica FORA da
# comparacao: incluida, ela diria "mudou" toda vez e a guarda de baixo nunca
# calaria ninguem.
CARIMBO_DA_SINCRONIZACAO = "github_sincronizado_em"


def cache_desatualizado(demanda: dict[str, Any], mudanca: dict[str, Any]) -> bool:
    """Se o que esta gravado na Demanda ja diz o que esta mudanca diria.

    A pergunta e sobre o DERIVADO, e nao sobre a foto crua (issue #690). Etapa,
    partes, "O que muda" e as contagens sao funcoes puras da foto, e a REGRA que
    as calcula muda com o app: basta uma label nova em `LABELS_PLANEJADA` ou um
    fim de bloco diferente no "Para o diretor". Comparando so o `github_foto`,
    toda Demanda cujo issue nao mexesse mais no GitHub ficaria com o valor da
    regra velha para sempre, e a reconciliacao de hora em hora passaria por ela
    sem consertar nada, porque a foto continua identica.

    A foto entra na conta junto com os derivados: ela e uma das colunas de
    `mudanca_da_foto`, e comparar todas de uma vez mantem esta guarda com um
    criterio so. Uma coluna nova no cache passa a ser comparada sozinha.
    """
    return any(valor != demanda.get(campo) for campo, valor in mudanca.items() if campo != CARIMBO_DA_SINCRONIZACAO)


def responsavel_da_foto(supabase, foto: dict[str, Any]) -> str | None:
    """O Responsavel que a foto diz: quem tem no cadastro o login do dono da
    issue (issue #1534, ADR 0083, decisao 6). `None` sem dono, ou com um dono
    que nao e usuario do app, e a lista o mostra pelo login.

    O login e unico no cadastro e gravado em minusculas
    (`normalizar_github_login`), o que o GitHub manda pode vir com maiusculas.
    """
    login = normalizar_github_login(foto.get(github_client.FATO_ASSIGNEE))
    if not login:
        return None
    result = supabase.table("participantes").select("id").eq("github_login", login).execute()
    linhas = result.data or []
    return str(linhas[0]["id"]) if linhas else None


def demanda_vinculada(supabase, numero: int) -> dict[str, Any] | None:
    """A Demanda que carrega este numero de issue, ou `None`.

    `None` e resposta, e nao erro: o repositorio tem centenas de issues e um
    punhado de Demandas vinculadas, entao a esmagadora maioria das entregas do
    webhook cai aqui e termina em 2xx sem escrever nada.
    """
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("github_issue_numero", numero).execute()
    linhas = result.data or []
    return linhas[0] if linhas else None


def _fatos_anteriores(demanda: dict[str, Any]) -> tuple[list[int], int | None]:
    """Os fatos do PR que a foto guardada ja carrega.

    A issue relida do GitHub nao diz nada sobre PR, entao uma sincronizacao
    pelo evento `issues` (uma label, uma edicao do corpo) apagaria o fato que o
    webhook `pull_request` gravou. Por isso todo caminho parte daqui e so troca
    o que ele mesmo sabe.
    """
    foto = demanda.get("github_foto")
    if not isinstance(foto, dict):
        return [], None
    abertos = [n for n in (foto.get(FATO_PRS_ABERTOS) or []) if isinstance(n, int)]
    fechada = foto.get(FATO_FECHADA_POR_PR)
    return abertos, fechada if isinstance(fechada, int) else None


def _pr_leva_subida(pr: int) -> bool:
    """Se o PR mergeado toca no app; "nao sei" vale "nao" (`sincronizar_pelo_pr`)."""
    try:
        return github_client.pr_toca_o_app(pr)
    except Exception:
        logger.warning(
            "[tecnologia] Falha ao ler os arquivos do PR #%s; o fechamento conta como sem subida.",
            pr,
            exc_info=True,
        )
        return False


def sincronizar_pelo_pr(supabase, demanda: dict[str, Any], *, pr: int, acao: str, mergeado: bool) -> bool:
    """O evento `pull_request` aplicado a uma Demanda cuja raiz o PR fecha.

    Abrir (ou reabrir) poe o PR entre os abertos; fechar o tira, com ou sem
    merge. So o merge grava "fechada por PR": o PR fechado sem merge apenas
    deixa de contar, e a Etapa volta a ser o que as labels e as partes dizem
    (ADR 0069, decisao 6).

    Vai como TROCA, e nao como a lista pronta: se outra escrita passar na
    frente, a troca e reaplicada sobre os fatos que ela gravou.

    O merge so grava "fechada por PR" quando o PR leva uma subida, isto e,
    toca no app (revisao do PR #1100). O PR de ferramenta e so merge: sem
    entrada no `history.json` e sem webhook de deploy, Em producao nunca
    chegaria. Se a leitura dos arquivos falhar, vale o mesmo: a issue conta
    como fechada sem PR (ADR 0069, decisao 5).
    """
    leva_subida = mergeado and _pr_leva_subida(pr)

    def _ajustar(abertos: list[int], fechada: int | None) -> tuple[list[int], int | None]:
        abertos = [n for n in abertos if n != pr]
        if acao in ("opened", "reopened"):
            abertos.append(pr)
        elif leva_subida:
            fechada = pr
        return abertos, fechada

    return sincronizar_demanda(supabase, demanda, ajustar_fatos=_ajustar)


# O que um gatilho sabe dos fatos do PR, como troca sobre os fatos guardados:
# recebe (abertos, fechada_por_pr) e devolve o par novo.
AjusteDosFatos = Callable[[list[int], int | None], tuple[list[int], int | None]]


def _com_os_fatos(
    foto: dict[str, Any], demanda: dict[str, Any], ajustar_fatos: AjusteDosFatos | None
) -> dict[str, Any]:
    """A foto lida do GitHub com os fatos do PR desta linha da Demanda, ja
    trocados por quem chamou. Copia nova a cada tentativa, porque cada uma parte
    da linha que acabou de ler."""
    abertos, fechada = _fatos_anteriores(demanda)
    if ajustar_fatos is not None:
        abertos, fechada = ajustar_fatos(abertos, fechada)
    foto = dict(foto)
    if abertos:
        foto[FATO_PRS_ABERTOS] = sorted(set(abertos))
    if fechada is not None:
        foto[FATO_FECHADA_POR_PR] = fechada
    return foto


def _versao_que_segura(demanda: dict[str, Any]) -> str | None:
    """A versao que mantem a Demanda Em producao enquanto a issue segue entregue.

    So vale com a Etapa JA em Em producao: quem a pos la foi a subida
    (`_carimbar_em_producao`), e a releitura da issue fechada nao tem como
    saber disso sozinha. A coluna pode guardar a versao de uma subida anterior
    com a Etapa que voltou atras (a issue reaberta para um ajuste), e passa-la
    adiante faria o proximo fechamento pular direto para Em producao com a
    versao velha, antes de a correcao subir.
    """
    if demanda.get("etapa") != ETAPA_EM_PRODUCAO:
        return None
    return demanda.get("versao_em_producao") or None


def _reler(supabase, demanda_id: str) -> dict[str, Any] | None:
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("id", demanda_id).execute()
    linhas = result.data or []
    return linhas[0] if linhas else None


def sincronizar_demanda(
    supabase,
    demanda: dict[str, Any],
    *,
    ajustar_fatos: AjusteDosFatos | None = None,
) -> bool:
    """Rele a issue vinculada e atualiza o cache da Demanda. `True` se mudou.

    `ajustar_fatos` e o que quem chama sabe dos fatos do PR (issue #1064).
    `None` quer dizer "nao sei", e o que vale e o que a foto guardada ja dizia:
    e o caso do evento `issues`, que nao fala de PR.

    **A escrita trava em `atualizado_em`**, que o gatilho da migration 102 troca
    a cada UPDATE. Ao mergear um PR com `Closes #N`, o GitHub manda
    `pull_request.closed` e `issues.closed` no mesmo segundo, e os dois leem a
    Demanda antes das chamadas ao GitHub. Sem a trava, quem escrevesse por
    ultimo regravaria os fatos do PR da foto que leu, e o evento `issues`
    apagaria o `fechada_por_pr`, que o GitHub nao reentrega e a reconciliacao
    nao recupera. Quem perde a trava rele a linha e refaz a conta sobre os fatos
    que o outro gravou, com a MESMA leitura do GitHub.

    NAO trata excecao: `GithubIndisponivelError` e `IssueNaoEncontradaError` sobem
    para quem chamou, porque o desfeito e diferente nos dois gatilhos. O webhook
    engole e responde 2xx (o GitHub nao reentrega, e insistir nao traria o evento
    de volta); o lote conta a falha e segue para a proxima Demanda.

    Demanda Concluida ou Cancelada (o estado de antes da ADR 0077, congelado na
    coluna) nao e tocada, pelos DOIS gatilhos. O lote ja nem a le (o filtro de
    estado poupa a cota do GitHub), mas a guarda mora aqui e nao la, porque o
    webhook chega pelo numero da issue e nao tem esse filtro: sem ela, os dois
    caminhos que a issue chama de "a mesma rotina" se comportariam diferente.
    """
    numero = demanda.get("github_issue_numero")
    if not numero:
        return False
    if str(demanda.get("estado") or "") in ESTADOS_FECHADOS:
        return False
    numero = int(numero)

    dados = github_client.ler_issue(numero)
    foto_do_github = github_client.montar_foto(dados, github_client.ler_sub_issues(numero))
    # O Responsavel e derivado do dono da issue, como a Etapa das labels
    # (issue #1534): entra no cache e na comparacao do cache igual.
    responsavel_id = responsavel_da_foto(supabase, foto_do_github)
    demanda_id = str(demanda["id"])

    for _ in range(TENTATIVAS_DA_ESCRITA):
        mudanca = mudanca_da_foto(
            _com_os_fatos(foto_do_github, demanda, ajustar_fatos), versao_em_producao=_versao_que_segura(demanda)
        )
        mudanca["responsavel_id"] = responsavel_id
        if not cache_desatualizado(demanda, mudanca):
            return False
        etapa_antes = demanda.get("etapa") or ETAPA_REGISTRADA
        muda_a_etapa = mudanca["etapa"] != etapa_antes
        if _escrever(supabase, demanda, mudanca, etapa_antes=etapa_antes, muda_a_etapa=muda_a_etapa):
            break
        # Outra escrita passou na frente. A linha relida traz os fatos do PR que
        # ela gravou e a Etapa que ela moveu: a proxima volta parte dali.
        relida = _reler(supabase, demanda_id)
        if relida is None or str(relida.get("estado") or "") in ESTADOS_FECHADOS:
            return False
        demanda = relida
    else:
        logger.warning(
            "[tecnologia] A Demanda %s foi escrita por outro caminho %s vezes seguidas; esta sincronização "
            "desistiu, e a reconciliação da hora seguinte relê a issue.",
            demanda_id,
            TENTATIVAS_DA_ESCRITA,
        )
        return False

    return True


def _escrever(
    supabase, demanda: dict[str, Any], mudanca: dict[str, Any], *, etapa_antes: str, muda_a_etapa: bool
) -> bool:
    """O UPDATE do cache, so se ninguem escreveu na Demanda desde a leitura.

    `False` quando a linha nao casou: outra escrita passou na frente, e quem
    chamou rele e tenta de novo.
    """
    consulta = (
        supabase.table(TABELA_DEMANDAS)
        .update(mudanca)
        .eq("id", str(demanda["id"]))
        # A trava dos fatos do PR (issue #1064): toda escrita troca o carimbo,
        # entao os fatos que este UPDATE regrava sao os da linha que foi lida.
        # A coluna e NOT NULL com default na migration 102.
        .eq("atualizado_em", demanda.get("atualizado_em"))
    )
    if muda_a_etapa:
        # Trava otimista, e nao enfeite: o job roda numa THREAD do
        # `BackgroundScheduler` e o webhook roda no event loop, entao entre o
        # `select` de um e o `update` do outro ha uma janela sem trava. Os dois
        # leriam `etapa_antes` igual e os dois achariam que a Etapa mudou.
        #
        # O `.eq("etapa", ...)` transforma o UPDATE num compare-and-swap: o
        # Postgres serializa a linha, e so um dos dois casa. Quem perde rele a
        # Demanda, ve a Etapa ja movida, e so regrava a foto se ainda houver o
        # que mudar nela.
        #
        # A coluna e NOT NULL com default na migration 103, entao o `.eq` nao cai
        # na armadilha do PostgREST de descartar linha com valor nulo.
        consulta = consulta.eq("etapa", etapa_antes)
    return bool(consulta.execute().data)


def _prs_abertos_do_lote() -> list[dict[str, Any]] | None:
    """Os PRs abertos do repositorio, lidos uma vez para o lote inteiro.

    `None` quando a leitura falha, e nao lista vazia: "nao consegui ler" virando
    "nao ha PR aberto" tiraria o fato de toda Demanda numa queda do GitHub, e o
    card voltaria para tras sem ninguem ter fechado PR nenhum. Com `None`, cada
    Demanda fica com o fato que a foto ja tinha, e o lote segue.
    """
    try:
        return github_client.ler_prs_abertos()
    except Exception:
        logger.warning(
            "[tecnologia] Falha ao ler os PRs abertos; a reconciliação segue com o fato de PR que cada foto já tinha.",
            exc_info=True,
        )
        return None


def marcar_em_producao(supabase, *, versao: str, data: str, issues: list[int]) -> dict[str, int]:
    """A subida chegou: Em produção nas Demandas destas issues (issue #1065).

    `versao` ja vem rotulada ("v0.169.0") e `issues` sao as que os PRs do lote
    fecham. Cada Demanda vinculada a uma delas passa por `_carimbar_em_producao`;
    as outras issues (a esmagadora maioria) nao tem Demanda nenhuma atras.

    Falha e de UMA Demanda, como no lote de hora em hora: a seguinte ainda e
    marcada, e a contagem diz quantas ficaram para tras.
    """
    marcadas = 0
    falhas = 0
    for numero in sorted(set(issues)):
        demanda = None
        try:
            demanda = demanda_vinculada(supabase, numero)
            if demanda is not None and _carimbar_em_producao(supabase, demanda, versao=versao, data=data):
                marcadas += 1
        except Exception:
            falhas += 1
            logger.warning(
                "[tecnologia] Falha ao marcar Em produção na %s a Demanda %s (issue #%s).",
                versao,
                (demanda or {}).get("id"),
                numero,
                exc_info=True,
            )
    return {"marcadas": marcadas, "falhas": falhas}


def _carimbar_em_producao(supabase, demanda: dict[str, Any], *, versao: str, data: str) -> bool:
    """Em producao nesta Demanda, se ela estiver Entregue. `True` se marcou.

    **So a Entregue sobe**, e e isso que faz o carimbo idempotente por
    (Demanda, versao): a segunda chamada com a mesma versao encontra Em producao
    e sai sem gravar. Pelo mesmo motivo uma subida
    seguinte que liste a mesma issue nao troca a versao: "Em producao desde"
    e a PRIMEIRA. A issue reaberta tira a Demanda de Em producao pela
    sincronizacao, e o proximo fechamento espera a proxima subida.

    O UPDATE e um compare-and-swap na Etapa, como o da sincronizacao: o webhook
    de deploy roda no threadpool e a reconciliacao numa thread do scheduler, e
    so um dos dois a move.

    Demanda fechada (Concluida ou Cancelada antes da ADR 0077) nao e tocada,
    pelo mesmo motivo da sincronizacao. As duas regras moram no proprio UPDATE,
    e nao num `if` antes dele: conferidas na linha lida, deixariam passar quem
    mudou a Demanda entre a leitura e a escrita.
    """
    demanda_id = str(demanda["id"])
    marcada = (
        supabase.table(TABELA_DEMANDAS)
        .update({"etapa": ETAPA_EM_PRODUCAO, "versao_em_producao": versao, "entregue_em": data})
        .eq("id", demanda_id)
        .eq("etapa", ETAPA_ENTREGUE)
        .in_("estado", list(ESTADOS_ABERTOS))
        .execute()
    )
    return bool(marcada.data)


def _subiu_depois_do_fechamento(data_da_subida: str, fechada_em: object) -> bool:
    """Se a subida e de DEPOIS do fechamento atual da issue (revisao do PR #1100).

    A entrada mais nova do `history.json` que lista a issue pode ser a de um
    fechamento ANTERIOR: a issue subiu, reabriu para um ajuste, o PR do ajuste
    foi mergeado, e a subida dele ainda nao foi registrada (build, health e a
    Action pos-merge; na onda, todos os merges antes de um build so). Carimbar
    essa entrada gravaria "Em producao desde" a versao velha com o ajuste fora
    do ar, e o webhook da subida certa ja nao corrigiria nada.

    O registro e gravado depois do health, e o merge fecha a issue antes do
    build: a subida que levou o fechamento atual tem sempre data posterior ao
    `closed_at`. Sem `closed_at` legivel nao ha como provar, e a Demanda espera
    o webhook ou a passagem seguinte.
    """
    if not isinstance(fechada_em, str):
        return False
    try:
        return datetime.fromisoformat(data_da_subida) > datetime.fromisoformat(fechada_em)
    except (TypeError, ValueError):
        return False


def reconciliar_em_producao(supabase) -> dict[str, int]:
    """O par do webhook de deploy no lote de hora em hora (ADR 0069, decisao 4).

    A Action pode nao ter avisado: o segredo ainda nao cadastrado, o app
    reiniciando na hora, a rede. O registro da subida esta no `history.json` da
    `main` do mesmo jeito, e esta passagem marca Em producao cada Demanda
    Entregue cuja issue aparece numa subida registrada, com a versao e a data
    da mais nova que a lista (`subida_de_cada_issue`), desde que essa subida
    seja de depois do fechamento atual da issue (`_subiu_depois_do_fechamento`,
    que rele a issue para o `closed_at`).

    Roda DEPOIS do `reconciliar_vinculos`, que pode ter acabado de levar a
    Demanda a Entregue (o `issues.closed` que o webhook perdeu). Sem Demanda
    Entregue aberta, o arquivo nem e lido: a cota do GitHub e uma so.

    O carimbo e o mesmo do webhook (`_carimbar_em_producao`), e por isso a
    mesma idempotencia.
    """
    result = (
        supabase.table(TABELA_DEMANDAS)
        .select("*")
        .eq("etapa", ETAPA_ENTREGUE)
        .in_("estado", list(ESTADOS_ABERTOS))
        .not_.is_("github_issue_numero", "null")
        .execute()
    )
    entregues = result.data or []
    if not entregues:
        return {"lidas": 0, "marcadas": 0, "falhas": 0}

    try:
        subidas = subida_de_cada_issue(github_client.ler_historico_de_deploys())
    except Exception:
        logger.warning(
            "[tecnologia] Falha ao ler o history.json da main; Em produção fica para a próxima passagem.",
            exc_info=True,
        )
        return {"lidas": len(entregues), "marcadas": 0, "falhas": len(entregues)}

    marcadas = 0
    falhas = 0
    for demanda in entregues:
        numero = int(demanda["github_issue_numero"])
        subida = subidas.get(numero)
        if subida is None:
            continue
        versao, data = subida
        try:
            if not _subiu_depois_do_fechamento(data, github_client.ler_issue(numero).get("closed_at")):
                continue
            if _carimbar_em_producao(supabase, demanda, versao=versao, data=data):
                marcadas += 1
        except Exception:
            falhas += 1
            logger.warning(
                "[tecnologia] Falha ao marcar Em produção na %s a Demanda %s pela reconciliação.",
                versao,
                demanda.get("id"),
                exc_info=True,
            )
    if marcadas or falhas:
        logger.info("[tecnologia] Em produção pelo history.json: %s marcada(s), %s falha(s).", marcadas, falhas)
    return {"lidas": len(entregues), "marcadas": marcadas, "falhas": falhas}


def reconciliar_vinculos(supabase) -> dict[str, int]:
    """O lote de hora em hora: toda Demanda vinculada que ainda esta aberta.

    Existe porque o webhook e o unico caminho rapido, e ele e perdivel: o GitHub
    exige 2xx em 10 segundos e nao reentrega a entrega que falhou. Um deploy no
    momento errado, uma queda de rede ou um erro nosso somem com o evento, e sem
    esta passagem a Etapa ficaria mentindo ate alguem reparar.

    Devolve `{"lidas", "mudadas", "falhas"}`, que e o que o log conta. Falha numa
    Demanda e contada e registrada com o identificador dela; o lote segue.
    """
    result = (
        supabase.table(TABELA_DEMANDAS)
        .select("*")
        .not_.is_("github_issue_numero", "null")
        .in_("estado", list(ESTADOS_DA_RECONCILIACAO))
        .execute()
    )
    demandas = result.data or []
    prs_abertos = _prs_abertos_do_lote() if demandas else None

    mudadas = 0
    falhas = 0
    for demanda in demandas:
        try:
            ajustar = None
            if prs_abertos is not None:
                numero = demanda.get("github_issue_numero")
                abertos = [pr["numero"] for pr in prs_abertos if numero in pr["fecha"]]
                # A lista do GitHub substitui a guardada; o `fechada_por_pr` fica.
                ajustar = lambda _guardados, fechada, abertos=abertos: (abertos, fechada)  # noqa: E731
            if sincronizar_demanda(supabase, demanda, ajustar_fatos=ajustar):
                mudadas += 1
        except github_client.IssueNaoEncontradaError:
            # Condicao PERMANENTE: a issue foi apagada ou transferida. Uma linha,
            # sem stack. Tratada como as outras falhas seria um traceback inteiro
            # por HORA, para sempre, sobre algo que nao se auto-resolve.
            falhas += 1
            logger.warning(
                "[tecnologia] A issue #%s da Demanda %s não existe mais no repositório.",
                demanda.get("github_issue_numero"),
                demanda.get("id"),
            )
        except Exception:
            # Qualquer causa, de proposito: `except GithubIndisponivelError`
            # deixaria o timeout do PostgREST subir cru e derrubar o lote na
            # metade, com as Demandas seguintes sem reconciliar e sem rastro.
            falhas += 1
            logger.warning(
                "[tecnologia] Falha ao reconciliar a Demanda %s (issue #%s)",
                demanda.get("id"),
                demanda.get("github_issue_numero"),
                exc_info=True,
            )

    if demandas:
        logger.info(
            "[tecnologia] Reconciliação do Vínculo: %s lida(s), %s mudada(s), %s falha(s).",
            len(demandas),
            mudadas,
            falhas,
        )
    return {"lidas": len(demandas), "mudadas": mudadas, "falhas": falhas}
