"""Router /admin/tecnologia, a aba Tecnologia (PRD #634, ADR 0050).

Desde a ADR 0077 a aba e uma tela so: o chat do Assistente de Tecnologia, em
que o diretor relata um bug ou pede uma melhoria e o card nasce no GitHub. O
Quadro, o Painel, os Produtos, o formulario a mao, a Conversa da Demanda, as
mencoes, o e-mail da aba, o Vinculo por numero, o Assistente de entrada e a
tela antiga do Planejamento sairam do codigo na issue #1386.

Todos os endpoints exigem `require_super_admin`. Esse e o gate de verdade: a
sidebar apenas esconde o item, e esconder nao e proteger (ADR 0050, decisao 2).

O chat da aba (issues #1381, #1383 e #1384):

- GET   /admin/tecnologia/eu                    se quem esta logado e
                                                Desenvolvedor (ADR 0083).
- GET   /admin/tecnologia/chat                  a lista lateral: as Demandas
                                                de quem esta logado, da mais
                                                recente para a mais antiga;
                                                `?filtro=todas` traz as de
                                                todos ao Desenvolvedor, e
                                                `?filtro=para_mim` as de que
                                                ele e o Responsavel. Combinam
                                                com isso a busca pelo titulo e
                                                os filtros Tipo, Etapa,
                                                Responsavel e Envio falhou
                                                (issue #1551).
- GET   /admin/tecnologia/entregas              a aba Entregas: os cards
                                                entregues por semana ou por
                                                mes, com filtros de periodo,
                                                tipo, Origem e Responsavel.
                                                So leitura (issue #1556).
- GET   /admin/tecnologia/desenvolvedores       o "Quem cuida disto?" do
                                                resumo (ADR 0083).
- POST  /admin/tecnologia/chat                  o primeiro turno: a Demanda
                                                nasce aqui.
- GET   /admin/tecnologia/chat/{id}             a conversa guardada.
- POST  /admin/tecnologia/chat/{id}             um turno: a fala do diretor
                                                entra, a da IA volta.
- POST  /admin/tecnologia/chat/{id}/nao-bateu   o que nao bateu no resumo.
- POST  /admin/tecnologia/chat/{id}/resumo      o "Fechar e resumir" da
                                                melhoria.
- POST  /admin/tecnologia/chat/{id}/criar-card  cria a issue (o bug pronto para
                                                a onda, ou o PRD do diretor),
                                                designada ao Responsavel, e
                                                vincula.
- POST  /admin/tecnologia/chat/{id}/reenviar    o "Reenviar" do Envio falhou,
                                                pela mesma porta (issue #1535).
- POST  /admin/tecnologia/chat/{id}/designar-de-novo  so a designacao da
                                                issue que nasceu sem o
                                                Responsavel, pelo
                                                Desenvolvedor (issue #1536).
- DELETE /admin/tecnologia/chat/{id}            o "Apagar": a conversa
                                                Registrada pelo autor, o card
                                                ate Planejada pelo
                                                Desenvolvedor, que fecha no
                                                GitHub como nao planejado
                                                (issue #1549, ADR 0084).

O print do chat (ADR 0056, decisao 4; ADR 0077, decisao 8):

- POST  /admin/tecnologia/assistente/descrever-imagem  le o print e devolve a
                                                       descricao com o
                                                       identificador efemero
                                                       que o faz Anexo.
- POST  /admin/tecnologia/assistente/ler-documento     extrai o texto do
                                                       documento, sem IA, e
                                                       devolve o identificador
                                                       (issue #1520).

Fora daqui, e de pe: o webhook do GitHub que deriva a Etapa
(`routers/webhooks.py`), a rota de automacao dos anexos
(`routers/tecnologia_automacao.py`) e o cron de hora em hora
(`cron/scheduler.py`).
"""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from datetime import UTC, date, datetime
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from supabase import Client

