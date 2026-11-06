"""Router /admin/tecnologia, a aba Tecnologia (PRD #634, ADR 0050).

Desde a ADR 0077 a aba e uma tela so: o chat do Assistente de Tecnologia, em
que o diretor relata um bug ou pede uma melhoria e o card nasce no GitHub. O
Quadro, o Painel, os Produtos, o formulario a mao, a Conversa da Demanda, as
mencoes, o e-mail da aba, o Vinculo por numero, o Assistente de entrada e a
tela antiga do Planejamento sairam do codigo na issue #1386.

Todos os endpoints exigem `require_super_admin`. Esse e o gate de verdade: a
sidebar apenas esconde o item, e esconder nao e proteger (ADR 0050, decisao 2).

O chat da aba (issues #1381, #1383 e #1384):

- GET   /admin/tecnologia/chat                  a lista lateral: as Demandas
                                                de quem esta logado, da mais
                                                recente para a mais antiga.
- POST  /admin/tecnologia/chat                  o primeiro turno: a Demanda
                                                nasce aqui.
- GET   /admin/tecnologia/chat/{id}             a conversa guardada.
- POST  /admin/tecnologia/chat/{id}             um turno: a fala do diretor
                                                entra, a da IA volta.
- POST  /admin/tecnologia/chat/{id}/nao-bateu   o que nao bateu no resumo.
- POST  /admin/tecnologia/chat/{id}/resumo      o "Fechar e resumir" da
                                                melhoria.
- POST  /admin/tecnologia/chat/{id}/criar-card  cria a issue (o bug pronto para
                                                a onda, ou o PRD do diretor) e
                                                vincula.

O print do chat (ADR 0056, decisao 4; ADR 0077, decisao 8):

- POST  /admin/tecnologia/assistente/descrever-imagem  le o print e devolve a
                                                       descricao com o
                                                       identificador efemero
                                                       que o faz Anexo.

Fora daqui, e de pe: o webhook do GitHub que deriva a Etapa
(`routers/webhooks.py`), a rota de automacao dos anexos
(`routers/tecnologia_automacao.py`) e o cron de hora em hora
(`cron/scheduler.py`).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from supabase import Client

from app.config import settings
from app.dependencies import get_supabase_client, require_super_admin
from app.limiter import limiter
from app.models.tecnologia_schemas import (
    AssistenteImagemResponse,
    ChatNaoBateuPayload,
    ChatPrimeiroTurnoPayload,
    ChatResponse,
    ChatTurnoPayload,
    DemandaResponse,
)
from app.services import (
    ai_processor,
    assistente_tecnologia,
    chat_tecnologia,
    custo_da_conversa,
    github_client,
    planejamento_demanda,
    tecnologia_anexos,
)
from app.services.conhecimento import carregar_kit
from app.services.tecnologia import (
    SEM_PRODUTO,
    TABELA_DEMANDAS,
    TABELA_PRODUTOS,
    instante_do_banco,
    versao_da_entrega,
)
from app.services.tecnologia_sincronizacao import mudanca_da_foto
from app.services.tecnologia_vinculo import (
    LABELS_DO_BUG,
    MOTIVO_CRIACAO_EM_ANDAMENTO,
    MOTIVO_GITHUB_INDISPONIVEL,
    MOTIVO_INTEGRACAO_DESLIGADA,
    corpo_da_issue_do_bug,
    corpo_do_prd_do_diretor,
    labels_da_issue_nova,
    link_da_demanda,
    login_para_publicar,
    titulo_da_issue,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tecnologia", tags=["admin", "tecnologia"])


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _recusar(motivo: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=motivo)


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _buscar_demanda(supabase: Client, demanda_id: str) -> dict:
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")
    return result.data[0]


def _para_a_lista(demandas: list[dict]) -> list[dict]:
    """A Demanda como a lista lateral do chat a le (issue #1384).

    E o funil por onde a Demanda sai desta API, e por isso o corte e aqui:
    numero e endereco da issue nao saem (ADR 0054, decisao 9), e o diretor le a
    Etapa e O que muda sem nenhum dos dois.
    """
    return [
        {
            **d,
            "tem_vinculo": bool(d.get("github_issue_numero")),
            "partes": _partes_visiveis(d),
            "versao": versao_da_entrega(d),
        }
        for d in demandas
    ]


def _partes_visiveis(demanda: dict) -> list[dict]:
    """As partes da entrega como o diretor as le (issue #676): o texto e a
    situacao, sem o numero da fatia, que e interno."""
    partes = demanda.get("partes")
    if not isinstance(partes, list):
        return []
    return [
        {"o_que_muda": parte.get("o_que_muda"), "situacao": parte.get("situacao")}
        for parte in partes
        if isinstance(parte, dict)
    ]


# ─── O card no GitHub (issue #674, ADR 0054; ADR 0077, decisao 7) ─────────


# Quantas vezes por minuto uma mesma origem pode mexer no Vinculo.
#
# O recurso escasso aqui e a cota da API do GitHub, que e UMA para o app inteiro
# e atende o token pessoal do Pedro: um laco bobo no "Criar o card" derrubaria a
# integracao para todo mundo, inclusive para a reconciliacao de hora em hora.
#
# `shared_limit`, e nao `limit`: o `Limiter` da casa nasce com
# `key_style="url"`, e com `limit` cada Demanda ganharia o proprio balde, o que
# faria o teto virar enfeite justo na porta em que ele foi pedido.
LIMITE_DO_VINCULO = "30/minute"
ESCOPO_DO_VINCULO = "tecnologia-vinculo-github"


def _exigir_integracao() -> None:
    """503 sem token ou sem repositorio configurado.

    503, e nao 500: nao ha defeito nenhum, falta configuracao no ambiente, e a
    frase diz isso. Nao ha o que tentar de novo sem alguem mexer no Coolify.
    """
    if not github_client.integracao_configurada():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MOTIVO_INTEGRACAO_DESLIGADA,
        )


def _issue_indisponivel() -> NoReturn:
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MOTIVO_GITHUB_INDISPONIVEL)


# Por quanto tempo o carimbo de "estou criando a issue agora" segura a porta.
#
# Maior que o timeout do cliente do GitHub (10 s) com folga para a escrita que
# vem depois, e curto o bastante para um processo morto no meio da criacao nao
# trancar a Demanda para sempre. O caminho normal nem chega perto disso: a
# falha DEVOLVE a vez na hora (`_devolver_a_vez`), e este teto e so a rede de
# baixo, para o que o codigo nao consegue desfazer.
JANELA_DA_CRIACAO = timedelta(seconds=60)


def _criacao_em_andamento(demanda: dict) -> bool:
    """Se outro pedido esta criando a issue desta Demanda AGORA (issue #677).

    O carimbo lido e o `github_sincronizado_em`, que numa Demanda sem Vinculo e
    sempre NULO: a unica coisa que o preenche antes de existir issue e o claim
    logo abaixo. Carimbo velho e claim que morreu com o processo, e a porta
    reabre.
    """
    carimbo = instante_do_banco(demanda.get("github_sincronizado_em"))
    if carimbo is None:
        return False
    return datetime.now(UTC) - carimbo < JANELA_DA_CRIACAO


def _tomar_a_vez_de_criar(supabase: Client, *, demanda_id: str, carimbo_lido: str | None) -> bool:
    """Carimba a Demanda como "indo para o desenvolvimento", ou devolve False.

    E o que fecha a janela do duplo clique DO LADO DO SERVIDOR, e nao so no
    botao: o `github_issue_numero` da Demanda so existe DEPOIS de a issue
    nascer, entao dois pedidos concorrentes leem os dois "sem Vinculo" e
    criariam duas issues publicas, a segunda orfa (o marcador dela aponta para
    a mesma Demanda, que ja aponta para a primeira).

    O UPDATE e condicionado ao valor que ESTE pedido leu (compare-and-swap): o
    Postgres serializa os dois, o segundo reavalia a condicao com a linha ja
    escrita e volta sem nenhuma. Nao ha transacao no PostgREST, e nao e preciso:
    um UPDATE condicionado e atomico por si.
    """
    consulta = supabase.table(TABELA_DEMANDAS).update({"github_sincronizado_em": _agora()}).eq("id", demanda_id)
    # Coluna nulavel: `.eq(coluna, None)` nao casa NULL no PostgREST, `.is_` casa.
    consulta = (
        consulta.eq("github_sincronizado_em", carimbo_lido)
        if carimbo_lido
        else consulta.is_("github_sincronizado_em", "null")
    )
    return bool(consulta.execute().data)


def _devolver_a_vez(supabase: Client, *, demanda_id: str, carimbo_lido: str | None) -> None:
    """Desfaz o claim quando a criacao nao aconteceu.

    Sem isto, a frase do 502 ("tente de novo em alguns instantes") seria
    mentira: a Demanda ficaria trancada pela `JANELA_DA_CRIACAO` inteira depois
    de uma falha que durou um segundo.
    """
    supabase.table(TABELA_DEMANDAS).update({"github_sincronizado_em": carimbo_lido}).eq("id", demanda_id).execute()


def _criar_issue_e_vincular(
    supabase: Client,
    *,
    demanda: dict,
    ator: dict,
    corpo,
    assignees: list[str],
    labels: list[str],
) -> dict:
    """O servico do "Criar o card" do chat (issues #1381 e #1383), o bug e a
    melhoria.

    Recebe a Demanda ja lida e as guardas da porta ja passadas, e faz o que e
    igual nos dois: a vez de criar, o titulo pela peneira, a issue no GitHub, o
    Vinculo e a Etapa derivada da issue nova. O que muda de um para o outro
    entra por parametro: o `corpo(titulo)`, os `assignees` e as `labels`.
    Devolve a linha da Demanda ja vinculada.
    """
    demanda_id = str(demanda["id"])
    if _criacao_em_andamento(demanda):
        _recusar(MOTIVO_CRIACAO_EM_ANDAMENTO)

    carimbo_lido = demanda.get("github_sincronizado_em")
    if not _tomar_a_vez_de_criar(supabase, demanda_id=demanda_id, carimbo_lido=carimbo_lido):
        # Outro pedido carimbou entre a leitura e agora. Ele esta criando a
        # issue; este para aqui em vez de criar a segunda.
        _recusar(MOTIVO_CRIACAO_EM_ANDAMENTO)

    # O titulo tambem vai para o repositorio publico, e nao so o corpo: passa
    # pela mesma peneira (o corpo ja passava, porque o titulo e o "O que muda"
    # da Demanda sem descricao). Inclusive a de dado pessoal (issue #772).
    titulo = titulo_da_issue(demanda.get("titulo"))

    try:
        dados = github_client.criar_issue(
            titulo=titulo,
            corpo=corpo(titulo),
            labels=labels,
            assignees=assignees,
        )
        numero = dados.get("number")
        if not isinstance(numero, int):
            # A issue pode ter nascido; o Vinculo, nao. Sem o numero nao ha par,
            # e gravar `None` no lugar dele e o meio Vinculo proibido.
            logger.error("[tecnologia] a criacao da issue da Demanda %s voltou sem numero", demanda_id)
            raise github_client.GithubIndisponivelError("A criacao da issue voltou sem numero")
    except github_client.GithubNaoConfiguradoError:
        # A configuracao pode ter sumido entre a guarda la em cima e a chamada.
        _devolver_a_vez(supabase, demanda_id=demanda_id, carimbo_lido=carimbo_lido)
        _exigir_integracao()
        raise
    except github_client.GithubIndisponivelError:
        _devolver_a_vez(supabase, demanda_id=demanda_id, carimbo_lido=carimbo_lido)
        logger.warning("[tecnologia] GitHub indisponivel ao criar o card da Demanda %s", demanda_id)
        _issue_indisponivel()

    # A issue acabou de nascer: ela nao tem sub-issue nenhuma, e a foto sai do
    # proprio JSON da criacao, sem uma segunda leitura.
    foto = github_client.montar_foto(dados, [])
    # O SHAPE do cache vem de um lugar so (`mudanca_da_foto`), o mesmo do
    # webhook e da reconciliacao (issue #678): so o par do Vinculo, que e desta
    # porta, entra por fora. A Etapa sai derivada dali, e
    # nao cravada aqui: a issue nova vem com a label da triagem, e a tabela de
    # Etapas le "Em análise" dela.
    mudanca = {
        **mudanca_da_foto(foto),
        "github_issue_numero": numero,
        "vinculado_por": ator["id"],
    }

    result = supabase.table(TABELA_DEMANDAS).update(mudanca).eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")

    return result.data[0]


# O mesmo teto dos outros chats do app. Ele e por ENDERECO, e nao por pessoa,
# porque e assim que o `limiter` do app conta em todo lugar; o que ele protege
# aqui e a cota do provedor de IA contra uma tela esquecida aberta.
LIMITE_DO_ASSISTENTE = "10/minute"


def _conflito(motivo: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=motivo)


# ─── O chat da aba (issue #1381, PRD #1380, ADR 0077) ────────────────────────


def _produtos_ativos(supabase: Client) -> list[dict]:
    """Os Produtos que o agente pode escolher, na ordem da lista."""
    result = supabase.table(TABELA_PRODUTOS).select("*").order("ordem").execute()
    return [
        {"id": p["id"], "nome": p.get("nome") or "", "dono_id": p.get("dono_id")}
        for p in (result.data or [])
        if p.get("ativo")
    ]


def _chat_para_a_tela(
    supabase: Client,
    demanda_id: str,
    linha: dict | None,
    *,
    aviso_dos_anexos: str | None = None,
) -> dict:
    """A conversa para a tela. `planejamento` diz que a conversa esta no
    planejamento da melhoria (issue #1383): o resumo dela tem outra forma, e
    sai em `resumo_da_melhoria`."""
    linha = linha or {}
    mensagens = linha.get("mensagens") or []
    planejamento = chat_tecnologia.em_planejamento(mensagens)
    return {
        "demanda_id": str(demanda_id),
        "estado": linha.get("estado"),
        "mensagens": chat_tecnologia.para_a_tela(mensagens),
        "resumo": None if planejamento else linha.get("resumo"),
        "resumo_da_melhoria": linha.get("resumo") if planejamento else None,
        "anexos": tecnologia_anexos.quantos_guardados(supabase, demanda_id),
        "planejamento": planejamento,
        "aviso_dos_anexos": aviso_dos_anexos,
        "custo": custo_da_conversa.da_demanda(supabase, demanda_id),
    }


def _nascer_a_demanda(supabase: Client, *, ator: dict, titulo: str, tipo: str, produto: dict) -> dict:
    """A Demanda que o primeiro turno do chat faz nascer (ADR 0077, decisao 2)."""
    criada = (
        supabase.table(TABELA_DEMANDAS)
        .insert(
            {
                "titulo": titulo,
                "descricao": None,
                "tipo": tipo,
                "produto_id": produto["id"],
                "estado": "nova",
                "responsavel_id": produto.get("dono_id"),
                "autor_id": ator["id"],
                "prioridade": "normal",
            }
        )
        .execute()
    )
    if not criada.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao criar a Demanda")
    return criada.data[0]


def _estado_do_planejamento(mensagem: dict) -> str:
    if mensagem.get("tipo") == "encerrou":
        return planejamento_demanda.ESTADO_ENCERRADO
    return planejamento_demanda.ESTADO_EM_ANDAMENTO


async def _comecar_a_melhoria(
    supabase: Client, *, ator: dict, falas: list[dict], produtos: list[dict], prints: list[str]
) -> dict:
    """O botao "Melhoria" abre o planejamento na hora (issue #1383): a primeira
    fala da IA ja e a primeira pergunta, com as duas opcoes e a recomendada.

    A Demanda nasce depois do turno, como no bug: um turno que falhou nao deixa
    Demanda vazia. Ela nasce Novo, no primeiro Produto e com o titulo
    provisorio; o titulo de verdade vem do resumo.
    """
    resultado = await ai_processor.chamar_ia_fora_do_loop(
        chat_tecnologia.turno_da_melhoria, mensagens=falas, kit=carregar_kit()
    )
    if resultado.erro:
        if resultado.chamada is not None:
            planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)

    demanda = _nascer_a_demanda(
        supabase,
        ator=ator,
        titulo=chat_tecnologia.TITULO_SEM_RESPOSTA,
        tipo=chat_tecnologia.TIPO_DA_CLASSIFICACAO["melhoria"],
        produto=produtos[0],
    )
    demanda_id = str(demanda["id"])
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, {**resultado.chamada, "demanda_id": demanda_id})
    descricao = chat_tecnologia.descricao_da_melhoria(falas)
    if descricao:
        supabase.table(TABELA_DEMANDAS).update({"descricao": descricao}).eq("id", demanda_id).execute()

    aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=prints, ator=ator)
    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=None,
        novo={
            "estado": _estado_do_planejamento(resultado.mensagem),
            "mensagens": [*falas, resultado.mensagem],
            "decisoes": [resultado.decisao] if resultado.decisao else [],
            "atualizado_em": _agora(),
        },
    )
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


def _prints_do_turno(supabase: Client, *, demanda: dict, print_ids: list[str], ator: dict) -> str | None:
    """Os prints que a fala do diretor trouxe viram Anexo da Demanda na hora
    (ADR 0077, decisao 8), e so quando a fala entrou na conversa: o turno que
    falhou devolve o 502 antes de chegar aqui, e o print espera o reenvio."""
    if not print_ids:
        return None
    return tecnologia_anexos.anexar_prints(supabase, demanda=demanda, print_ids=print_ids, quem_id=ator["id"])


def _passar_ao_planejamento(
    supabase: Client, demanda_id: str, *, atual: dict | None, mensagens: list[dict]
) -> dict | None:
    """A melhoria confirmada segue, no proprio chat, pelo planejamento (issue
    #1383).

    O que o diretor disse vira a descricao da Demanda, que e de onde o
    planejamento parte, e a ultima fala da IA leva a marca `planejar`: dali em
    diante a conversa e do planejamento, e a tela pede o turno seguinte, que
    traz a primeira pergunta. Devolve a linha gravada, ou `None` se outra aba
    gravou no meio.
    """
    *anteriores, ultima = mensagens
    mensagens = [*anteriores, {**ultima, "planejar": True}]
    descricao = chat_tecnologia.descricao_da_melhoria(mensagens)
    supabase.table(TABELA_DEMANDAS).update({"descricao": descricao}).eq("id", demanda_id).execute()
    return planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={"estado": planejamento_demanda.ESTADO_EM_ANDAMENTO, "mensagens": mensagens, "atualizado_em": _agora()},
    )


def _estado_depois_do_turno(resultado: chat_tecnologia.ResultadoDoTurno) -> str:
    return planejamento_demanda.ESTADO_RESUMIDO if resultado.resumo else planejamento_demanda.ESTADO_EM_ANDAMENTO


@router.get("/chat", response_model=list[DemandaResponse])
async def listar_as_conversas(
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A lista ao lado do chat (issue #1384): as Demandas que o Super admin
    logado pediu, com o titulo e a Etapa, a mais recente primeiro.

    Sai pelo `_para_a_lista`, o funil da Demanda desta API: e la que numero e
    endereco da issue ficam de fora, e o diretor le aqui a Etapa e O que muda
    sem nenhum dos dois.
    """
    result = (
        supabase.table(TABELA_DEMANDAS).select("*").eq("autor_id", ator["id"]).order("criado_em", desc=True).execute()
    )
    return _para_a_lista(list(result.data or []))


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def comecar_o_chat(
    request: Request,
    payload: ChatPrimeiroTurnoPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O primeiro turno: a Demanda nasce aqui (ADR 0077, decisao 2).

    O botao da abertura ou o texto livre entram na conversa depois da pergunta
    "bug ou melhoria?", e o agente responde. So entao a Demanda e gravada, com
    o Tipo da classificacao (Defeito para bug, Novo para melhoria), o Produto
    que o agente escolheu pelo Kit e o titulo dele: um turno que falhou nao
    deixa Demanda vazia para tras, e o texto continua na caixa da tela.
    """
    texto = (payload.texto or "").strip()
    if not payload.escolha and not texto:
        _recusar(chat_tecnologia.MOTIVO_SEM_TEXTO)

    produtos = _produtos_ativos(supabase)
    falas = [chat_tecnologia.mensagem_de_abertura()]
    if payload.escolha:
        falas.append(chat_tecnologia.fala_do_diretor(chat_tecnologia.ESCOLHAS[payload.escolha]))
    if texto:
        falas.append(chat_tecnologia.fala_do_diretor(texto))

    if payload.escolha == "melhoria":
        return await _comecar_a_melhoria(supabase, ator=ator, falas=falas, produtos=produtos, prints=payload.prints)

    # Fora do loop (issue #773, o porque em `ai_processor._EXECUTOR_DA_IA`).
    resultado = await ai_processor.chamar_ia_fora_do_loop(
        chat_tecnologia.turno, mensagens=falas, kit=carregar_kit(), produtos=produtos, escolha=payload.escolha
    )
    if resultado.erro:
        if resultado.chamada is not None:
            planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)

    produto = next((p for p in produtos if p["id"] == resultado.produto_id), produtos[0])
    demanda = _nascer_a_demanda(
        supabase,
        ator=ator,
        titulo=resultado.titulo,
        tipo=chat_tecnologia.TIPO_DA_CLASSIFICACAO[resultado.classificacao],
        produto=produto,
    )
    demanda_id = str(demanda["id"])
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, {**resultado.chamada, "demanda_id": demanda_id})

    aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=payload.prints, ator=ator)
    if resultado.caminho == chat_tecnologia.CAMINHO_DO_PLANEJAMENTO:
        linha = _passar_ao_planejamento(supabase, demanda_id, atual=None, mensagens=[*falas, resultado.mensagem])
        return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)

    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=None,
        novo={
            "estado": _estado_depois_do_turno(resultado),
            "mensagens": [*falas, resultado.mensagem],
            "resumo": resultado.resumo,
            "atualizado_em": _agora(),
        },
    )
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


MOTIVO_CHAT_NAO_ENCONTRADO = "Esta conversa não foi encontrada. Comece uma nova na aba Tecnologia."
MOTIVO_CHAT_NO_RESUMO = "O resumo já está pronto. Clique em Criar o card, ou em Não bateu para corrigir."
MOTIVO_CHAT_TERMINOU = "Esta conversa já virou card. Comece uma nova na aba Tecnologia."
MOTIVO_CHAT_MUDOU = "A conversa mudou em outra aba. Recarregue a página e tente de novo."
ESTADOS_DEPOIS_DO_FIM = (planejamento_demanda.ESTADO_ENCERRADO, planejamento_demanda.ESTADO_RESUMIDO)
MOTIVO_RESUMO_SO_DA_MELHORIA = "Fechar e resumir vale para uma melhoria, depois que as perguntas começaram."


def _chat_guardado(supabase: Client, demanda_id: str) -> tuple[dict, dict]:
    """A Demanda e a conversa do chat dela, ou 404.

    A conversa do Planejamento mora na mesma tabela (ADR 0077, decisao 2), e
    nao e um chat: abri-la por aqui misturaria as duas conversas.
    """
    demanda = _buscar_demanda(supabase, demanda_id)
    linha = planejamento_demanda.ler(supabase, demanda_id)
    if not chat_tecnologia.e_do_chat(linha):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MOTIVO_CHAT_NAO_ENCONTRADO)
    return demanda, linha


def _acompanhar_o_turno(supabase: Client, demanda: dict, resultado: chat_tecnologia.ResultadoDoTurno) -> None:
    """A Demanda acompanha a conversa: o Tipo da classificacao, o Produto que o
    agente escolheu e o titulo. So o que mudou e escrito."""
    novo = {
        "tipo": chat_tecnologia.TIPO_DA_CLASSIFICACAO[resultado.classificacao],
        "produto_id": resultado.produto_id or demanda.get("produto_id"),
        "titulo": resultado.titulo or demanda.get("titulo"),
    }
    mudancas = {campo: valor for campo, valor in novo.items() if valor != demanda.get(campo)}
    if mudancas:
        supabase.table(TABELA_DEMANDAS).update(mudancas).eq("id", demanda["id"]).execute()


async def _turno_da_melhoria(
    supabase: Client, *, demanda: dict, atual: dict, payload: ChatTurnoPayload, ator: dict, depois_do_fim: bool
) -> dict:
    """Um turno do planejamento da melhoria dentro do chat (issue #1383).

    As regras sao as do Planejamento da Demanda: com pergunta em aberto, a
    resposta e a letra da opcao OU o texto livre; sem pergunta (a passagem do
    chat ao planejamento, ou o "Nao bateu"), o corpo vazio pede a pergunta
    seguinte. Depois do encerramento ou do resumo (`depois_do_fim`), so o
    texto livre vale, e ele volta o planejamento a em andamento com a pergunta
    seguinte (ADR 0079, decisao 3). A conversa so e gravada depois que o turno
    deu certo.
    """
    demanda_id = str(demanda["id"])
    mensagens = list(atual.get("mensagens") or [])
    _, planejamento = chat_tecnologia.partes_da_melhoria(mensagens)
    if payload.continuar:
        resposta, motivo = planejamento_demanda.fala_de_continuar(atual.get("resumo"))
        if motivo:
            _conflito(motivo)
    else:
        resposta, motivo = planejamento_demanda.resposta_do_diretor(
            planejamento, opcao=payload.opcao, texto=payload.texto, depois_do_fim=depois_do_fim
        )
        if motivo:
            _recusar(motivo)
    if resposta is not None:
        mensagens.append(resposta)

    resultado = await ai_processor.chamar_ia_fora_do_loop(
        chat_tecnologia.turno_da_melhoria,
        mensagens=mensagens,
        kit=carregar_kit(),
        demanda_id=demanda_id,
        titulo=demanda.get("titulo"),
    )
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
    if resultado.erro:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)

    decisoes = list(atual.get("decisoes") or [])
    if resultado.decisao:
        decisoes.append(resultado.decisao)
    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={
            "estado": _estado_do_planejamento(resultado.mensagem),
            "mensagens": [*mensagens, resultado.mensagem],
            "decisoes": decisoes,
            "atualizado_em": _agora(),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=payload.prints, ator=ator)
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


@router.get("/chat/{demanda_id}", response_model=ChatResponse)
async def ler_o_chat(
    demanda_id: str,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A conversa guardada, para retomar de onde parou."""
    _demanda, linha = _chat_guardado(supabase, demanda_id)
    return _chat_para_a_tela(supabase, demanda_id, linha)


@router.post("/chat/{demanda_id}", response_model=ChatResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def responder_no_chat(
    request: Request,
    demanda_id: str,
    payload: ChatTurnoPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Um turno: a fala do diretor entra, a da IA volta.

    A conversa so e gravada depois que o turno deu certo: falha do provedor ou
    resposta fora do esquema devolve 502 com a frase para a tela, e o que
    estava guardado fica como estava. O custo da chamada e gravado nos dois
    casos.
    """
    demanda, atual = _chat_guardado(supabase, demanda_id)
    estado = atual.get("estado")
    mensagens = list(atual.get("mensagens") or [])
    na_melhoria = chat_tecnologia.em_planejamento(mensagens)
    # A melhoria segue aberta depois do encerramento e do resumo, ate o Criar
    # o card (ADR 0079, decisao 3); o Roteiro do bug, nao.
    depois_do_fim = na_melhoria and estado in ESTADOS_DEPOIS_DO_FIM
    if estado == planejamento_demanda.ESTADO_RESUMIDO and not depois_do_fim:
        _conflito(MOTIVO_CHAT_NO_RESUMO)
    if estado != planejamento_demanda.ESTADO_EM_ANDAMENTO and not depois_do_fim:
        _conflito(MOTIVO_CHAT_TERMINOU)
    # O "Continuar respondendo" vale so no resumo da melhoria (issue #1440).
    if payload.continuar and not (depois_do_fim and estado == planejamento_demanda.ESTADO_RESUMIDO):
        _conflito(planejamento_demanda.MOTIVO_NADA_EM_ABERTO)

    if na_melhoria:
        return await _turno_da_melhoria(
            supabase, demanda=demanda, atual=atual, payload=payload, ator=ator, depois_do_fim=depois_do_fim
        )
    texto = (payload.texto or "").strip()
    if texto:
        mensagens.append(chat_tecnologia.fala_do_diretor(texto))
    elif mensagens[-1].get("tipo") == "ia":
        # Sem texto e sem fala do diretor esperando: nao ha o que a IA responder.
        _recusar(chat_tecnologia.MOTIVO_SEM_TEXTO)

    resultado = await ai_processor.chamar_ia_fora_do_loop(
        chat_tecnologia.turno,
        mensagens=mensagens,
        kit=carregar_kit(),
        produtos=_produtos_ativos(supabase),
        titulo_atual=demanda.get("titulo"),
        demanda_id=demanda_id,
    )
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
    if resultado.erro:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)

    if resultado.caminho == chat_tecnologia.CAMINHO_DO_PLANEJAMENTO:
        linha = _passar_ao_planejamento(supabase, demanda_id, atual=atual, mensagens=[*mensagens, resultado.mensagem])
        if linha is None:
            _conflito(MOTIVO_CHAT_MUDOU)
        _acompanhar_o_turno(supabase, demanda, resultado)
        aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=payload.prints, ator=ator)
        return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)

    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={
            "estado": _estado_depois_do_turno(resultado),
            "mensagens": [*mensagens, resultado.mensagem],
            "resumo": resultado.resumo or atual.get("resumo"),
            "atualizado_em": _agora(),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    _acompanhar_o_turno(supabase, demanda, resultado)
    aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=payload.prints, ator=ator)
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


MOTIVO_CHAT_SEM_RESUMO = "Ainda não há resumo para virar card. Responda às perguntas até o resumo aparecer."


@router.post("/chat/{demanda_id}/nao-bateu", response_model=ChatResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def resumo_do_chat_nao_bateu(
    request: Request,
    demanda_id: str,
    payload: ChatNaoBateuPayload,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Nao bateu" do resumo: o que nao bateu entra na conversa como fala do
    diretor e ela volta a em andamento. A IA nao e chamada aqui: a tela pede o
    turno seguinte sem texto, e a IA retoma da fala, refazendo o resumo. O
    resumo velho fica ate o novo o substituir, como no planejamento."""
    _demanda, atual = _chat_guardado(supabase, demanda_id)
    texto = (payload.texto or "").strip()
    if not texto:
        _recusar(planejamento_demanda.MOTIVO_NAO_SEM_TEXTO)
    if atual.get("estado") != planejamento_demanda.ESTADO_RESUMIDO:
        _conflito(MOTIVO_CHAT_SEM_RESUMO)

    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={
            "estado": planejamento_demanda.ESTADO_EM_ANDAMENTO,
            "mensagens": [*(atual.get("mensagens") or []), {"tipo": "nao_bateu", "texto": texto}],
            "atualizado_em": _agora(),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    return _chat_para_a_tela(supabase, demanda_id, linha)


@router.post("/chat/{demanda_id}/resumo", response_model=ChatResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def fechar_e_resumir_a_melhoria(
    request: Request,
    demanda_id: str,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Fechar e resumir" da melhoria (issue #1383): vale a qualquer altura do
    planejamento, da primeira pergunta ao "encerrou". O resumo traz as decisoes,
    o que ficou em aberto (o que nao foi perguntado nunca vira decisao) e o
    glossario. O titulo provisorio da Demanda da lugar ao do resumo. Falha da
    IA devolve 502 sem mexer em nada."""
    demanda, atual = _chat_guardado(supabase, demanda_id)
    mensagens = list(atual.get("mensagens") or [])
    if not chat_tecnologia.em_planejamento(mensagens):
        _conflito(MOTIVO_RESUMO_SO_DA_MELHORIA)
    estado = atual.get("estado")
    if estado == planejamento_demanda.ESTADO_RESUMIDO:
        _conflito(MOTIVO_CHAT_NO_RESUMO)
    if estado not in (planejamento_demanda.ESTADO_EM_ANDAMENTO, planejamento_demanda.ESTADO_ENCERRADO):
        _conflito(MOTIVO_CHAT_TERMINOU)

    resultado = await ai_processor.chamar_ia_fora_do_loop(
        chat_tecnologia.resumo_da_melhoria,
        mensagens=mensagens,
        kit=carregar_kit(),
        demanda_id=demanda_id,
        titulo=demanda.get("titulo"),
    )
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
    if resultado.erro:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)
    if resultado.parecida:
        # O pedido aberto parecido (issue #1385): o aviso vem com o resumo,
        # antes do Criar o card.
        mensagens.append(chat_tecnologia.fala_do_aviso(resultado.parecida))

    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={
            "estado": planejamento_demanda.ESTADO_RESUMIDO,
            "mensagens": mensagens,
            "resumo": resultado.resumo,
            "atualizado_em": _agora(),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    if resultado.titulo and resultado.titulo != demanda.get("titulo"):
        supabase.table(TABELA_DEMANDAS).update({"titulo": resultado.titulo}).eq("id", demanda_id).execute()
    return _chat_para_a_tela(supabase, demanda_id, linha)


@router.post("/chat/{demanda_id}/criar-card", response_model=ChatResponse)
@limiter.shared_limit(LIMITE_DO_VINCULO, ESCOPO_DO_VINCULO)
async def criar_o_card(
    request: Request,
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Criar o card" do resumo (ADR 0077, decisoes 6 e 7).

    Pelo servico `_criar_issue_e_vincular`: a vez de criar, a peneira no
    titulo, o Vinculo e a Etapa. O que e do bug entra por parametro: o corpo
    com os rotulos do roteiro e os criterios de aceite, as labels que fazem a
    onda pegar sozinha (`ready-for-agent`, sem `needs-triage`) e nenhum
    assignee, porque assignee e claim. A melhoria leva o PRD do diretor.

    Sem gate de `github_login`: quem cria o card e o diretor que relatou. A
    ordem das guardas e: o que eu pedi existe e faz sentido (404, 409) e so
    entao o ambiente (503). Falha do GitHub sai como 502 com o resumo intacto,
    para o clique valer de novo.
    """
    demanda, atual = _chat_guardado(supabase, demanda_id)
    if demanda.get("github_issue_numero") or atual.get("estado") == planejamento_demanda.ESTADO_ENVIADO:
        _conflito(MOTIVO_CHAT_TERMINOU)
    resumo = atual.get("resumo")
    if atual.get("estado") != planejamento_demanda.ESTADO_RESUMIDO or not resumo:
        _conflito(MOTIVO_CHAT_SEM_RESUMO)
    _exigir_integracao()

    if chat_tecnologia.em_planejamento(atual.get("mensagens") or []):
        # A melhoria (issue #1383): o PRD do diretor, que nasce na triagem
        # (`needs-triage` e `type:feature`) porque ainda passa pelo
        # `/to-issues`, atribuido ao dono da empresa.
        def corpo_do_prd(titulo: str) -> str:
            return corpo_do_prd_do_diretor(
                demanda_id=demanda_id,
                titulo=titulo,
                descricao=demanda.get("descricao"),
                resumo=resumo,
                link=link_da_demanda(demanda_id),
                anexos=tecnologia_anexos.quantos_guardados(supabase, demanda_id),
            )

        dono = login_para_publicar(settings.github_login_dono)
        _criar_issue_e_vincular(
            supabase,
            demanda=demanda,
            ator=ator,
            corpo=corpo_do_prd,
            assignees=[dono] if dono else [],
            labels=labels_da_issue_nova(chat_tecnologia.TIPO_DA_CLASSIFICACAO["melhoria"]),
        )
        linha = planejamento_demanda.marcar_enviado(supabase, demanda_id, agora=_agora())
        return _chat_para_a_tela(
            supabase, demanda_id, linha or {**atual, "estado": planejamento_demanda.ESTADO_ENVIADO}
        )

    produtos = supabase.table(TABELA_PRODUTOS).select("id, nome").eq("id", demanda.get("produto_id")).execute()
    produto_nome = (produtos.data or [{}])[0].get("nome") or SEM_PRODUTO

    def corpo(_titulo: str) -> str:
        return corpo_da_issue_do_bug(
            demanda_id=demanda_id,
            resumo=resumo,
            produto_nome=produto_nome,
            link=link_da_demanda(demanda_id),
            anexos=tecnologia_anexos.quantos_guardados(supabase, demanda_id),
        )

    _criar_issue_e_vincular(supabase, demanda=demanda, ator=ator, corpo=corpo, assignees=[], labels=LABELS_DO_BUG)
    linha = planejamento_demanda.marcar_enviado(supabase, demanda_id, agora=_agora())
    return _chat_para_a_tela(supabase, demanda_id, linha or {**atual, "estado": planejamento_demanda.ESTADO_ENVIADO})


# A lista de extensoes, o teto e as duas frases de recusa vem do SERVICO, que e
# quem manda a imagem ao modelo: e ele que precisa do tipo de cada extensao, e
# duas copias da regra divergiriam calado (o 413 recusando o que o payload
# saberia rotular).
MOTIVO_IMAGEM_FORA_DA_LISTA = assistente_tecnologia.MOTIVO_IMAGEM_FORA_DA_LISTA
MOTIVO_IMAGEM_GRANDE = assistente_tecnologia.MOTIVO_IMAGEM_GRANDE

# A frase de quando a imagem chegou inteira e a LEITURA nao aconteceu: provedor
# fora do ar, resposta vazia.
#
# Ela e separada das duas de cima porque a saida e outra: quem levou 422 ou 413
# tem que trocar de arquivo, e quem leva esta pode mandar o MESMO print de novo.
# Ela tambem nao culpa a imagem, porque o codigo nao sabe se o problema era ela.
MOTIVO_PRINT_ILEGIVEL = "Não deu para ler esse print agora. Tente de novo, ou escreva o que aparece na tela."


@router.post("/assistente/descrever-imagem", response_model=AssistenteImagemResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def assistente_descrever_imagem(
    request: Request,
    imagem: UploadFile = File(...),
    _ator: dict = Depends(require_super_admin),
):
    """O print anexado vira descricao, e a imagem some (ADR 0056, decisao 4).

    A primeira chamada MULTIMODAL do app. Nao grava NADA: nem storage, nem
    tabela, nem log com o conteudo. Os bytes ficam so na memoria do processo,
    com um identificador efemero que volta junto da descricao (issue #1062): o
    print vira Anexo quando a fala do chat que traz o identificador entra na
    conversa (ADR 0077, decisao 8), e some sozinho se nao entrar. O que a tela
    faz com o que sai daqui e escrever uma fala do diretor com o prefixo
    `[print] `, que e o que a deixa ver o que o assistente enxergou e o que faz
    o material entrar cercado no prompt do turno seguinte.

    O tipo da imagem vem da EXTENSAO, e nunca do `content-type` do cliente
    (mesma regra do Anexo da Manifestacao, ADR 0034): o cabecalho e escrito do
    lado de la.
    """
    extensao = os.path.splitext(imagem.filename or "")[1].lower()
    if extensao not in assistente_tecnologia.TIPOS_DE_IMAGEM:
        # Antes de ler os bytes, como na extracao: nao ha por que trazer um
        # video de 40 MB a memoria para recusa-lo pelo nome.
        _recusar(MOTIVO_IMAGEM_FORA_DA_LISTA)

    conteudo = await imagem.read()
    if len(conteudo) > assistente_tecnologia.LIMITE_DA_IMAGEM:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=MOTIVO_IMAGEM_GRANDE,
        )

    # Fora do loop (issue #773): a visao e a chamada mais longa de todas.
    texto = await ai_processor.chamar_ia_fora_do_loop(
        assistente_tecnologia.descrever_imagem, imagem=conteudo, extensao=extensao
    )
    if texto is None:
        # O servico nao levanta: ele devolve `None` para "nao deu para ler", e
        # quem escreve a frase e a rota. 502, e nao 422: o arquivo estava bom, e
        # quem leva este codigo pode mandar o MESMO print de novo.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MOTIVO_PRINT_ILEGIVEL)

    logger.info(f"Print lido para o Assistente por {_ator['id']}: {extensao}, {len(texto)} chars")
    # O print fica so na memoria, com um identificador efemero (issue #1062): vira
    # Anexo quando a fala do chat o trouxer, e some sozinho se nao trouxer.
    print_id = tecnologia_anexos.guardar_print(quem_id=_ator["id"], nome=imagem.filename or "", conteudo=conteudo)
    return {"texto": texto, "print_id": print_id}
