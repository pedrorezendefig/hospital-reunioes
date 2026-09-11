"""A Demanda vinculada relendo o GitHub (issue #678, PRD #673, ADR 0054).

Uma rotina, dois gatilhos. `sincronizar_demanda` le a issue, monta a foto,
compara com a guardada e, se mudou, grava o cache e a linha automatica da Etapa.
Quem a chama e o webhook (em segundos, pelo numero da issue do payload) e o job
de hora em hora (sobre o lote inteiro). O par webhook + reconciliacao e o mesmo
molde da ClickSign, e existe pelo mesmo motivo: o GitHub NAO reentrega webhook
que falhou, e sem a segunda passagem um container reiniciando na hora errada
congelaria o selo do card ate alguem mexer nele a mao.

Tres invariantes que valem pelos dois caminhos:

- **Foto igual nao escreve NADA.** Nem a linha do fio, nem o `UPDATE`, nem o
  carimbo da ultima sincronizacao. E o que faz a entrega repetida do GitHub e a
  passagem de hora em hora serem inofensivas: sem esta guarda, o fio do diretor
  ganharia uma linha por hora dizendo a mesma coisa.
- **Etapa igual nao grava linha.** Um degrau abaixo da guarda acima: editar o
  corpo da issue muda a foto sem mudar a Etapa, e o cache precisa acompanhar
  enquanto o fio fica calado.
- **Falha e de UMA Demanda.** No lote, o `except` e por linha e por qualquer
  causa (o GitHub fora do ar e o timeout do PostgREST chegam por portas
  diferentes), e o log guarda o identificador.

Desde a issue #679 a rotina tambem DEVOLVE a Demanda a quem pediu quando a
Etapa chega a Entregue: Aguardando, com o autor como responsavel, as duas
linhas automaticas e o e-mail de atribuicao com o recado "Entregue, confira e
conclua". Fica aqui, e nao no router, porque este e o caminho comum dos dois
gatilhos: escrito la, a devolucao valeria para o webhook e nao para o lote.

O I/O do GitHub e todo do `github_client`; a regra da Etapa e toda do
`tecnologia_vinculo`. Aqui mora so a costura entre os dois e o banco.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.services import github_client
from app.services.tecnologia import (
    AUTOR_DA_ENTREGA,
    ESTADO_AGUARDANDO,
    ESTADOS_ABERTOS,
    ESTADOS_FECHADOS,
    RECADO_DA_ENTREGA,
    SEM_EFEITO,
    TABELA_CONVERSAS,
    TABELA_DEMANDAS,
    TABELA_PARTICIPANTES,
    TABELA_PRODUTOS,
    e_pessoa_da_aba,
    efeito_da_etapa,
    linha_de_movimento,
    texto_movimento_estado,
    texto_movimento_responsavel,
)
from app.services.tecnologia_email import avisar_atribuicao
from app.services.tecnologia_vinculo import (
    ETAPA_REGISTRADA,
    etapa_da_foto,
    foto_mudou,
    o_que_muda_da_foto,
    partes_da_foto,
    partes_para_o_diretor,
    texto_movimento_etapa,
)

logger = logging.getLogger(__name__)

# As acoes do evento `issues` que podem mexer na foto (issue #678).
#
# `opened` fica de fora porque uma issue recem-aberta nao tem Demanda vinculada
# ainda: o Vinculo nasce depois, e ja sincroniza na hora em que e criado. As
# demais acoes (`assigned`, `milestoned`, `pinned`) nao tocam em label, estado
# nem corpo, que sao os tres campos de que a Etapa e o "O que muda" vivem.
ACOES_DE_ISSUE = ("labeled", "unlabeled", "closed", "reopened", "edited")

# Quais Demandas o lote de hora em hora rele.
#
# A lista e a POSITIVA, e nao "tudo menos concluida e cancelada", porque no
# PostgREST um filtro de negacao sobre coluna com NULL descarta as linhas nulas
# em silencio. O teste amarra esta tupla ao complemento de `ESTADOS_FECHADOS`:
# um estado novo que ficasse de fora sumiria da reconciliacao sem erro nenhum.
ESTADOS_DA_RECONCILIACAO = ESTADOS_ABERTOS


def mudanca_da_foto(foto: dict[str, Any]) -> dict[str, Any]:
    """O cache da Demanda para esta foto: Etapa, partes, "O que muda" e carimbo.

    Um lugar so para o SHAPE do cache. Ele e escrito por tres caminhos (vincular,
    webhook e reconciliacao), e montar o dicionario a mao em cada um deles faria
    uma coluna nova nascer preenchida num caminho e parada nos outros dois. Foi
    o que quase aconteceu com o `o_que_muda` da issue #676, que entrou pelo
    `vincular`: sem esta funcao, o bloco que o diretor le congelaria no texto do
    dia do Vinculo e a edicao dele no GitHub nunca chegaria ao card.
    """
    entregues, total = partes_da_foto(foto)
    return {
        "etapa": etapa_da_foto(foto),
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


def demanda_vinculada(supabase, numero: int) -> dict[str, Any] | None:
    """A Demanda que carrega este numero de issue, ou `None`.

    `None` e resposta, e nao erro: o repositorio tem centenas de issues e um
    punhado de Demandas vinculadas, entao a esmagadora maioria das entregas do
    webhook cai aqui e termina em 2xx sem escrever nada.
    """
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("github_issue_numero", numero).execute()
    linhas = result.data or []
    return linhas[0] if linhas else None


def _gravar_linha(supabase, *, demanda_id: str, campo: str, de: str | None, para: str | None, texto: str) -> None:
    """A linha automatica do fio, com o desfecho DESTE lado.

    A forma da linha e uma so (`linha_de_movimento`); o que muda e quem tem como
    reagir a falha dela. O router devolve 500 com a frase honesta a quem clicou;
    aqui nao ha ninguem clicando, e a falha sobe para o webhook (que responde
    2xx com `falhou: true`) ou para o lote (que conta a falha e segue). Por isso
    este helper nao engole excecao: engolir apagaria a unica noticia que os dois
    gatilhos tem de que o fio ficou incompleto.
    """
    supabase.table(TABELA_CONVERSAS).insert(
        linha_de_movimento(demanda_id=demanda_id, campo=campo, de=de, para=para, texto=texto)
    ).execute()


# O que a peneira de acesso precisa ler do participante.
#
# `ativo` e `is_super_admin`/`access_profile` entram porque o filtro roda em
# Python (`e_pessoa_da_aba`): um `.eq("ativo", True)` no PostgREST descartaria
# as linhas com `ativo` NULL, que contam como ativas. `nome_completo` entra
# porque a linha do fio o mostra, e essa e a mesma consulta.
_CAMPOS_DA_PESSOA = "id, nome_completo, ativo, is_super_admin, access_profile"


def _pessoa_da_aba(supabase, pessoa_id: str) -> dict[str, Any] | None:
    """O autor, se ele AINDA ve a aba. `None` quando ele saiu.

    A pergunta e a mesma que o `atribuir` do router faz antes de trocar o
    responsavel, e existe pelo mesmo motivo escrito la: entregar a Demanda a
    quem nao pode abri-la a deixa parada sem ninguem saber por que. Na devolucao
    automatica o silencio seria pior, porque ninguem clicou para receber um erro:
    o card sumiria da "Minha vez" de todo mundo (ninguem seria responsavel, e a
    mencao nao existe) e o e-mail tambem nao sairia, porque o `_mandar` pula quem
    nao passa nesta mesma peneira e so registra um INFO.

    Uma consulta so para as duas coisas: se a pessoa ainda esta na aba e como ela
    se chama. Sao a mesma leitura, e separa-las pagaria duas.
    """
    result = supabase.table(TABELA_PARTICIPANTES).select(_CAMPOS_DA_PESSOA).eq("id", pessoa_id).execute()
    linhas = result.data or []
    pessoa = linhas[0] if linhas else None
    return pessoa if e_pessoa_da_aba(pessoa) else None


def _avisar_a_devolucao(supabase, demanda: dict[str, Any], *, destinatario_id: str) -> None:
    """O e-mail de atribuicao que ja existe, com o recado da Entrega.

    E o MESMO gatilho da atribuicao feita a mao (`avisar_atribuicao`), e nao um
    quarto e-mail: o que muda e o trecho que motiva o aviso, que aqui e
    "Entregue, confira e conclua" em vez da descricao do pedido.

    O nome do Produto e lido aqui porque o e-mail o mostra, e a Demanda que a
    sincronizacao tem em maos e a LINHA do banco, sem o `produto_nome` que o
    router resolve no `_com_nomes`. Sem esta leitura o aviso diria "(sem
    Produto)" sobre uma Demanda que tem Produto.

    E ela roda dentro de um `try` pelo mesmo motivo do `_aviso_da_correcao` do
    router: acontece com a devolucao JA GRAVADA, e um timeout do PostgREST (que
    sobe cru, porque nao e `APIError`) faria o webhook responder `falhou: true`
    sobre um movimento que valeu. A reconciliacao seguinte veria a foto igual e
    nao repetiria nada: o aviso se perderia de vez. Falha de aviso e aviso que
    nao saiu, e nao acao desfeita.

    `avisar_atribuicao` nunca levanta (o `_mandar` tem `except` largo e devolve
    `False`), entao o e-mail que nao sai vira log, e nao excecao.
    """
    produto_nome = None
    produto_id = demanda.get("produto_id")
    if produto_id:
        try:
            result = supabase.table(TABELA_PRODUTOS).select("nome").eq("id", produto_id).execute()
            linhas = result.data or []
            produto_nome = linhas[0].get("nome") if linhas else None
        except Exception:
            logger.warning(
                "[tecnologia] Falha ao ler o Produto da Demanda %s para o aviso da entrega.",
                demanda.get("id"),
                exc_info=True,
            )
    avisar_atribuicao(
        supabase,
        demanda={**demanda, "produto_nome": produto_nome},
        destinatario_id=destinatario_id,
        quem_fez_nome=AUTOR_DA_ENTREGA,
        trecho=RECADO_DA_ENTREGA,
    )


def _devolver_a_quem_pediu(supabase, demanda: dict[str, Any], *, etapa_nova: str) -> None:
    """A Entrega devolve a bola a quem pediu (issue #679, ADR 0054, decisao 6).

    Quem decide SE ha devolucao e o que ela faz e o servico puro
    (`efeito_da_etapa`); aqui mora so a costura com o banco, nas mesmas duas
    rotinas que o Quadro ja usa a mao: mover (com a amarra no estado lido) e
    atribuir (linha do fio, depois o e-mail).

    **A devolucao para no primeiro passo que nao casa.** Se o UPDATE do estado
    nao casar linha nenhuma, alguem mexeu no card entre a leitura e agora, e
    esse alguem e gente: pode ter acabado de concluir a Demanda. Atribuir
    assim mesmo entregaria a um responsavel novo um card que a pessoa fechou.

    **O e-mail vem depois da linha do fio**, como no `atribuir` do router: se o
    fio falhar, o aviso nem chega a ser montado, e ninguem recebe "a Demanda e
    sua" sobre um card com a trilha quebrada.

    Nao ha aqui uma segunda checagem de "ja avisei": a corrida entre o webhook e
    o lote morre no compare-and-swap da Etapa, um degrau acima, e so a thread
    que mudou a Etapa chega ate esta funcao.
    """
    efeito = efeito_da_etapa(demanda, etapa_nova=etapa_nova)
    if efeito == SEM_EFEITO:
        return

    demanda_id = str(demanda["id"])
    if efeito.mover_para:
        estado_antes = str(demanda.get("estado") or "")
        movida = (
            supabase.table(TABELA_DEMANDAS)
            .update({"estado": efeito.mover_para})
            .eq("id", demanda_id)
            .eq("estado", estado_antes)
            .execute()
        )
        if not movida.data:
            logger.info(
                "[tecnologia] A Demanda %s saiu de %s antes da entrega devolvê-la; nada foi movido.",
                demanda_id,
                estado_antes,
            )
            return
        _gravar_linha(
            supabase,
            demanda_id=demanda_id,
            campo="estado",
            de=estado_antes,
            para=efeito.mover_para,
            texto=texto_movimento_estado(autor_nome=AUTOR_DA_ENTREGA, para=efeito.mover_para),
        )

    if not efeito.atribuir_a:
        # O autor JA e o responsavel: nao ha atribuicao, e portanto nao ha
        # e-mail. E a mesma regra do `atribuir` do router, que nao grava linha
        # nem avisa quando o responsavel nao muda: o aviso seria "a Demanda e
        # sua" para quem ja a tinha na mao.
        return

    autor = _pessoa_da_aba(supabase, efeito.atribuir_a)
    if autor is None:
        # O card ja foi movido, e fica em Aguardando com o responsavel que
        # tinha: alguem da Vitta continua com ele na "Minha vez" e pode
        # repassa-lo a mao. Entrega-lo a quem saiu o faria sumir da aba de todo
        # mundo, e em silencio, porque o e-mail tambem nao sairia.
        logger.warning(
            "[tecnologia] O autor %s da Demanda %s não está mais na lista de acesso à aba: "
            "a entrega moveu o card e NÃO trocou o responsável.",
            efeito.atribuir_a,
            demanda_id,
        )
        return

    responsavel_antes = demanda.get("responsavel_id")
    atribuida = (
        supabase.table(TABELA_DEMANDAS)
        .update({"responsavel_id": efeito.atribuir_a})
        .eq("id", demanda_id)
        # A MESMA amarra do movimento, e ela precisa estar aqui tambem: quando a
        # Demanda ja estava em Aguardando o bloco de cima nem roda, e sem esta
        # linha o UPDATE casaria so por id. Bastaria alguem concluir o card no
        # intervalo para o fio de uma Demanda FECHADA ganhar "A entrega atribuiu
        # a Fulano" e o e-mail sair para quem acabou de concluir.
        #
        # A amarra e pelo ESTADO, e nao pelo `responsavel_id`: aquela coluna e
        # anulavel, e um `.eq` sobre NULL no PostgREST nao casa linha nenhuma
        # (a Demanda sem responsavel nunca seria devolvida).
        .eq("estado", ESTADO_AGUARDANDO)
        .execute()
    )
    if not atribuida.data:
        # Duas causas possiveis, e daqui nao da para distinguir: alguem mexeu no
        # card no intervalo, ou a escrita nao valeu. O que muda e o RAMO em que
        # este UPDATE nao casou (issue #694), porque os dois deixam o card em
        # lugares diferentes.
        if not efeito.mover_para:
            # A Demanda ja estava em Aguardando: o bloco do movimento nem rodou,
            # e este UPDATE era a UNICA escrita da devolucao. Nao casar significa
            # que NADA foi escrito, e o desfecho e correto: o card esta como
            # estava, o fio intacto, ninguem avisado de nada errado. ERROR aqui
            # viraria alerta por uma corrida bem resolvida, e a mesma corrida um
            # degrau acima (o movimento que nao casa) ja sai em INFO.
            logger.warning(
                "[tecnologia] A devolução da entrega não trocou o responsável da Demanda %s "
                "(alguém mexeu no card, ou a escrita não valeu): nada foi escrito, "
                "o card está como estava.",
                demanda_id,
            )
            return
        # O ramo do movimento, e aqui a devolucao ficou MESMO pela metade: o card
        # ja andou para Aguardando e ja ganhou a linha do fio, ninguem foi
        # avisado, e a passagem seguinte NAO refaz nada (a foto ja gravada barra
        # a releitura). A frase manda CONFERIR antes de refazer, e nao refazer os
        # tres passos: parte deles ja esta feita, e quem le no susto repetiria o
        # movimento que valeu.
        logger.error(
            "[tecnologia] A devolução da entrega NÃO trocou o responsável da Demanda %s "
            "(alguém mexeu no card, ou a escrita não valeu): a devolução ficou pela metade. "
            "Confira o estado do card (movimento, responsável e aviso) antes de terminá-la à mão.",
            demanda_id,
        )
        return
    _gravar_linha(
        supabase,
        demanda_id=demanda_id,
        campo="responsavel",
        de=responsavel_antes,
        para=efeito.atribuir_a,
        texto=texto_movimento_responsavel(
            autor_nome=AUTOR_DA_ENTREGA,
            # O id quando o nome nao veio, como o router faz: uma linha
            # "A entrega atribuiu a " nao diz a quem.
            para_nome=str(autor.get("nome_completo") or efeito.atribuir_a),
        ),
    )
    _avisar_a_devolucao(supabase, atribuida.data[0], destinatario_id=efeito.atribuir_a)


def sincronizar_demanda(supabase, demanda: dict[str, Any]) -> bool:
    """Rele a issue vinculada e atualiza o cache da Demanda. `True` se mudou.

    NAO trata excecao: `GithubIndisponivelError` e `IssueNaoEncontradaError` sobem
    para quem chamou, porque o desfeito e diferente nos dois gatilhos. O webhook
    engole e responde 2xx (o GitHub nao reentrega, e insistir nao traria o evento
    de volta); o lote conta a falha e segue para a proxima Demanda.

    Demanda Concluida ou Cancelada nao e tocada, pelos DOIS gatilhos. O lote ja
    nem a le (o filtro de estado poupa a cota do GitHub), mas a guarda mora aqui
    e nao la, porque o webhook chega pelo numero da issue e nao tem esse filtro:
    sem ela, fechar a issue depois que alguem concluiu a Demanda a mao escreveria
    no fio de um card fechado, e os dois caminhos que a issue chama de "a mesma
    rotina" se comportariam diferente.
    """
    numero = demanda.get("github_issue_numero")
    if not numero:
        return False
    if str(demanda.get("estado") or "") in ESTADOS_FECHADOS:
        return False
    numero = int(numero)

    dados = github_client.ler_issue(numero)
    foto = github_client.montar_foto(dados, github_client.ler_sub_issues(numero))
    if not foto_mudou(demanda.get("github_foto"), foto):
        return False

    demanda_id = str(demanda["id"])
    etapa_antes = demanda.get("etapa") or ETAPA_REGISTRADA
    mudanca = mudanca_da_foto(foto)
    muda_a_etapa = mudanca["etapa"] != etapa_antes

    consulta = supabase.table(TABELA_DEMANDAS).update(mudanca).eq("id", demanda_id)
    if muda_a_etapa:
        # Trava otimista, e nao enfeite: o job roda numa THREAD do
        # `BackgroundScheduler` e o webhook roda no event loop, entao entre o
        # `select` de um e o `insert` do outro ha uma janela sem trava. Os dois
        # leriam `etapa_antes` igual, os dois achariam que a Etapa mudou, e o
        # diretor leria a MESMA linha duas vezes no fio.
        #
        # O `.eq("etapa", ...)` transforma o UPDATE num compare-and-swap: o
        # Postgres serializa a linha, e so um dos dois casa. Quem perde sai sem
        # escrever a segunda linha. O cache dele se perde junto, e tudo bem: quem
        # ganhou acabou de gravar uma foto lida do mesmo GitHub, e se ela for a
        # mais velha das duas a reconciliacao da hora seguinte reescreve.
        #
        # A coluna e NOT NULL com default na migration 103, entao o `.eq` nao cai
        # na armadilha do PostgREST de descartar linha com valor nulo.
        consulta = consulta.eq("etapa", etapa_antes)
    result = consulta.execute()

    if not muda_a_etapa:
        return True
    if not result.data:
        logger.info(
            "[tecnologia] A Etapa da Demanda %s já tinha sido movida por outro caminho; linha não repetida.",
            demanda_id,
        )
        return False

    _gravar_linha(
        supabase,
        demanda_id=demanda_id,
        campo="etapa",
        de=etapa_antes,
        para=mudanca["etapa"],
        texto=texto_movimento_etapa(
            para=mudanca["etapa"],
            entregues=mudanca["partes_entregues"],
            total=mudanca["partes_total"],
        ),
    )
    # Depois da linha da Etapa, e so aqui dentro: este ponto do codigo e o
    # unico em que a Etapa acabou de MUDAR e o compare-and-swap acima disse que
    # foi esta thread quem a mudou. Uma edicao do corpo da issue mexe na foto
    # sem mexer na Etapa e nao chega ate aqui, entao a Demanda nao e devolvida
    # de novo a cada webhook depois da entrega.
    try:
        _devolver_a_quem_pediu(supabase, demanda, etapa_nova=mudanca["etapa"])
    except Exception:
        # A excecao continua subindo (o webhook responde `falhou: true`, o lote
        # conta a falha), mas ela sai daqui com NOME. O cache e a linha da Etapa
        # ja estao gravados, entao a passagem seguinte vera a foto igual e sairá
        # sem refazer nada: esta devolucao esta PERDIDA, e alguem precisa
        # termina-la a mao. Um WARNING generico prometendo que "a reconciliacao
        # recupera" mandaria quem le o log esperar por uma segunda passagem que
        # nao vai acontecer.
        logger.error(
            "[tecnologia] A devolução da entrega NÃO foi concluída na Demanda %s e a reconciliação "
            "não vai refazê-la (a foto já foi gravada): termine à mão o movimento para Aguardando, "
            "o responsável e o aviso.",
            demanda_id,
            exc_info=True,
        )
        raise
    return True


def reconciliar_vinculos(supabase) -> dict[str, int]:
    """O lote de hora em hora: toda Demanda vinculada que ainda esta aberta.

    Existe porque o webhook e o unico caminho rapido, e ele e perdivel: o GitHub
    exige 2xx em 10 segundos e nao reentrega a entrega que falhou. Um deploy no
    momento errado, uma queda de rede ou um erro nosso somem com o evento, e sem
    esta passagem o card ficaria mentindo ate alguem reparar.

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

    mudadas = 0
    falhas = 0
    for demanda in demandas:
        try:
            if sincronizar_demanda(supabase, demanda):
                mudadas += 1
        except github_client.IssueNaoEncontradaError:
            # Condicao PERMANENTE: a issue foi apagada ou transferida. Uma linha,
            # sem stack. Tratada como as outras falhas seria um traceback inteiro
            # por HORA, para sempre, sobre algo que nao se auto-resolve: quem for
            # consertar desfaz o Vinculo na tela.
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