from app.config import settings
from app.dependencies import get_supabase_client, is_super_admin, require_super_admin, selecionar_participantes
from app.limiter import limiter
from app.models.tecnologia_schemas import (
    AssistenteDocumentoResponse,
    AssistenteImagemResponse,
    ChatNaoBateuPayload,
    ChatPrimeiroTurnoPayload,
    ChatResponse,
    ChatTurnoPayload,
    ConversaDaDemandaResponse,
    CriarOCardPayload,
    DemandaResponse,
    DesenvolvedorResponse,
    EntregasResponse,
    EstimativaDaRevisao,
    MensagemDaConversaPayload,
    MensagemDaConversaResponse,
    QuemSouNaAbaResponse,
    RevisarPayload,
)
from app.services import (
    ai_processor,
    assistente_tecnologia,
    chat_tecnologia,
    custo_da_conversa,
    github_client,
    planejamento_demanda,
    tecnologia_anexos,
    tecnologia_apagar,
    tecnologia_email,
    tecnologia_entregas,
    tecnologia_envio,
    tecnologia_revisao,
    tecnologia_sincronizacao,
)
from app.services.conhecimento import carregar_kit
from app.services.mencoes import extrair_mencoes
from app.services.notificacao_service import criar_notificacao_tecnologia
from app.services.tecnologia import (
    MOTIVO_REVISAR_JA_COMECOU,
    ORIGEM_VITTA,
    SEM_PRODUTO,
    TABELA_CONVERSA_DA_DEMANDA,
    TABELA_DEMANDAS,
    TABELA_PRODUTOS,
    e_desenvolvedor,
    em_producao_desde,
    entregue_na_data,
    instante_do_banco,
    login_do_responsavel,
    origem_da_demanda,
    pode_ver,
    quem_avisar,
    recusa_de_apagar,
    recusa_de_revisar,
    responsavel_da_demanda,
    versao_da_entrega,
)
from app.services.tecnologia_vinculo import (
    ETAPA_REGISTRADA,
    ETAPAS,
    LABEL_ORIGEM_DIRETOR,
    LABELS_DO_BUG,
    MOTIVO_CRIACAO_EM_ANDAMENTO,
    MOTIVO_GITHUB_INDISPONIVEL,
    MOTIVO_INTEGRACAO_DESLIGADA,
    corpo_da_issue_do_bug,
    corpo_do_prd_do_diretor,
    labels_da_issue_nova,
    link_da_demanda,
    login_para_publicar,
    normalizar_github_login,
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
    """A Demanda, ou 404. A lapide do Apagar (ADR 0084, decisao 2) responde como
    inexistente: toda leitura e toda escrita da aba passam por aqui."""
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("id", demanda_id).is_("apagada_em", "null").execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")
    return result.data[0]


def _para_a_lista(supabase: Client, demandas: list[dict], *, ator: dict) -> list[dict]:
    """A Demanda como a lista lateral do chat a le (issue #1384).

    E o funil por onde a Demanda sai desta API, e por isso o corte e aqui:
    numero e endereco da issue nao saem para o diretor (ADR 0054, decisao 9), e
    ele le a Etapa e O que muda sem nenhum dos dois. O Desenvolvedor le tambem
    o autor, o numero e o link (ADR 0083, decisao 3). O Responsavel sai para
    os dois (ADR 0083, decisao 5), e o selo "Envio falhou" tambem; o motivo
    tecnico da falha, so para o Desenvolvedor (issue #1535). A designacao
    falhada sai so para o Desenvolvedor (issue #1536). O `pode_apagar` diz a
    tela se mostra o "Apagar" (issue #1549), pela regra da rota. A `origem`
    da o selo "Pedido do diretor" ou "Vitta" (issue #1554).
    """
    desenvolvedor = e_desenvolvedor(ator)
    ids = {responsavel_da_demanda(d) for d in demandas}
    if desenvolvedor:
        ids |= {d.get("autor_id") for d in demandas}
    nomes = _nomes(supabase, ids)
    conversas = _conversas_dos_cards(supabase, demandas)
    return [
        {
            **d,
            "tem_vinculo": bool(d.get("github_issue_numero")),
            "partes": _partes_visiveis(d),
            "versao": versao_da_entrega(d),
            "fechada_em": entregue_na_data(d),
            "em_producao_em": em_producao_desde(d),
            "classificacao": chat_tecnologia.CLASSIFICACAO_DO_TIPO.get(str(d.get("tipo") or "")),
            "minha": d.get("autor_id") == ator["id"],
            "autor": nomes.get(str(d.get("autor_id"))) if desenvolvedor else None,
            "issue_numero": d.get("github_issue_numero") if desenvolvedor else None,
            "issue_url": _url_da_issue(d) if desenvolvedor else None,
            "responsavel": _nome_do_responsavel(d, nomes),
            "envio_falhou": tecnologia_envio.envio_falhou(d),
            "designacao_falhou": desenvolvedor and tecnologia_envio.designacao_falhou(d),
            "envio_motivo": d.get("envio_motivo") if desenvolvedor and _falha_pendente(d) else None,
            "pode_apagar": recusa_de_apagar(ator, d) is None,
            "origem": origem_da_demanda(d),
            **_revisao_na_lista(ator, d, conversas.get(str(d["id"]))),
        }
        for d in demandas
    ]


def _conversas_dos_cards(supabase: Client, demandas: list[dict]) -> dict[str, dict]:
    """O estado da conversa de cada Demanda que pode ser revisada (issue #1557):
    uma leitura so, e so dos cards da melhoria."""
    ids = [
        str(d["id"])
        for d in demandas
        if d.get("github_issue_numero") and d.get("tipo") == "novo" and origem_da_demanda(d) != ORIGEM_VITTA
    ]
    if not ids:
        return {}
    result = (
        supabase.table(planejamento_demanda.TABELA_PLANEJAMENTOS)
        .select("demanda_id, estado, revisao_iniciada_em")
        .in_("demanda_id", ids)
        .execute()
    )
    return {str(linha["demanda_id"]): linha for linha in (result.data or [])}


def _revisao_na_lista(ator: dict, demanda: dict, conversa: dict | None) -> dict:
    """O botao "Revisar com o codigo de hoje" e a conversa reaberta pela
    revisao (issue #1557). O botao so com a conversa ja enviada: a que esta em
    revisao ainda nao virou card de novo."""
    estado = (conversa or {}).get("estado")
    return {
        "pode_revisar": recusa_de_revisar(ator, demanda) is None and estado == planejamento_demanda.ESTADO_ENVIADO,
        "em_revisao": bool((conversa or {}).get("revisao_iniciada_em"))
        and estado not in (None, planejamento_demanda.ESTADO_ENVIADO),
    }


def _falha_pendente(demanda: dict) -> bool:
    """O envio ou a designacao que falhou e ainda espera alguem (issues #1535 e #1536)."""
    return tecnologia_envio.envio_falhou(demanda) or tecnologia_envio.designacao_falhou(demanda)


def _nome_do_responsavel(demanda: dict, nomes: dict[str, str]) -> str | None:
    """O Responsavel como a tela o mostra: o nome do usuario, ou o login do
    dono no GitHub quando ele nao e usuario do app (issue #1534, ADR 0083,
    decisao 6)."""
    return nomes.get(str(responsavel_da_demanda(demanda))) or login_do_responsavel(demanda)


def _nomes(supabase: Client, ids: set) -> dict[str, str]:
    ids_lidos = sorted({str(i) for i in ids if i})
    if not ids_lidos:
        return {}
    result = selecionar_participantes(supabase, "id, nome_completo", lambda q: q.in_("id", ids_lidos))
    return {str(p["id"]): p.get("nome_completo") or "" for p in (result.data or [])}


def _url_da_issue(demanda: dict) -> str | None:
    """O endereco da issue-raiz: o que a foto do GitHub guardou, ou o montado
    pelo numero quando a foto ainda nao veio."""
    numero = demanda.get("github_issue_numero")
    if not numero:
        return None
    foto = demanda.get("github_foto")
    if isinstance(foto, dict) and foto.get("url"):
        return str(foto["url"])
    repo = settings.github_integracao_repo
    return f"https://github.com/{repo}/issues/{numero}" if repo else None


def _partes_visiveis(demanda: dict) -> list[dict]:
    """As partes da entrega como o diretor as le (issue #676): o texto, a
    situacao e a data do fechamento (issue #1552), sem o numero da fatia, que
    e interno."""
    partes = demanda.get("partes")
    if not isinstance(partes, list):
        return []
    return [
        {
            "o_que_muda": parte.get("o_que_muda"),
            "situacao": parte.get("situacao"),
            "fechada_em": parte.get("fechada_em"),
        }
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


AVISO_DO_ENVIO_FALHOU = "O envio de um card falhou"
AVISO_DA_DESIGNACAO_FALHOU = "Um card nasceu sem o Responsável"


def _avisar_os_desenvolvedores(supabase: Client, demanda: dict, *, titulo: str) -> None:
    """A falha do envio no sino de cada Desenvolvedor (issue #1536, ADR 0083,
    decisao 7). O aviso abre a Demanda, onde estao o motivo e o botao."""
    for pessoa in _desenvolvedores(supabase):
        criar_notificacao_tecnologia(
            supabase,
            destinatario_id=str(pessoa["id"]),
            titulo=titulo,
            mensagem=str(demanda.get("titulo") or "")[:80],
            demanda_id=str(demanda["id"]),
        )


def _enviar(
    supabase: Client,
    *,
    demanda: dict,
    ator: dict,
    corpo,
    assignees: list[str],
    labels: list[str],
    responsavel_id: str | None,
) -> dict:
    """A porta unica do envio (`tecnologia_envio.enviar`, issue #1535) em HTTP.

    Duplo clique e 422; Demanda que sumiu e 404. A falha ja ficou gravada na
    Demanda como "Envio falhou" quando chega aqui, e sai como 503 (falta
    configuracao) ou 502 (o GitHub nao criou), com o resumo intacto. Devolve a
    linha da Demanda ja vinculada.
    """
    try:
        envio = tecnologia_envio.enviar(
            supabase,
            demanda=demanda,
            ator=ator,
            corpo=corpo,
            assignees=assignees,
            labels=labels,
            responsavel_id=responsavel_id,
        )
    except tecnologia_envio.EnvioEmAndamentoError:
        _recusar(MOTIVO_CRIACAO_EM_ANDAMENTO)
    except tecnologia_envio.DemandaSumiuError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada") from None
    if not envio.criado:
        _avisar_os_desenvolvedores(supabase, demanda, titulo=AVISO_DO_ENVIO_FALHOU)
    elif envio.designacao_falhou:
        _avisar_os_desenvolvedores(supabase, demanda, titulo=AVISO_DA_DESIGNACAO_FALHOU)
    if envio.integracao_desligada:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MOTIVO_INTEGRACAO_DESLIGADA)
    if not envio.criado:
        _issue_indisponivel()
    return envio.demanda


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
    anexos_da_demanda: list[dict] | None = None,
    responsavel: str | None = None,
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
        "mensagens": chat_tecnologia.para_a_tela(
            mensagens, _nomes(supabase, chat_tecnologia.quem_respondeu(mensagens))
        ),
        "resumo": None if planejamento else linha.get("resumo"),
        "resumo_da_melhoria": linha.get("resumo") if planejamento else None,
        # O documento vivo, so da melhoria (issue #1553): o bug segue o
        # Roteiro do bug, sem documento ao lado.
        "documento": linha.get("documento") if planejamento else None,
        # As imagens: e o que a linha "Prints" do resumo do bug conta.
        "anexos": tecnologia_anexos.quantos_guardados(supabase, demanda_id)[0],
        "planejamento": planejamento,
        "aviso_dos_anexos": aviso_dos_anexos,
        "custo": custo_da_conversa.da_demanda(supabase, demanda_id),
        "anexos_da_demanda": anexos_da_demanda or [],
        "responsavel": responsavel,
        "revisao": _revisao_da_conversa(linha),
    }


def _revisao_da_conversa(linha: dict) -> dict | None:
    """A marca da revisao e o que o "isso atende?" ja decidiu (issue #1557)."""
    if not linha.get("revisao_iniciada_em"):
        return None
    _, planejamento = chat_tecnologia.partes_da_melhoria(linha.get("mensagens") or [])
    return {
        "iniciada_em": linha.get("revisao_iniciada_em"),
        "versao_base": linha.get("revisao_versao_base"),
        **(tecnologia_revisao.escopo(planejamento) or {"saiu": [], "continua": []}),
    }


def _respondido_por(fala: dict, ator: dict) -> dict:
    """A fala de gente com quem a escreveu (ADR 0084, decisao 3): o autor ou o
    Desenvolvedor, que na revisao tambem responde."""
    return {**fala, "respondido_por": ator["id"]}


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
                # O Responsavel nasce no "Criar o card" (ADR 0083, decisao 5).
                "responsavel_id": None,
                "autor_id": ator["id"],
                "prioridade": "normal",
            }
        )
        .execute()
    )
    if not criada.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao criar a Demanda")
    return criada.data[0]


def _rascunho_do_documento(resultado) -> dict:
    """O rascunho do documento do card que o turno da melhoria trouxe (issue
    #1553, ADR 0084, decisao 7). O turno sem rascunho deixa o de antes."""
    return {"documento": resultado.documento} if resultado.documento else {}


def _estado_do_planejamento(mensagem: dict) -> str:
    if mensagem.get("tipo") == "encerrou":
        return planejamento_demanda.ESTADO_ENCERRADO
    return planejamento_demanda.ESTADO_EM_ANDAMENTO


async def _comecar_a_melhoria(
    supabase: Client, *, ator: dict, falas: list[dict], produtos: list[dict], prints: list[str], documentos: list[str]
) -> dict:
    """O botao "Melhoria" abre o planejamento na hora (issue #1383): a primeira
    fala da IA ja e a primeira pergunta, com as duas opcoes e a recomendada.

    A Demanda nasce depois do turno, como no bug: um turno que falhou nao deixa
    Demanda vazia. Ela nasce Novo, no primeiro Produto e com o titulo que o
    modelo deu ja na primeira pergunta (issue #1438); sem ele, com o titulo
    provisorio. Os turnos seguintes e o resumo podem refinar.
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
        titulo=resultado.titulo or chat_tecnologia.TITULO_SEM_RESPOSTA,
        tipo=chat_tecnologia.TIPO_DA_CLASSIFICACAO["melhoria"],
        produto=produtos[0],
    )
    demanda_id = str(demanda["id"])
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, {**resultado.chamada, "demanda_id": demanda_id})
    descricao = chat_tecnologia.descricao_da_melhoria(falas)
    if descricao:
        supabase.table(TABELA_DEMANDAS).update({"descricao": descricao}).eq("id", demanda_id).execute()

    aviso = _prints_do_turno(supabase, demanda=demanda, print_ids=prints, ator=ator, documento_ids=documentos)
    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=None,
        novo={
            "estado": _estado_do_planejamento(resultado.mensagem),
            "mensagens": [*falas, resultado.mensagem],
            "decisoes": [resultado.decisao] if resultado.decisao else [],
            "atualizado_em": _agora(),
            **_rascunho_do_documento(resultado),
        },
    )
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


def _prints_do_turno(
    supabase: Client, *, demanda: dict, print_ids: list[str], ator: dict, documento_ids: list[str] | None = None
) -> str | None:
    """Os prints e os documentos que a fala do diretor trouxe viram Anexo da
    Demanda na hora (ADR 0077, decisao 8; issue #1520), e so quando a fala
    entrou na conversa: o turno que falhou devolve o 502 antes de chegar aqui,
    e o arquivo espera o reenvio."""
    avisos = []
    if print_ids:
        avisos.append(
            tecnologia_anexos.anexar_prints(supabase, demanda=demanda, print_ids=print_ids, quem_id=ator["id"])
        )
    if documento_ids:
        avisos.append(
            tecnologia_anexos.anexar_documentos(
                supabase, demanda=demanda, documento_ids=documento_ids, quem_id=ator["id"]
            )
        )
    return " ".join(a for a in avisos if a) or None


def _documentos_da_fala(supabase: Client, *, demanda_id: str | None, ids: list[str], ator: dict) -> list[dict]:
    """Os documentos que a fala traz (issue #1520), lidos da memoria SEM sair
    dela: o turno ainda pode falhar, e o reenvio tem que acha-los. O texto de
    cada um entra na fala; o original sai da memoria so quando vira Anexo.

    Duas recusas, antes de qualquer IA: o documento que nao esta mais guardado
    (a fala sem ele seria vazia) e o que nao caberia no teto de dez anexos da
    Demanda, somando imagens e documentos.
    """
    documentos = []
    for documento_id in dict.fromkeys(ids):
        guardado = tecnologia_anexos.ver_documento(quem_id=ator["id"], documento_id=documento_id)
        if guardado is None:
            _conflito(tecnologia_anexos.MOTIVO_DOCUMENTO_SUMIU)
        documentos.append(
            {"nome": guardado["nome"], "tamanho_bytes": len(guardado["conteudo"]), "texto": guardado["texto"]}
        )
    if demanda_id and documentos and tecnologia_anexos.posicoes_livres(supabase, demanda_id) < len(documentos):
        _recusar(tecnologia_anexos.MOTIVO_ANEXOS_DEMAIS)
    return documentos


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


@router.get("/eu", response_model=QuemSouNaAbaResponse)
async def quem_sou_na_aba(ator: dict = Depends(require_super_admin)):
    """Se quem esta logado e Desenvolvedor (ADR 0083, decisao 2)."""
    return {"desenvolvedor": e_desenvolvedor(ator)}


# A recusa do Responsavel que nao esta no "Quem cuida disto?": a tela so
# oferece Desenvolvedor, e o id que chega de fora dela nao vira assignee.
MOTIVO_RESPONSAVEL_FORA_DA_LISTA = "Escolha quem cuida disto entre as pessoas da lista."


def _desenvolvedores(supabase: Client) -> list[dict]:
    """Os Desenvolvedores do cadastro, pelo nome: o Super admin ativo com login
    do GitHub (ADR 0083, decisao 2). E quem pode ser Responsavel."""
    result = selecionar_participantes(
        supabase, "id, nome_completo, access_profile, is_super_admin, github_login, ativo"
    )
    pessoas = [p for p in (result.data or []) if p.get("ativo") is not False and e_desenvolvedor(p)]
    return sorted(pessoas, key=lambda p: (p.get("nome_completo") or "").casefold())


def _id_do_dono(desenvolvedores: list[dict]) -> str | None:
    """Quem tem, no cadastro, o login do dono que esta na configuracao: o
    Responsavel do card sem escolha."""
    dono = login_para_publicar(settings.github_login_dono)
    pessoa = next((p for p in desenvolvedores if dono and normalizar_github_login(p.get("github_login")) == dono), None)
    return str(pessoa["id"]) if pessoa else None


def _responsavel_do_card(
    supabase: Client, escolhido: str | None, *, guardado: bool = False
) -> tuple[list[str], str | None]:
    """O assignee da issue e o Responsavel da Demanda (ADR 0083, decisao 5).

    Com escolha, o Desenvolvedor escolhido. Sem escolha, o login do dono que ja
    esta na configuracao, em bug e em melhoria; o Responsavel e quem tem esse
    login no cadastro, ou ninguem, e o card nasce designado do mesmo jeito.

    `guardado` e o Responsavel que ficou na Demanda no clique que falhou (o
    "Reenviar", issue #1535): quem deixou de ser Desenvolvedor desde entao
    conta como sem escolha, em vez de recusar o reenvio.
    """
    desenvolvedores = _desenvolvedores(supabase)
    pessoa = next((p for p in desenvolvedores if escolhido and str(p["id"]) == escolhido), None)
    if escolhido and pessoa is None and not guardado:
        _recusar(MOTIVO_RESPONSAVEL_FORA_DA_LISTA)
    if pessoa is not None:
        login = login_para_publicar(pessoa.get("github_login"))
        return ([login] if login else []), str(pessoa["id"])
    dono = login_para_publicar(settings.github_login_dono)
    return ([dono] if dono else []), _id_do_dono(desenvolvedores)


@router.get("/desenvolvedores", response_model=list[DesenvolvedorResponse])
async def listar_os_desenvolvedores(
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Quem cuida disto?" do resumo (ADR 0083, decisao 5). `padrao` marca
    para quem vai o card sem escolha, e a tela diz o nome."""
    desenvolvedores = _desenvolvedores(supabase)
    dono = _id_do_dono(desenvolvedores)
    return [
        {"id": str(p["id"]), "nome": p.get("nome_completo") or "", "padrao": str(p["id"]) == dono}
        for p in desenvolvedores
    ]


def _sem_acento(texto: str) -> str:
    """O texto como a busca da lista o compara: sem acento e sem caixa (issue #1551)."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").casefold()


@router.get("/chat", response_model=list[DemandaResponse])
async def listar_as_conversas(
    filtro: Literal["minhas", "todas", "para_mim"] = "minhas",
    busca: str | None = None,
    tipo: Literal["bug", "melhoria"] | None = None,
    etapa: str | None = None,
    responsavel: str | None = None,
    envio_falhou: bool = False,
    origem: Literal["diretor", "vitta"] | None = None,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A lista ao lado do chat (issue #1384): as Demandas que o Super admin
    logado pediu, com o titulo e a Etapa, a mais recente primeiro.

    `todas` e o filtro do Desenvolvedor (ADR 0083, decisao 3). Quem corta e o
    `pode_ver`, a mesma regra da leitura da conversa: para quem nao e
    Desenvolvedor, `todas` volta so as dele. `para_mim` e o padrao da lista do
    Desenvolvedor: as Demandas de que ele e o Responsavel (ADR 0083, decisao 5).

    Por cima do recorte, e combinando entre si (issue #1551): a `busca` pelo
    titulo, sem diferenciar maiuscula e acento; o `tipo` (bug ou melhoria); a
    `etapa`; o `responsavel` (o id de quem cuida); e o `envio_falhou`, as
    Demandas cujo card nao chegou ao GitHub (issue #1535), de todos os autores
    mesmo partindo de `para_mim`, porque elas nao tem Responsavel. `para_mim`,
    `responsavel` e `envio_falhou` sao do Desenvolvedor, como os chips da
    tela, e a rota os recusa a quem nao e. A `origem` (issue #1554) e para
    todos.

    O diretor ve, alem das dele, os cards de Origem Vitta, abertos pelo
    terminal (ADR 0084, decisao 4): o "Minhas" dele e o `pode_ver`, e o do
    Desenvolvedor continua sendo o que ele mesmo pediu.

    Sai pelo `_para_a_lista`, o funil da Demanda desta API: e la que numero e
    endereco da issue ficam de fora para o diretor.
    """
    if not e_desenvolvedor(ator) and (filtro == "para_mim" or responsavel or envio_falhou):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Filtro so do Desenvolvedor")
    if etapa is not None and etapa not in ETAPAS:
        _recusar("Etapa desconhecida")
    # A lapide do Apagar fica fora de todo filtro (ADR 0084, decisao 2).
    consulta = supabase.table(TABELA_DEMANDAS).select("*").is_("apagada_em", "null")
    if filtro == "minhas" and e_desenvolvedor(ator):
        consulta = consulta.eq("autor_id", ator["id"])
    elif filtro == "para_mim":
        consulta = consulta.eq("responsavel_id", ator["id"])
    result = consulta.order("criado_em", desc=True).execute()
    visiveis = [d for d in (result.data or []) if pode_ver(ator, d)]
    # A Demanda em Envio falhou nao tem card, logo nao tem Responsavel: com
    # `envio_falhou`, o recorte por Responsavel (Para mim e o `responsavel`)
    # nao corta, senao a lista do Desenvolvedor, que abre em Para mim, sairia
    # sempre vazia (issue #1535).
    if filtro == "para_mim" and not envio_falhou:
        visiveis = [d for d in visiveis if responsavel_da_demanda(d) == ator["id"]]
    if busca and busca.strip():
        procurado = _sem_acento(busca.strip())
        visiveis = [d for d in visiveis if procurado in _sem_acento(str(d.get("titulo") or ""))]
    if tipo:
        visiveis = [d for d in visiveis if d.get("tipo") == chat_tecnologia.TIPO_DA_CLASSIFICACAO[tipo]]
    if etapa:
        visiveis = [d for d in visiveis if (d.get("etapa") or ETAPA_REGISTRADA) == etapa]
    if responsavel and not envio_falhou:
        visiveis = [d for d in visiveis if responsavel_da_demanda(d) == responsavel]
    if envio_falhou:
        visiveis = [d for d in visiveis if tecnologia_envio.envio_falhou(d)]
    if origem:
        visiveis = [d for d in visiveis if origem_da_demanda(d) == origem]
    return _para_a_lista(supabase, visiveis, ator=ator)


@router.get("/entregas", response_model=EntregasResponse)
async def listar_as_entregas(
    agrupar: Literal["semana", "mes"] = "semana",
    de: date | None = None,
    ate: date | None = None,
    tipo: Literal["bug", "melhoria"] | None = None,
    origem: Literal["diretor", "vitta"] | None = None,
    responsavel: str | None = None,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A aba Entregas (issue #1556, ADR 0084, decisao 8): os cards entregues,
    contados por semana ou por mes. So leitura: ninguem move nada por aqui.

    Entra o que quem pede ve (`pode_ver`, a regra da lista do chat), fora a
    lapide do Apagar e o card que nao foi entregue. Os filtros combinam: o
    periodo (`de` e `ate`, dias do hospital, inclusive) sobre a data de
    entrega, o `tipo`, a `origem` e o `responsavel`, que aqui e de todos: o id
    do usuario, ou o login do dono no GitHub quando ele nao e usuario do app.
    A contagem segue os filtros; as opcoes do Responsavel, nao, para o filtro
    ligado poder trocar.

    Sai pelo `_para_a_lista`, o mesmo funil da lista do chat: o clique abre o
    Documento do card sem outro pedido, e numero e link seguem so para o
    Desenvolvedor.
    """
    if de and ate and de > ate:
        _recusar("O inicio do periodo vem depois do fim")
    result = supabase.table(TABELA_DEMANDAS).select("*").is_("apagada_em", "null").execute()
    entregues = [
        (dia, d)
        for d in (result.data or [])
        if pode_ver(ator, d) and (dia := tecnologia_entregas.dia_da_entrega(d)) is not None
    ]
    entregues.sort(key=lambda par: par[0], reverse=True)
    nomes = _nomes(supabase, {responsavel_da_demanda(d) for _, d in entregues})
    opcoes = {
        chave: _nome_do_responsavel(d, nomes) or chave
        for _, d in entregues
        if (chave := tecnologia_entregas.chave_do_responsavel(d))
    }
    filtradas = [
        (dia, d)
        for dia, d in entregues
        if (de is None or dia >= de)
        and (ate is None or dia <= ate)
        and (tipo is None or chat_tecnologia.CLASSIFICACAO_DO_TIPO.get(str(d.get("tipo") or "")) == tipo)
        and (origem is None or origem_da_demanda(d) == origem)
        and (responsavel is None or tecnologia_entregas.chave_do_responsavel(d) == responsavel)
    ]
    return {
        "agrupar": agrupar,
        "periodos": tecnologia_entregas.contagem([dia for dia, _ in filtradas], agrupar),
        "entregas": _para_a_lista(supabase, [d for _, d in filtradas], ator=ator),
        "responsaveis": [
            {"valor": valor, "nome": nome} for valor, nome in sorted(opcoes.items(), key=lambda par: par[1].casefold())
        ],
    }


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
    if not payload.escolha and not texto and not payload.documentos:
        _recusar(chat_tecnologia.MOTIVO_SEM_TEXTO)
    documentos = _documentos_da_fala(supabase, demanda_id=None, ids=payload.documentos, ator=ator)

    produtos = _produtos_ativos(supabase)
    falas = [chat_tecnologia.mensagem_de_abertura()]
    if payload.escolha:
        falas.append(_respondido_por(chat_tecnologia.fala_do_diretor(chat_tecnologia.ESCOLHAS[payload.escolha]), ator))
    if texto or documentos:
        falas.append(_respondido_por(chat_tecnologia.fala_do_diretor(texto, documentos), ator))

    if payload.escolha == "melhoria":
        return await _comecar_a_melhoria(
            supabase, ator=ator, falas=falas, produtos=produtos, prints=payload.prints, documentos=payload.documentos
        )

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

    aviso = _prints_do_turno(
        supabase, demanda=demanda, print_ids=payload.prints, ator=ator, documento_ids=payload.documentos
    )
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
    supabase: Client,
    *,
    demanda: dict,
    atual: dict,
    payload: ChatTurnoPayload,
    ator: dict,
    depois_do_fim: bool,
    documentos: list[dict],
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
    elif documentos:
        # O documento vale como resposta em texto livre (issue #1520): com ou
        # sem pergunta em aberto, e nunca junto da letra de uma opcao.
        if payload.opcao:
            _recusar(planejamento_demanda.MOTIVO_DUAS_RESPOSTAS)
        resposta = {"tipo": "resposta", "opcao": None, "texto": (payload.texto or "").strip(), "documentos": documentos}
    else:
        resposta, motivo = planejamento_demanda.resposta_do_diretor(
            planejamento, opcao=payload.opcao, texto=payload.texto, depois_do_fim=depois_do_fim
        )
        if motivo:
            _recusar(motivo)
    if resposta is not None:
        mensagens.append(_respondido_por(resposta, ator))

    # Na revisao, o proximo "isso atende?" e do codigo, sem IA (issue #1557).
    atende = tecnologia_revisao.proxima_pergunta_de_atende(mensagens)
    if atende is not None:
        linha = planejamento_demanda.gravar(
            supabase,
            demanda_id,
            atual=atual,
            novo={
                "estado": planejamento_demanda.ESTADO_EM_ANDAMENTO,
                "mensagens": [*mensagens, atende],
                "atualizado_em": _agora(),
            },
        )
        if linha is None:
            _conflito(MOTIVO_CHAT_MUDOU)
        aviso = _prints_do_turno(
            supabase, demanda=demanda, print_ids=payload.prints, ator=ator, documento_ids=payload.documentos
        )
        return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)

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
            **_rascunho_do_documento(resultado),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    # O titulo acompanha a conversa a cada turno em que o modelo o der (issue
    # #1438); o turno sem titulo deixa o que a Demanda tem.
    if resultado.titulo and resultado.titulo != demanda.get("titulo"):
        supabase.table(TABELA_DEMANDAS).update({"titulo": resultado.titulo}).eq("id", demanda_id).execute()
    aviso = _prints_do_turno(
        supabase, demanda=demanda, print_ids=payload.prints, ator=ator, documento_ids=payload.documentos
    )
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


@router.get("/chat/{demanda_id}", response_model=ChatResponse)
async def ler_o_chat(
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A conversa guardada, para retomar de onde parou.

    So o autor e o Desenvolvedor a abrem (ADR 0083): a Demanda de outro autor
    responde como inexistente, sem dizer que existe. O Desenvolvedor le tambem
    os Anexos.
    """
    demanda, linha = _chat_guardado(supabase, demanda_id)
    if not pode_ver(ator, demanda):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MOTIVO_CHAT_NAO_ENCONTRADO)
    anexos = tecnologia_anexos.para_quem_desenvolve(supabase, demanda_id) if e_desenvolvedor(ator) else None
    # O Responsavel de agora, derivado do GitHub (issue #1534): so leitura.
    responsavel = _nome_do_responsavel(demanda, _nomes(supabase, {responsavel_da_demanda(demanda)}))
    return _chat_para_a_tela(supabase, demanda_id, linha, anexos_da_demanda=anexos, responsavel=responsavel)


# ─── A Conversa da Demanda (issue #1537, ADR 0083, decisao 8) ──────────────


def _demanda_visivel(supabase: Client, demanda_id: str, ator: dict) -> dict:
    """A Demanda, se quem pede a ve; senao 404, como a leitura do chat: a de
    outro autor responde como inexistente, sem dizer que existe."""
    demanda = _buscar_demanda(supabase, demanda_id)
    if not pode_ver(ator, demanda):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MOTIVO_CHAT_NAO_ENCONTRADO)
    return demanda


def _mencionaveis(supabase: Client, demanda: dict) -> list[dict]:
    """Quem ve a Demanda: o autor e os Desenvolvedores, e no card de Origem
    Vitta toda a diretoria (ADR 0084, decisao 4). E so quem a menção alcanca,
    para o aviso nunca levar alguem a uma Demanda que ele nao abre."""
    if origem_da_demanda(demanda) == ORIGEM_VITTA:
        result = selecionar_participantes(supabase, "id, nome_completo, access_profile, is_super_admin, ativo")
        diretoria = [p for p in (result.data or []) if p.get("ativo") is not False and is_super_admin(p)]
        return sorted(diretoria, key=lambda p: (p.get("nome_completo") or "").casefold())
    pessoas = {str(p["id"]): p for p in _desenvolvedores(supabase)}
    autor_id = demanda.get("autor_id")
    if autor_id and str(autor_id) not in pessoas:
        result = selecionar_participantes(supabase, "id, nome_completo", lambda q: q.eq("id", autor_id))
        pessoas.update({str(p["id"]): p for p in (result.data or [])})
    return sorted(pessoas.values(), key=lambda p: (p.get("nome_completo") or "").casefold())


def _mensagem_para_a_tela(linha: dict, *, nomes: dict[str, str], ator: dict) -> dict:
    return {
        "id": str(linha["id"]),
        "autor": nomes.get(str(linha.get("autor_id"))),
        "texto": linha.get("texto") or "",
        "criado_em": linha.get("criado_em"),
        "minha": linha.get("autor_id") == ator["id"],
    }


@router.get("/chat/{demanda_id}/conversa", response_model=ConversaDaDemandaResponse)
async def ler_a_conversa_da_demanda(
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A Conversa da Demanda, da mais antiga para a mais nova, e quem pode ser
    mencionado nela. So quem ve a Demanda a le."""
    demanda = _demanda_visivel(supabase, demanda_id, ator)
    linhas = (
        supabase.table(TABELA_CONVERSA_DA_DEMANDA)
        .select("*")
        .eq("demanda_id", demanda_id)
        .order("criado_em")
        .execute()
        .data
        or []
    )
    nomes = _nomes(supabase, {linha.get("autor_id") for linha in linhas})
    return {
        "mensagens": [_mensagem_para_a_tela(linha, nomes=nomes, ator=ator) for linha in linhas],
        "mencionaveis": [
            {"id": str(p["id"]), "nome": p.get("nome_completo") or ""} for p in _mencionaveis(supabase, demanda)
        ],
    }


@router.post(
    "/chat/{demanda_id}/conversa",
    response_model=MensagemDaConversaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def escrever_na_conversa_da_demanda(
    demanda_id: str,
    payload: MensagemDaConversaPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Uma mensagem na Conversa da Demanda. Escreve quem ve a Demanda. Nada
    daqui vai para o GitHub (ADR 0083, decisao 8)."""
    demanda = _demanda_visivel(supabase, demanda_id, ator)
    texto = payload.texto.strip()
    if not texto:
        _recusar("Escreva a mensagem antes de enviar.")
    mencoes = extrair_mencoes(texto, _mencionaveis(supabase, demanda))
    ja_escreveram = [
        str(m["autor_id"])
        for m in (
            supabase.table(TABELA_CONVERSA_DA_DEMANDA).select("autor_id").eq("demanda_id", demanda_id).execute().data
            or []
        )
        if m.get("autor_id")
    ]
    [linha] = (
        supabase.table(TABELA_CONVERSA_DA_DEMANDA)
        .insert({"demanda_id": demanda_id, "autor_id": ator["id"], "texto": texto, "mencoes": mencoes})
        .execute()
        .data
    )
    nome = ator.get("nome_completo") or ""
    for destinatario in quem_avisar(demanda, autor_id=ator["id"], mencoes=mencoes, ja_escreveram=ja_escreveram):
        aviso = f"{nome} mencionou você" if destinatario in mencoes else f"{nome} escreveu na Demanda"
        criar_notificacao_tecnologia(
            supabase,
            destinatario_id=destinatario,
            titulo=aviso,
            mensagem=str(demanda.get("titulo") or "")[:80],
            demanda_id=demanda_id,
        )
        # O mesmo aviso, por e-mail (issue #1538): o diretor não fica com o app aberto.
        tecnologia_email.enviar_aviso_da_conversa(
            supabase, destinatario_id=destinatario, aviso=aviso, autor_nome=nome, demanda=demanda
        )
    return _mensagem_para_a_tela(linha, nomes={str(ator["id"]): nome}, ator=ator)


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
    documentos = _documentos_da_fala(supabase, demanda_id=demanda_id, ids=payload.documentos, ator=ator)

    if na_melhoria:
        return await _turno_da_melhoria(
            supabase,
            demanda=demanda,
            atual=atual,
            payload=payload,
            ator=ator,
            depois_do_fim=depois_do_fim,
            documentos=documentos,
        )
    texto = (payload.texto or "").strip()
    if texto or documentos:
        mensagens.append(_respondido_por(chat_tecnologia.fala_do_diretor(texto, documentos), ator))
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
        aviso = _prints_do_turno(
            supabase, demanda=demanda, print_ids=payload.prints, ator=ator, documento_ids=payload.documentos
        )
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
    aviso = _prints_do_turno(
        supabase, demanda=demanda, print_ids=payload.prints, ator=ator, documento_ids=payload.documentos
    )
    return _chat_para_a_tela(supabase, demanda_id, linha, aviso_dos_anexos=aviso)


MOTIVO_CHAT_SEM_RESUMO = "Ainda não há resumo para virar card. Responda às perguntas até o resumo aparecer."


@router.post("/chat/{demanda_id}/nao-bateu", response_model=ChatResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def resumo_do_chat_nao_bateu(
    request: Request,
    demanda_id: str,
    payload: ChatNaoBateuPayload,
    ator: dict = Depends(require_super_admin),
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
            "mensagens": [
                *(atual.get("mensagens") or []),
                _respondido_por({"tipo": "nao_bateu", "texto": texto}, ator),
            ],
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
    payload: CriarOCardPayload | None = None,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Criar o card" do resumo (ADR 0077, decisoes 6 e 7).

    Pela porta unica do envio (`_enviar`, issue #1535): a vez de criar, a peneira no
    titulo, o Vinculo e a Etapa. O que e do bug entra por parametro: o corpo
    com os rotulos do roteiro e os criterios de aceite e as labels que fazem a
    onda pegar sozinha (`ready-for-agent`, sem `needs-triage`). A melhoria leva
    o PRD do diretor. Nos dois, o assignee e o Responsavel escolhido no "Quem
    cuida disto?", ou o dono da configuracao sem escolha (ADR 0083, decisao 5).

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
    assignees, responsavel_id = _responsavel_do_card(supabase, payload.responsavel_id if payload else None)
    return _enviar_o_card(
        supabase, demanda=demanda, atual=atual, ator=ator, assignees=assignees, responsavel_id=responsavel_id
    )


MOTIVO_SEM_ENVIO_FALHOU = "Este card não está com o envio falhado. Recarregue a página."


@router.post("/chat/{demanda_id}/reenviar", response_model=ChatResponse)
@limiter.shared_limit(LIMITE_DO_VINCULO, ESCOPO_DO_VINCULO)
async def reenviar_o_card(
    request: Request,
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Reenviar" da Demanda em "Envio falhou" (issue #1535, ADR 0083, decisao 7).

    Pelo autor ou pelo Desenvolvedor: quem nao ve a Demanda leva 404, como na
    leitura. Passa pela mesma porta do "Criar o card", com o Responsavel que
    ficou guardado no primeiro clique. Antes, confere se a Demanda ja tem issue
    vinculada, e nesse caso nao cria a segunda. Nada reenvia sozinho.
    """
    demanda, atual = _chat_guardado(supabase, demanda_id)
    if not pode_ver(ator, demanda):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MOTIVO_CHAT_NAO_ENCONTRADO)
    if demanda.get("github_issue_numero"):
        _conflito(MOTIVO_CHAT_TERMINOU)
    if not tecnologia_envio.envio_falhou(demanda):
        _conflito(MOTIVO_SEM_ENVIO_FALHOU)
    if atual.get("estado") != planejamento_demanda.ESTADO_RESUMIDO or not atual.get("resumo"):
        _conflito(MOTIVO_CHAT_SEM_RESUMO)
    assignees, responsavel_id = _responsavel_do_card(supabase, demanda.get("responsavel_id"), guardado=True)
    return _enviar_o_card(
        supabase, demanda=demanda, atual=atual, ator=ator, assignees=assignees, responsavel_id=responsavel_id
    )


MOTIVO_SEM_DESIGNACAO_FALHOU = "Este card não está com a designação falhada. Recarregue a página."
MOTIVO_SEM_LOGIN_PARA_DESIGNAR = "O Responsável deste card não tem login do GitHub no cadastro."


@router.post("/chat/{demanda_id}/designar-de-novo", response_model=DemandaResponse)
@limiter.shared_limit(LIMITE_DO_VINCULO, ESCOPO_DO_VINCULO)
async def designar_de_novo(
    request: Request,
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Designar de novo" da issue que nasceu sem o Responsavel (issue #1536,
    ADR 0083, decisao 7).

    So o Desenvolvedor: para o diretor a rota responde como inexistente, porque
    a designacao falhada nem aparece para ele. Pede ao GitHub so a designacao,
    com o login do Responsavel que ficou na Demanda, sem criar issue nenhuma. A
    designacao que pega limpa o estado; a que falha de novo sai como 502 e
    guarda o motivo novo.
    """
    if not e_desenvolvedor(ator):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MOTIVO_CHAT_NAO_ENCONTRADO)
    demanda = _buscar_demanda(supabase, demanda_id)
    if not tecnologia_envio.designacao_falhou(demanda):
        _conflito(MOTIVO_SEM_DESIGNACAO_FALHOU)
    logins, responsavel_id = _responsavel_do_card(supabase, demanda.get("responsavel_id"), guardado=True)
    if not logins:
        _conflito(MOTIVO_SEM_LOGIN_PARA_DESIGNAR)
    _exigir_integracao()
    try:
        github_client.designar(int(demanda["github_issue_numero"]), logins)
    except (github_client.GithubIndisponivelError, github_client.GithubNaoConfiguradoError) as exc:
        supabase.table(TABELA_DEMANDAS).update({"envio_motivo": str(exc), "envio_em": _agora()}).eq(
            "id", demanda_id
        ).execute()
        _issue_indisponivel()
    result = (
        supabase.table(TABELA_DEMANDAS)
        .update({"envio_estado": None, "envio_motivo": None, "envio_em": _agora(), "responsavel_id": responsavel_id})
        .eq("id", demanda_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")
    return _para_a_lista(supabase, result.data, ator=ator)[0]


MOTIVO_APAGAR_GITHUB_FALHOU = (
    "O GitHub não respondeu, e o card não foi fechado lá. Nada foi apagado: tente de novo em instantes."
)


@router.delete("/chat/{demanda_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.shared_limit(LIMITE_DO_VINCULO, ESCOPO_DO_VINCULO)
async def apagar_a_demanda(
    request: Request,
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Apagar" da Demanda (issue #1549, ADR 0084, decisao 2).

    Quem pode e ate onde e a `recusa_de_apagar`: o autor apaga a conversa
    Registrada; o card criado, so o Desenvolvedor, ate Planejada. A recusa
    sai com o status dela (403 ou 409). O card fecha antes no GitHub, e a
    falha de la sai como 503 (falta configuracao) ou 502, sem nada apagado no
    app.
    """
    demanda = _buscar_demanda(supabase, demanda_id)
    recusa = recusa_de_apagar(ator, demanda)
    if recusa is not None:
        raise HTTPException(status_code=recusa[0], detail=recusa[1])
    if demanda.get("github_issue_numero"):
        _exigir_integracao()
    try:
        tecnologia_apagar.apagar(supabase, demanda, ator=ator)
    except github_client.GithubNaoConfiguradoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MOTIVO_INTEGRACAO_DESLIGADA
        ) from None
    except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
        logger.warning("[tecnologia] o card da Demanda %s não fechou no GitHub: %s", demanda_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MOTIVO_APAGAR_GITHUB_FALHOU) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── A Revisao com o codigo de hoje (issue #1557, ADR 0084, decisao 3) ──────

MOTIVO_REVISAO_SEM_CONVERSA = "Este pedido já está em revisão, ou não tem conversa para retomar. Recarregue a página."
MOTIVO_REVISAO_SEM_CONFIRMACAO = "Confirme a revisão para a IA começar."
MOTIVO_REVISAO_GITHUB_FALHOU = (
    "O desenvolvimento não respondeu, e a revisão não começou. Nada foi cobrado: tente de novo em instantes."
)


def _revisao_permitida(supabase: Client, demanda_id: str, ator: dict) -> tuple[dict, dict]:
    """A Demanda e a conversa que se revisam, ou a recusa: 404 para quem nao a
    ve, a `recusa_de_revisar` (403 ou 409), e 409 sem a conversa da melhoria
    ja enviada para retomar."""
    demanda = _demanda_visivel(supabase, demanda_id, ator)
    recusa = recusa_de_revisar(ator, demanda)
    if recusa is not None:
        raise HTTPException(status_code=recusa[0], detail=recusa[1])
    linha = planejamento_demanda.ler(supabase, demanda_id)
    mensagens = (linha or {}).get("mensagens") or []
    if (
        not chat_tecnologia.e_do_chat(linha)
        or not chat_tecnologia.em_planejamento(mensagens)
        or linha.get("estado") != planejamento_demanda.ESTADO_ENVIADO
    ):
        _conflito(MOTIVO_REVISAO_SEM_CONVERSA)
    return demanda, linha


def _tamanho_do_pedido(demanda: dict, linha: dict) -> int:
    """O tamanho da conversa e do PRD, em caracteres, para a estimativa. O PRD
    do diretor sai do resumo e da descricao, que e de onde o card nasceu."""
    mensagens = linha.get("mensagens") or []
    _, planejamento = chat_tecnologia.partes_da_melhoria(mensagens)
    conversa = planejamento_demanda.pedido_do_turno(
        chat_tecnologia.demanda_da_melhoria(mensagens, demanda_id=str(demanda["id"]), titulo=demanda.get("titulo")),
        planejamento,
    )
    return len(conversa) + len(json.dumps(linha.get("resumo") or {}, ensure_ascii=False))


@router.get("/chat/{demanda_id}/revisao", response_model=EstimativaDaRevisao)
async def estimar_a_revisao(
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """A estimativa do diálogo de confirmação (ADR 0082): a faixa em dólar do
    Retrato de hoje, pelo tamanho da conversa e do PRD e pelo preço do modelo
    do planejamento. Só conta: nenhuma IA e nenhum GitHub."""
    demanda, linha = _revisao_permitida(supabase, demanda_id, ator)
    return tecnologia_revisao.estimativa(caracteres=_tamanho_do_pedido(demanda, linha), kit=carregar_kit())


@router.post("/chat/{demanda_id}/revisao", response_model=ChatResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def revisar_com_o_codigo_de_hoje(
    request: Request,
    demanda_id: str,
    payload: RevisarPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Revisar com o código de hoje" confirmado (ADR 0084, decisão 3).

    Sem `confirmado`, 422 antes de qualquer leitura: a IA só roda depois do
    clique em Confirmar (ADR 0082). Confirmado, lê do GitHub o card, os
    comentários e o `history.json`, e o primeiro turno é o Retrato de hoje. A
    mesma conversa volta a em andamento com a marca da revisão (quando, por
    quem, a versão de base) e, se há item em Já existe, com o primeiro "isso
    atende?"; sem item, com a primeira pergunta pelas lacunas. Falha do
    GitHub ou do Retrato devolve 502 com a conversa como estava.
    """
    demanda, atual = _revisao_permitida(supabase, demanda_id, ator)
    if not payload.confirmado:
        _recusar(MOTIVO_REVISAO_SEM_CONFIRMACAO)
    _exigir_integracao()
    numero = int(demanda["github_issue_numero"])
    try:
        issue = github_client.ler_issue(numero)
        comentarios = github_client.ler_comentarios(numero)
        historico = github_client.ler_historico_de_deploys()
    except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
        logger.warning("[tecnologia] a revisão da Demanda %s não leu o GitHub: %s", demanda_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MOTIVO_REVISAO_GITHUB_FALHOU) from None
    data_do_card = instante_do_banco(issue.get("created_at")) or instante_do_banco(demanda.get("criado_em"))

    mensagens = list(atual.get("mensagens") or [])
    _, planejamento = chat_tecnologia.partes_da_melhoria(mensagens)
    resultado = await ai_processor.chamar_ia_fora_do_loop(
        tecnologia_revisao.retrato_de_hoje,
        demanda=chat_tecnologia.demanda_da_melhoria(mensagens, demanda_id=demanda_id, titulo=demanda.get("titulo")),
        mensagens=planejamento,
        kit=carregar_kit(),
        corpo_da_issue=str(issue.get("body") or ""),
        comentarios=comentarios,
        subidas=tecnologia_revisao.subidas_desde(historico, data_do_card),
        data_do_card=data_do_card,
    )
    if resultado.chamada is not None:
        planejamento_demanda.gravar_chamada(supabase, resultado.chamada)
    if resultado.erro:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resultado.erro)

    mensagens.append(resultado.mensagem)
    atende = tecnologia_revisao.proxima_pergunta_de_atende(mensagens)
    estado = planejamento_demanda.ESTADO_EM_ANDAMENTO
    do_turno: dict = {}
    if atende is not None:
        mensagens.append(atende)
    else:
        # Sem item em Ja existe nao ha "isso atende?": a primeira pergunta
        # pelas lacunas vem no mesmo clique, senao a conversa para no retrato.
        # Se ela falhar, o retrato ja cobrado fica e a tela pede de novo.
        turno = await ai_processor.chamar_ia_fora_do_loop(
            chat_tecnologia.turno_da_melhoria,
            mensagens=mensagens,
            kit=carregar_kit(),
            demanda_id=demanda_id,
            titulo=demanda.get("titulo"),
        )
        if turno.chamada is not None:
            planejamento_demanda.gravar_chamada(supabase, turno.chamada)
        if not turno.erro:
            mensagens.append(turno.mensagem)
            estado = _estado_do_planejamento(turno.mensagem)
            do_turno = {
                **_rascunho_do_documento(turno),
                **({"decisoes": [*(atual.get("decisoes") or []), turno.decisao]} if turno.decisao else {}),
            }
    linha = planejamento_demanda.gravar(
        supabase,
        demanda_id,
        atual=atual,
        novo={
            "estado": estado,
            **do_turno,
            "mensagens": mensagens,
            "revisao_iniciada_em": _agora(),
            "revisao_por": ator["id"],
            "revisao_versao_base": tecnologia_revisao.versao(settings.app_version),
            "atualizado_em": _agora(),
        },
    )
    if linha is None:
        _conflito(MOTIVO_CHAT_MUDOU)
    return _chat_para_a_tela(supabase, demanda_id, linha)


# ─── O "Atualizar o card" da revisao (issue #1558, ADR 0084, decisao 3) ─────

MOTIVO_ATUALIZAR_SEM_REVISAO = "Este pedido não está em revisão. Recarregue a página."
MOTIVO_ATUALIZAR_GITHUB_FALHOU = (
    "O desenvolvimento não respondeu, e o card não foi atualizado. Nada mudou aqui: tente de novo em instantes."
)


@router.post("/chat/{demanda_id}/atualizar-card", response_model=ChatResponse)
@limiter.shared_limit(LIMITE_DO_VINCULO, ESCOPO_DO_VINCULO)
async def atualizar_o_card(
    request: Request,
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O "Atualizar o card" no fim da revisão (ADR 0084, decisão 3).

    Quem pode é a `recusa_de_revisar`, e a conversa tem de estar em revisão,
    com o resumo refeito. No GitHub, pela ordem: o comentário do que entrou e
    do que saiu, as partes não começadas fechadas como não planejadas, e o
    corpo regravado com o marcador da Demanda intacto e a raiz de volta em
    `needs-triage`. Parte em desenvolvimento recusa com 409 antes de qualquer
    escrita. Só depois do GitHub o app grava: a conversa volta a enviada e a
    Etapa é relida. Falha do GitHub sai como 502, com nada gravado no app.
    """
    demanda = _demanda_visivel(supabase, demanda_id, ator)
    recusa = recusa_de_revisar(ator, demanda)
    if recusa is not None:
        raise HTTPException(status_code=recusa[0], detail=recusa[1])
    atual = planejamento_demanda.ler(supabase, demanda_id) or {}
    if not atual.get("revisao_iniciada_em") or atual.get("estado") == planejamento_demanda.ESTADO_ENVIADO:
        _conflito(MOTIVO_ATUALIZAR_SEM_REVISAO)
    if atual.get("estado") != planejamento_demanda.ESTADO_RESUMIDO or not atual.get("resumo"):
        _conflito(MOTIVO_CHAT_SEM_RESUMO)
    _exigir_integracao()

    _, planejamento = chat_tecnologia.partes_da_melhoria(atual.get("mensagens") or [])
    corpo_novo = _corpo_do_prd(supabase, demanda=demanda, atual=atual, titulo=titulo_da_issue(demanda.get("titulo")))
    try:
        tecnologia_revisao.atualizar_no_github(
            int(demanda["github_issue_numero"]),
            demanda_id=demanda_id,
            corpo_novo=corpo_novo,
            saiu_por_atender=(tecnologia_revisao.escopo(planejamento) or {}).get("saiu") or [],
            versao_base=atual.get("revisao_versao_base"),
        )
    except tecnologia_revisao.ParteJaComecouError:
        _conflito(MOTIVO_REVISAR_JA_COMECOU)
    except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
        logger.warning("[tecnologia] o card da Demanda %s não foi atualizado no GitHub: %s", demanda_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MOTIVO_ATUALIZAR_GITHUB_FALHOU) from None

    linha = planejamento_demanda.marcar_enviado(supabase, demanda_id, agora=_agora())
    try:
        # A Etapa e lida de novo do GitHub, como no webhook: o card volta a Em
        # analise. Falha aqui nao desfaz o que o GitHub ja gravou; o webhook
        # da raiz regravada e a reconciliacao acertam a Etapa depois.
        tecnologia_sincronizacao.sincronizar_demanda(supabase, _buscar_demanda(supabase, demanda_id))
    except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
        logger.warning("[tecnologia] a Etapa da Demanda %s não foi relida depois do Atualizar: %s", demanda_id, exc)
    return _chat_para_a_tela(supabase, demanda_id, linha or {**atual, "estado": planejamento_demanda.ESTADO_ENVIADO})


def _corpo_do_prd(supabase: Client, *, demanda: dict, atual: dict, titulo: str) -> str:
    """O PRD do diretor que vai a issue, no "Criar o card" e no "Atualizar o
    card" da revisao: o resumo, o documento vivo e so a contagem dos anexos
    (ADR 0069), por tipo (issue #1520)."""
    demanda_id = str(demanda["id"])
    imagens, documentos = tecnologia_anexos.quantos_guardados(supabase, demanda_id)
    return corpo_do_prd_do_diretor(
        demanda_id=demanda_id,
        titulo=titulo,
        descricao=demanda.get("descricao"),
        resumo=atual.get("resumo"),
        link=link_da_demanda(demanda_id),
        anexos=imagens,
        documentos=documentos,
        documento=atual.get("documento"),
    )


def _enviar_o_card(
    supabase: Client,
    *,
    demanda: dict,
    atual: dict,
    ator: dict,
    assignees: list[str],
    responsavel_id: str | None,
) -> dict:
    """O envio do card, igual para "Criar o card" e "Reenviar" (issue #1535).

    Recebe as guardas da rota ja passadas e o Responsavel ja resolvido. O que
    e do bug entra por parametro na porta: o corpo com os rotulos do roteiro e
    os criterios de aceite e as labels que fazem a onda pegar sozinha
    (`ready-for-agent`, sem `needs-triage`). A melhoria leva o PRD do diretor.
    """
    demanda_id = str(demanda["id"])
    resumo = atual.get("resumo")
    _exigir_integracao()

    if chat_tecnologia.em_planejamento(atual.get("mensagens") or []):
        # A melhoria (issue #1383): o PRD do diretor, que nasce na triagem
        # (`needs-triage` e `type:feature`) porque ainda passa pelo
        # `/to-issues`, atribuido ao Responsavel.
        _enviar(
            supabase,
            demanda=demanda,
            ator=ator,
            corpo=lambda titulo: _corpo_do_prd(supabase, demanda=demanda, atual=atual, titulo=titulo),
            assignees=assignees,
            labels=[*labels_da_issue_nova(chat_tecnologia.TIPO_DA_CLASSIFICACAO["melhoria"]), LABEL_ORIGEM_DIRETOR],
            responsavel_id=responsavel_id,
        )
        linha = planejamento_demanda.marcar_enviado(supabase, demanda_id, agora=_agora())
        return _chat_para_a_tela(
            supabase, demanda_id, linha or {**atual, "estado": planejamento_demanda.ESTADO_ENVIADO}
        )

    produtos = supabase.table(TABELA_PRODUTOS).select("id, nome").eq("id", demanda.get("produto_id")).execute()
    produto_nome = (produtos.data or [{}])[0].get("nome") or SEM_PRODUTO
    # So a contagem dos anexos vai a issue (ADR 0069), por tipo (issue #1520).
    imagens, documentos = tecnologia_anexos.quantos_guardados(supabase, demanda_id)

    def corpo(_titulo: str) -> str:
        return corpo_da_issue_do_bug(
            demanda_id=demanda_id,
            resumo=resumo,
            produto_nome=produto_nome,
            link=link_da_demanda(demanda_id),
            anexos=imagens,
            documentos=documentos,
        )

    _enviar(
        supabase,
        demanda=demanda,
        ator=ator,
        corpo=corpo,
        assignees=assignees,
        labels=[*LABELS_DO_BUG, LABEL_ORIGEM_DIRETOR],
        responsavel_id=responsavel_id,
    )
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


@router.post("/assistente/ler-documento", response_model=AssistenteDocumentoResponse)
@limiter.limit(LIMITE_DO_ASSISTENTE)
async def assistente_ler_documento(
    request: Request,
    documento: UploadFile = File(...),
    _ator: dict = Depends(require_super_admin),
):
    """O documento anexado no chat vira texto (issue #1520, ADR 0069).

    Irma da rota do print, sem IA: o texto sai do extrator da Ata Guiada, com
    o parser em processo isolado (issue #758). Os bytes e o texto ficam so na
    memoria, com o identificador efemero que a tela leva na fala do chat; o
    original vira Anexo quando a fala entra na conversa. O texto NAO sai daqui:
    a tela mostra o nome e o tamanho, e o agente le o texto pela fala.

    O tipo vem da EXTENSAO, e nunca do `content-type` do cliente (ADR 0034), e
    a recusa do tipo vem antes de ler os bytes.
    """
    nome = documento.filename or ""
    try:
        extensao = tecnologia_anexos.extensao_do_documento(nome)
        conteudo = await documento.read()
        texto = await tecnologia_anexos.texto_do_documento(nome=nome, conteudo=conteudo)
    except tecnologia_anexos.AnexoRecusadoError as recusa:
        raise HTTPException(status_code=recusa.status_code, detail=str(recusa)) from recusa

    logger.info(f"Documento lido no chat por {_ator['id']}: {extensao}, {len(texto)} chars")
    documento_id = tecnologia_anexos.guardar_documento(quem_id=_ator["id"], nome=nome, conteudo=conteudo, texto=texto)
    return {"documento_id": documento_id, "nome": nome, "tamanho_bytes": len(conteudo), "caracteres": len(texto)}
