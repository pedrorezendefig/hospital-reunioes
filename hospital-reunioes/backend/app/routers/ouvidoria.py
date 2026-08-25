"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. O painel lista o
índice para toda a equipe e abre o Dossiê só para a Ouvidoria (ADR 0034).

Desde a issue #321 a Manifestação também nasce aqui: o ouvidor registra o que
chegou por telefone, balcão ou email, com a data e hora reais do contato.
"""

import datetime as dt
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from supabase import Client

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO_TUPLA
from app.services import ouvidoria_notificacoes, ouvidoria_prorrogacao, storage
from app.services.ouvidoria_anexos import (
    AnexoGrandeDemaisError,
    AnexoRecusadoError,
    TipoNaoPermitidoError,
    validar_anexo,
)
from app.services.ouvidoria_estados import (
    DadosInsuficientesError,
    TransicaoInvalidaError,
    validar_transicao,
)
from app.services.ouvidoria_prazos import (
    TETO_PRORROGACAO_DIAS_UTEIS,
    Prazo,
    calcular_vencimento,
    cumprimento_da_area,
    esta_vencido,
    minutos_uteis_entre,
    rotular_vencimento,
    vencimento_prorrogado,
)
from app.services.ouvidoria_responsaveis import escolher_destinatario
from app.utils.text_sanitizer import sanitizar_travessao

# O T0 é hora de relógio de parede do hospital: o ouvidor digita "14/08 16h50"
# pensando em Brasília, e a persistência é em UTC.
FUSO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Folga para relógio de máquina adiantado, ao recusar contato "no futuro".
TOLERANCIA_RELOGIO = timedelta(minutes=5)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria"])


def agora_utc() -> dt.datetime:
    """O relógio do módulo, num ponto só. Prazo, janela comercial e marco T1
    precisam enxergar o MESMO instante dentro de uma validação: lidos em
    chamadas diferentes, o email poderia dizer um vencimento e o banco guardar
    outro."""
    return dt.datetime.now(dt.UTC)


async def require_acesso_painel(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do painel: quem tem papel no contexto Reuniões (facilitador,
    secretária, super admin) mais quem tem papel na Ouvidoria. O ouvidor pode
    não participar de Reuniões nenhuma e ainda assim é o dono desta tela.

    Devolve o participante: a listagem decide o que mostrar pelo perfil."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or not (tem_acesso_reunioes(me) or tem_perfil_ouvidoria(me)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à equipe de Reuniões",
        )
    return me


# Índice do painel: os campos da API da Ana mais o prazo do motor novo. Fica
# separado de _CAMPOS_PROTOCOLO_TUPLA de propósito: aquela tupla dimensiona a
# resposta da API da Ana, que tem teto de leitura no cliente (ADR 0032).
# `respondida_em` entra por causa do indicador de cumprimento, que compara o
# marco T2 com o vencimento VIGENTE (prorrogação aprovada já mexeu nele).
_CAMPOS_INDICE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + ("gravidade", "prazo_area_em", "respondida_em")
_CAMPOS_INDICE = ", ".join(_CAMPOS_INDICE_TUPLA)


def carregar_feriados(supabase) -> frozenset[dt.date]:
    """Os feriados que o motor precisa (RN-22). Falha aqui não derruba o
    painel: sem a lista o motor conta feriado como dia útil, o que erra para
    menos (cobra antes), e é melhor que a tela não abrir."""
    try:
        result = supabase.table("ouvidoria_feriados").select("data").execute()
        # A conversão entra no try junto da leitura: uma data malformada não
        # pode derrubar o painel inteiro, que é o que a promessa acima diz.
        return frozenset(dt.date.fromisoformat(str(row["data"])) for row in (result.data or []) if row.get("data"))
    except Exception:
        logger.warning("Falha ao carregar feriados: o calendário útil vai contar sem eles")
        return frozenset()


def _projetar_prazo(row: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> dict:
    """Traduz o vencimento persistido no que a tela precisa mostrar. O prazo é
    lido, nunca recalculado: caso já despachado mantém o que o setor recebeu.

    `minutos_uteis_restantes` sai daqui porque o destaque visual precisa da
    mesma régua do rótulo: medir a proximidade em dias corridos no navegador
    apagaria o alerta justo quando o vencimento atravessa fim de semana."""
    bruto = row.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    estourado = esta_vencido(vencimento, agora)
    if vencimento is None or estourado:
        restantes = None if vencimento is None else 0
    else:
        restantes = minutos_uteis_entre(agora, vencimento, feriados)
    respondida = row.get("respondida_em")
    return {
        "rotulo_prazo": rotular_vencimento(vencimento, agora, feriados),
        "prazo_estourado": estourado,
        "minutos_uteis_restantes": restantes,
        # O indicador de prazo da área (PRD #318, história 5). A régua é o
        # vencimento vigente, então prorrogação aprovada conta como cumprido
        # sem nenhum caso especial aqui.
        "cumprimento": cumprimento_da_area(
            vencimento,
            dt.datetime.fromisoformat(str(respondida)) if respondida else None,
            agora,
        ),
    }


@router.get("/protocolos")
@limiter.limit("60/minute")
async def listar_protocolos(
    request: Request,
    me: dict = Depends(require_acesso_painel),
    supabase=Depends(get_supabase_client),
):
    """Todos os protocolos, mais recentes primeiro, com prazo e status.

    Índice, não Dossiê: agora que a tabela guarda relato e identificação
    (ADR 0034), a resposta é fechada no índice campo a campo, e não no que o
    select devolveu."""
    # sigilo_reforcado entra no select mas não na resposta: é a coluna que
    # decide o filtro abaixo, e o índice segue fechado em _CAMPOS_INDICE.
    query = (
        supabase.table("ouvidoria_protocolos").select(f"{_CAMPOS_INDICE}, sigilo_reforcado").order("numero", desc=True)
    )
    # Sigilo reforçado (RN-40): o resumo de uma denúncia já identifica quem
    # relatou, então a sigilosa não entra nem no índice de quem está fora da
    # Ouvidoria, super admin incluído. O filtro vive na query (a linha nem sai
    # do banco) e de novo em Python, caso a coluna volte nula por engano.
    if not tem_perfil_ouvidoria(me):
        query = query.eq("sigilo_reforcado", False)
    result = query.execute()
    linhas = result.data or []
    if not tem_perfil_ouvidoria(me):
        linhas = [row for row in linhas if not row.get("sigilo_reforcado")]

    # O rótulo é calculado no servidor, uma vez por carga, com o mesmo motor
    # que o email do setor usa: painel e email nunca dizem prazos diferentes.
    # O calendário só é lido se houver prazo para contar.
    feriados = carregar_feriados(supabase) if any(row.get("prazo_area_em") for row in linhas) else frozenset()
    # Pelo relógio do módulo, como o resto do painel: rótulo de prazo e
    # indicador de cumprimento saem da MESMA leitura do relógio em toda rota.
    agora = agora_utc()
    return {
        "protocolos": [
            {campo: row.get(campo) for campo in _CAMPOS_INDICE_TUPLA} | _projetar_prazo(row, agora, feriados)
            for row in linhas
        ]
    }


# Dossiê completo (ADR 0034, decisão 1): o índice mais o que só ouvidor e
# diretoria executiva podem ler.
_CAMPOS_DOSSIE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + (
    "relato_integral",
    "manifestante_nome",
    "manifestante_contato",
    "manifestante_vinculo",
    "anonimo",
    "sigilo_reforcado",
    "dados_incompletos",
    "classificacao_ia",
    "desfecho",
    "desfecho_descricao",
    "canal",
    "contato_em",
    "gravidade",
    "prazo_area_em",
    "prazo_rompido_em",
    "validada_em",
    "validada_por",
    "respondida_em",
    "resposta_da_area",
    "respondida_por_nome",
    "encerrada_em",
)
_CAMPOS_DOSSIE = ", ".join(_CAMPOS_DOSSIE_TUPLA)

PERFIS_OUVIDORIA = ("ouvidor", "diretoria_executiva")


def tem_perfil_ouvidoria(participante: dict | None) -> bool:
    """Quem lê o Dossiê (ADR 0034, decisão 8): só os dois perfis do contexto
    Ouvidoria. Papel nas Reuniões, inclusive super admin, não concede."""
    return bool(participante) and participante.get("perfil_ouvidoria") in PERFIS_OUVIDORIA


async def require_perfil_ouvidoria(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do Dossiê. Devolve o participante para a rota decidir sobre sigilo
    e para registrar o log de acesso."""
    me = await get_participante_for_user(current_user, supabase)
    if not tem_perfil_ouvidoria(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à Ouvidoria",
        )
    return me


async def require_diretoria_executiva(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate de quem define os parâmetros do prazo (RN-21). Mais estreito que o
    da Ouvidoria de propósito: o ouvidor trabalha com o prazo, quem o define é
    a Diretoria Executiva."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or me.get("perfil_ouvidoria") != "diretoria_executiva":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Só a Diretoria Executiva altera os parâmetros da Ouvidoria",
        )
    return me


def registrar_acesso(supabase, me: dict, manifestacao_id: str, acao: str) -> None:
    """Grava o log de acesso. Falha aqui não derruba a leitura: a trilha é
    importante, mas deixar o ouvidor sem o Dossiê por causa dela seria pior.
    O timestamp é do banco (`ocorrido_em` tem default now())."""
    try:
        supabase.table("ouvidoria_acessos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "ator_id": me["id"],
                "ator_nome": me.get("nome_completo") or me["id"],
                "acao": acao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao registrar acesso à manifestação %s", manifestacao_id)


class RegistroManual(BaseModel):
    """Manifestação digitada pelo ouvidor (issue #321).

    `contato_em` é o T0: a data e hora em que a manifestação chegou ao
    hospital, não o momento do clique. Sem fuso na entrada, vale o horário de
    Brasília, que é como o ouvidor pensa a hora do telefonema."""

    canal: Literal["telefone", "presencial", "email"]
    contato_em: datetime
    categoria: str
    setor: str
    resumo: str
    relato_integral: str
    manifestante_nome: str | None = None
    manifestante_contato: str | None = None
    manifestante_vinculo: Literal["paciente", "acompanhante", "colaborador", "terceiro", "outro"] | None = None
    anonimo: bool = False
    sigilo_reforcado: bool = False

    @field_validator("categoria", "setor", "resumo", "relato_integral")
    @classmethod
    def campo_critico_nao_vazio(cls, valor: str) -> str:
        # Tipografia sanitizada antes da validação (ADR 0013): o texto aparece
        # no painel e nos emails ao setor.
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo crítico não pode ser vazio")
        return valor

    @field_validator("manifestante_nome", "manifestante_contato")
    @classmethod
    def identificacao_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = sanitizar_travessao(valor).strip()
        return valor or None

    @field_validator("contato_em")
    @classmethod
    def contato_nao_pode_ser_no_futuro(cls, valor: datetime) -> datetime:
        # Retroativo é o caso normal; futuro seria erro de digitação que
        # empurraria o prazo do setor para frente sem ninguém perceber.
        #
        # A folga existe porque o campo já vem preenchido com o relógio do
        # navegador: uns minutos adiantados no computador do balcão não podem
        # recusar o valor que a própria tela sugeriu.
        instante = valor.replace(tzinfo=FUSO_HOSPITAL) if valor.tzinfo is None else valor
        if instante > datetime.now(tz=FUSO_HOSPITAL) + TOLERANCIA_RELOGIO:
            raise ValueError("a data e hora do contato não podem estar no futuro")
        return instante


# Denúncia e relato de conduta nascem sigilosos (ADR 0034, decisão 1): a regra
# olha a categoria digitada, sem acento e sem caixa, porque quem digita escreve
# "Denúncia", "denuncia" ou "Relato de conduta".
#
# "conduta" sozinha ficou de fora de propósito: o sigiloso some do índice de
# todos que estão fora da Ouvidoria, e "Elogio pela conduta da equipe" viraria
# um caso invisível sem ninguém ter pedido. O gesto de esconder é sempre a
# palavra inteira "denuncia" ou a expressão "relato de conduta"; para o resto,
# o ouvidor marca o sigilo na mão.
_CATEGORIAS_SIGILOSAS = ("denuncia", "relato de conduta")


def nasce_sigilosa(categoria: str) -> bool:
    """Se a categoria é denúncia ou relato de conduta, o sigilo não é opção do
    ouvidor: vem junto."""
    sem_acento = unicodedata.normalize("NFKD", categoria).encode("ascii", "ignore").decode()
    return any(termo in sem_acento.lower() for termo in _CATEGORIAS_SIGILOSAS)


@router.post("/manifestacoes", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def registrar_manifestacao(
    request: Request,
    registro: RegistroManual,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação que chegou por telefone, balcão ou email.

    A abertura acompanha o T0 informado (e não o dia da digitação), então o
    protocolo e o prazo saem do momento real do contato. O número `ANO-NNNN` é
    do banco, como sempre: a aplicação nunca o compõe."""
    anonimo = registro.anonimo
    # Anônimo é escolha de quem manifesta, e ela vale contra o que veio no
    # corpo: nome e contato não são gravados, ponto.
    nome = None if anonimo else registro.manifestante_nome
    contato = None if anonimo else registro.manifestante_contato

    linha = {
        "canal": registro.canal,
        "contato_em": registro.contato_em.isoformat(),
        "data_abertura": registro.contato_em.astimezone(FUSO_HOSPITAL).date().isoformat(),
        "categoria": registro.categoria,
        "setor": registro.setor,
        "resumo": registro.resumo,
        "relato_integral": registro.relato_integral,
        "manifestante_nome": nome,
        "manifestante_contato": contato,
        "manifestante_vinculo": None if anonimo else registro.manifestante_vinculo,
        "anonimo": anonimo,
        "sigilo_reforcado": registro.sigilo_reforcado or nasce_sigilosa(registro.categoria),
        # O ouvidor preencheu o formulário inteiro: só fica incompleta a que se
        # identificou pela metade (dá nome mas não deixa como responder).
        "dados_incompletos": not anonimo and not (nome and contato),
        "registrado_por": me["id"],
    }

    try:
        result = supabase.table("ouvidoria_protocolos").insert(linha).execute()
    except APIError as exc:
        logger.error("Falha ao registrar manifestação manual (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar a manifestação",
        ) from exc
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar a manifestação",
        )

    row = result.data[0]
    registrar_movimento_de_abertura(supabase, me, row, registro.canal)
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


def registrar_movimento_de_abertura(supabase, me: dict, row: dict, canal: str) -> None:
    """Abre a trilha do caso: o primeiro movimento é o nascimento dele.

    Falha aqui não desfaz o registro (o protocolo já foi dito a quem
    manifestou), mas fica no log para conferência."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": row["id"],
                "estado_anterior": None,
                "estado_novo": row.get("status") or "em_classificacao",
                "autor_id": me["id"],
                "autor_nome": me.get("nome_completo") or me["id"],
                "observacao": f"Registro manual da ouvidoria (canal: {canal})",
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de abertura da manifestação %s", row.get("id"))


@router.get("/manifestacoes/{manifestacao_id}")
@limiter.limit("60/minute")
async def abrir_manifestacao(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Abre o Dossiê completo de uma manifestação."""
    try:
        result = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    row = result.data[0]
    registrar_acesso(supabase, me, manifestacao_id, "abrir_dossie")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


class PedidoTransicao(BaseModel):
    """Pedido de mudança de estado. `desfecho` e `desfecho_descricao` só fazem
    sentido no encerramento, e lá são obrigatórios."""

    estado: Literal["em_classificacao", "aguardando_area", "respondido", "encerrado"]
    observacao: str | None = None
    desfecho: str | None = None
    desfecho_descricao: str | None = None


@router.post("/manifestacoes/{manifestacao_id}/transicoes")
@limiter.limit("60/minute")
async def transicionar_manifestacao(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoTransicao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Porta de entrada única da máquina de estados: valida a regra e grava o
    movimento na mesma transação (RPC `ouvidoria_transicionar`).

    A regra é checada aqui para devolver mensagem útil, e de novo no banco,
    para que contornar a API não contorne a máquina de estados."""
    try:
        atual = supabase.table("ouvidoria_protocolos").select("id, status").eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")

    try:
        validar_transicao(
            atual.data[0]["status"],
            pedido.estado,
            desfecho=pedido.desfecho,
            desfecho_descricao=pedido.desfecho_descricao,
        )
    except DadosInsuficientesError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        resultado = supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": pedido.estado,
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": pedido.observacao,
                "p_desfecho": pedido.desfecho,
                "p_desfecho_descricao": pedido.desfecho_descricao,
            },
        ).execute()
    except APIError as exc:
        # A regra também vive no banco: check_violation é corrida com outra
        # transição; o resto é falha real e não pode se disfarçar de 409.
        if exc.code == "23514":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transição recusada") from exc
        if exc.code == "P0002":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
        logger.error("Erro na RPC ouvidoria_transicionar (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao transicionar manifestação",
        ) from exc

    row = resultado.data[0] if isinstance(resultado.data, list) else resultado.data

    # Marco T3 (issue #326): o encerramento fica carimbado no caso, no padrão
    # do T1 (validada_em). Falha aqui não desfaz a transição (o movimento é a
    # fonte da verdade do ato); fica no log para conferência.
    if pedido.estado == "encerrado":
        try:
            carimbo = {"encerrada_em": agora_utc().isoformat()}
            supabase.table("ouvidoria_protocolos").update(carimbo).eq("id", manifestacao_id).execute()
            row.update(carimbo)
        except APIError:
            logger.error("Falha ao carimbar o T3 da manifestação %s", manifestacao_id)

    registrar_acesso(supabase, me, manifestacao_id, "transicionar")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


# =====================================================================
# Validação e acionamento da área (issue #325, ADR 0034 decisões 3, 5 e 7)
# =====================================================================

_CAMPOS_RESPONSAVEL_TUPLA = ("id", "setor", "papel", "nome", "email", "vigencia_inicio", "vigencia_fim")
_CAMPOS_RESPONSAVEL = ", ".join(_CAMPOS_RESPONSAVEL_TUPLA)


class PedidoValidacao(BaseModel):
    """O que o ouvidor confere antes de qualquer setor ser acionado: tipo,
    área e gravidade. Nada disso vem da IA: a sugestão da Ana vive em
    `classificacao_ia` e nunca chega aqui sozinha (ADR 0034, decisão 10).

    `extrato_para_o_setor` é o texto que vai por email ao responsável, escrito
    pelo ouvidor. Obrigatório em todo acionamento: o campo é opcional no schema
    só para a rota poder recusar com uma mensagem que explica o porquê, em vez
    do erro genérico do pydantic."""

    categoria: str
    setor: str
    gravidade: Literal["critico", "alto", "medio", "baixo"]
    observacao: str | None = None
    extrato_para_o_setor: str | None = None

    @field_validator("categoria", "setor")
    @classmethod
    def _classificacao_nao_vazia(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo da classificação não pode ser vazio")
        return valor

    @field_validator("observacao", "extrato_para_o_setor")
    @classmethod
    def _observacao_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None


def extrato_do_acionamento(escrito_pelo_ouvidor: str | None) -> str:
    """O texto que o responsável do setor vai ler no email.

    Obrigatório em todo acionamento, sem exceção (decisão de 25/08). Nem o
    `resumo` nem o relato servem de padrão: os dois carregam a palavra de quem
    manifestou (no canal aberto, o que o cidadão digitou; no canal da Ana, texto
    gerado a partir da conversa com ele), e o responsável do setor é gente de
    fora da Ouvidoria, sem login no app. Uma regra só, sem caso especial para
    alguém lembrar: todo email que sai da Ouvidoria leva texto escrito pela
    Ouvidoria (ADR 0034, decisão 8)."""
    if escrito_pelo_ouvidor:
        return escrito_pelo_ouvidor
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            "O acionamento exige o extrato para o setor. "
            "Escreva com as suas palavras o que a área precisa resolver: o relato original não sai da Ouvidoria."
        ),
    )


def carregar_prazo_da_area(supabase, gravidade: str) -> Prazo:
    """A célula da tabela de prazos que vale para a resposta do setor.

    Célula ausente vira prazo indefinido em vez de erro: a Diretoria pode ter
    esvaziado a linha, e travar a validação por isso deixaria o caso parado na
    fila da ouvidoria, que é pior do que acionar sem contagem regressiva."""
    try:
        result = (
            supabase.table("ouvidoria_prazos")
            .select("valor, unidade")
            .eq("gravidade", gravidade)
            .eq("marco", "area_resposta")
            .execute()
        )
    except Exception:
        logger.warning("Falha ao ler o prazo de %s: o acionamento segue sem vencimento", gravidade)
        return Prazo(valor=None)
    if not result.data:
        return Prazo(valor=None)
    linha = result.data[0]
    return Prazo(valor=linha.get("valor"), unidade=linha.get("unidade") or "dias_uteis")


def carregar_responsaveis(supabase, setor: str) -> list[dict]:
    """O cadastro de quem responde pelo setor. A vigência é filtrada em
    Python, pela função pura, e não na query: a regra de quem responde hoje é
    domínio, não detalhe de SQL."""
    result = supabase.table("ouvidoria_setor_responsaveis").select(_CAMPOS_RESPONSAVEL).eq("setor", setor).execute()
    return result.data or []


def alertar_diretoria_sem_titular(
    supabase,
    manifestacao_id: str,
    gestor_nome: str,
    gravidade: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> None:
    """Setor acionado sem titular vigente sobe ao gestor E avisa a Diretoria
    (ADR 0034, decisão 5): o alerta é o que impede o buraco no cadastro de
    virar rotina silenciosa."""
    try:
        result = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("perfil_ouvidoria", "diretoria_executiva")
            .execute()
        )
        diretores = [d for d in (result.data or []) if (d.get("email") or "").strip()]
    except Exception:
        logger.warning("Falha ao buscar a Diretoria Executiva para o alerta de setor sem titular")
        return

    if not diretores:
        logger.warning("Setor sem titular na manifestação %s e sem Diretoria com email cadastrado", manifestacao_id)
        return

    for diretor in diretores:
        alerta = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=ouvidoria_notificacoes.GATILHO_ALERTA_SEM_TITULAR,
            destinatario_nome=diretor.get("nome_completo") or diretor["email"],
            destinatario_email=diretor["email"],
            papel_destinatario="diretoria_executiva",
            # A janela comercial vale para toda notificação da leva, não só
            # para o acionamento: setor sem titular não é urgência que
            # justifique acordar a Diretoria de madrugada. Caso crítico é a
            # exceção, e é a mesma regra do email ao setor.
            enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, gravidade, feriados),
            detalhe=gestor_nome,
        )
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, alerta, agora, feriados)


class PedidoResponsavel(BaseModel):
    """Quem passa a responder pelo setor. `vigencia_fim` vazio é o caso comum:
    o titular de hoje, sem data de saída marcada."""

    setor: str
    papel: Literal["titular", "substituto", "gestor"]
    nome: str
    email: EmailStr
    vigencia_inicio: dt.date | None = None
    vigencia_fim: dt.date | None = None

    @field_validator("setor", "nome")
    @classmethod
    def _texto_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo obrigatório do cadastro não pode ser vazio")
        return valor

    @model_validator(mode="after")
    def _vigencia_coerente(self) -> "PedidoResponsavel":
        inicio = self.vigencia_inicio or dt.date.today()
        if self.vigencia_fim and self.vigencia_fim < inicio:
            raise ValueError("a vigência não pode terminar antes de começar")
        return self


class EdicaoResponsavel(BaseModel):
    """Edição do cadastro. É por aqui que a vigência do titular se encerra
    quando ele sai do papel."""

    nome: str
    email: EmailStr
    vigencia_inicio: dt.date | None = None
    vigencia_fim: dt.date | None = None

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("o nome do responsável não pode ser vazio")
        return valor

    @model_validator(mode="after")
    def _vigencia_coerente(self) -> "EdicaoResponsavel":
        if self.vigencia_fim and self.vigencia_inicio and self.vigencia_fim < self.vigencia_inicio:
            raise ValueError("a vigência não pode terminar antes de começar")
        return self


def exigir_setor_da_taxonomia(supabase, setor: str) -> None:
    """Responsável só entra em setor que existe na taxonomia da casa (tabela
    `setores`, migration 027).

    Sem isso o cadastro viraria uma lista de nomes livres que nunca casaria com
    o setor da manifestação, e o acionamento cairia sempre no gestor."""
    try:
        result = supabase.table("setores").select("nome").eq("nome", setor).eq("ativo", True).execute()
    except Exception:
        logger.warning("Falha ao conferir o setor %s na taxonomia", setor)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível conferir o setor agora. Tente de novo em instantes.",
        ) from None
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"O setor {setor} não existe na lista de setores ativos do hospital",
        )


@router.get("/responsaveis")
@limiter.limit("60/minute")
async def listar_responsaveis(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Quem responde por cada setor. O ouvidor precisa enxergar o cadastro para
    saber por que uma demanda subiu ao gestor."""
    result = supabase.table("ouvidoria_setor_responsaveis").select(_CAMPOS_RESPONSAVEL).order("setor").execute()
    return {
        "responsaveis": [{campo: row.get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA} for row in (result.data or [])]
    }


@router.post("/responsaveis", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def cadastrar_responsavel(
    request: Request,
    pedido: PedidoResponsavel,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Cadastra titular, substituto ou gestor de um setor."""
    exigir_setor_da_taxonomia(supabase, pedido.setor)
    linha = {
        "setor": pedido.setor,
        "papel": pedido.papel,
        "nome": pedido.nome,
        "email": str(pedido.email),
        "vigencia_inicio": (pedido.vigencia_inicio or agora_utc().astimezone(FUSO_HOSPITAL).date()).isoformat(),
        "vigencia_fim": pedido.vigencia_fim.isoformat() if pedido.vigencia_fim else None,
    }
    try:
        result = supabase.table("ouvidoria_setor_responsaveis").insert(linha).execute()
    except APIError as exc:
        logger.error("Falha ao cadastrar responsável do setor (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível cadastrar o responsável",
        ) from exc
    row = result.data[0] if result.data else linha
    return {campo: row.get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA}


@router.put("/responsaveis/{responsavel_id}")
@limiter.limit("30/minute")
async def editar_responsavel(
    request: Request,
    responsavel_id: str,
    pedido: EdicaoResponsavel,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Edita o cadastro. Encerrar a vigência aqui é o que faz a próxima demanda
    do setor subir ao gestor, sem programador no meio."""
    mudanca: dict = {
        "nome": pedido.nome,
        "email": str(pedido.email),
        "vigencia_fim": pedido.vigencia_fim.isoformat() if pedido.vigencia_fim else None,
    }
    if pedido.vigencia_inicio:
        mudanca["vigencia_inicio"] = pedido.vigencia_inicio.isoformat()

    try:
        result = supabase.table("ouvidoria_setor_responsaveis").update(mudanca).eq("id", responsavel_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado")
    return {campo: result.data[0].get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA}


@router.delete("/responsaveis/{responsavel_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def remover_responsavel(
    request: Request,
    responsavel_id: str,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Tira a pessoa do cadastro. Para guardar a história de quem respondeu
    quando, o caminho é encerrar a vigência, não remover."""
    supabase.table("ouvidoria_setor_responsaveis").delete().eq("id", responsavel_id).execute()


@router.post("/manifestacoes/{manifestacao_id}/validar")
@limiter.limit("30/minute")
async def validar_e_acionar(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoValidacao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Valida a manifestação e aciona a área na mesma ação.

    É a única porta do despacho: nenhum processo automático acorda um setor
    (ADR 0034, decisão 3). O vencimento é calculado aqui e PERSISTIDO: mudar a
    tabela de prazos depois não move o prazo que o setor recebeu por email."""
    try:
        atual = (
            supabase.table("ouvidoria_protocolos")
            .select("id, status, sigilo_reforcado")
            .eq("id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")

    caso = atual.data[0]
    try:
        validar_transicao(caso["status"], "aguardando_area")
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # A validação é onde a categoria é DECIDIDA, então é aqui que a regra do
    # sigilo por categoria vale de novo: caso que chegou pela Ana nasce sem
    # sigilo (defaults da migration 064) e vira denúncia na mão do ouvidor. Sem
    # reavaliar, o email da denúncia iria ao setor denunciado com o nome de quem
    # manifestou e sem o selo, porque `_identificacao` só olha estas colunas.
    #
    # Só eleva, nunca abaixa: quem já é sigiloso segue sigiloso, seja qual for a
    # categoria escolhida. Por isso a coluna só entra no update quando sobe.
    sigiloso = bool(caso.get("sigilo_reforcado")) or nasce_sigilosa(pedido.categoria)

    extrato = extrato_do_acionamento(pedido.extrato_para_o_setor)

    agora = agora_utc()
    hoje = agora.astimezone(FUSO_HOSPITAL).date()
    destinatario = escolher_destinatario(carregar_responsaveis(supabase, pedido.setor), hoje)
    if destinatario is None:
        # Sem titular e sem gestor não há para quem despachar. Recusar é a
        # única saída honesta: acionar assim mandaria a demanda para o vazio e
        # o prazo correria contra ninguém.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O setor {pedido.setor} não tem titular nem gestor vigente. "
                "Cadastre o responsável antes de acionar a área."
            ),
        )

    feriados = carregar_feriados(supabase)
    vencimento = calcular_vencimento(agora, carregar_prazo_da_area(supabase, pedido.gravidade), feriados)

    # A classificação que o ouvidor digitou é gravada antes da transição: se a
    # corrida com outra transição recusar o passo, o que sobra no caso é o
    # trabalho de classificação, que não faz mal a ninguém. O extrato entra
    # junto pelo mesmo motivo, e porque o email é montado a partir do caso: o
    # que o setor lê tem que estar gravado antes de o email sair.
    #
    # O marco T1 e o prazo da área NÃO entram aqui: eles descrevem um
    # acionamento que aconteceu, e carimbá-los antes da RPC deixaria um caso
    # recusado com hora de validação e vencimento de um despacho que nunca
    # existiu. Vão logo depois da transição valer.
    classificacao = {
        "categoria": pedido.categoria,
        "setor": pedido.setor,
        "gravidade": pedido.gravidade,
        "extrato_para_o_setor": extrato,
    }
    if sigiloso and not caso.get("sigilo_reforcado"):
        classificacao["sigilo_reforcado"] = True
    supabase.table("ouvidoria_protocolos").update(classificacao).eq("id", manifestacao_id).execute()

    observacao = f"Validada e acionada: setor {pedido.setor}, gravidade {pedido.gravidade}"
    if pedido.observacao:
        observacao = f"{observacao}. {pedido.observacao}"
    try:
        resultado = supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": "aguardando_area",
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": observacao,
                "p_desfecho": None,
                "p_desfecho_descricao": None,
            },
        ).execute()
    except APIError as exc:
        if exc.code == "23514":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transição recusada") from exc
        logger.error("Erro na RPC ouvidoria_transicionar durante a validação (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acionar a área",
        ) from exc

    # Agora a transição existe: o marco e o vencimento podem ser carimbados.
    # Falha aqui é falha de infraestrutura e não pode passar em silêncio, senão
    # o setor recebe um email com prazo que o painel não mostra.
    #
    # `dados_incompletos` fica de fora: ele marca identificação pela metade
    # (nome sem contato, migration 064), e a validação classifica tipo, área e
    # gravidade sem pedir nem completar dado de quem manifestou. Zerar aqui
    # apagaria a sinalização do caso pela metade sem ninguém ter completado nada.
    try:
        supabase.table("ouvidoria_protocolos").update(
            {
                "prazo_area_em": vencimento.isoformat() if vencimento else None,
                "validada_em": agora.isoformat(),
                "validada_por": me["id"],
            }
        ).eq("id", manifestacao_id).execute()
    except APIError as exc:
        logger.error("Falha ao gravar o marco T1 da manifestação %s (código %s)", manifestacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso mudou de estado, mas o prazo não foi gravado e o setor não foi notificado. "
                "Confira a manifestação no painel."
            ),
        ) from exc

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
        destinatario_nome=destinatario.nome,
        destinatario_email=destinatario.email,
        papel_destinatario=destinatario.papel,
        enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, pedido.gravidade, feriados),
    )
    if notificacao is None:
        # Sem linha na fila não há email, não há registro no caso e não há botão
        # de reenvio: o prazo correria contra um setor que ninguém avisou. Mesma
        # régua da gravação do marco T1 acima, o caso não pode mentir ao ouvidor.
        logger.error("Falha ao registrar o acionamento da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso mudou de estado, mas o setor não foi notificado e o acionamento não ficou registrado. "
                "Confira a manifestação no painel."
            ),
        )
    ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, feriados)

    if destinatario.alerta_diretoria:
        alertar_diretoria_sem_titular(supabase, manifestacao_id, destinatario.nome, pedido.gravidade, agora, feriados)

    registrar_acesso(supabase, me, manifestacao_id, "validar_e_acionar")
    row = resultado.data[0] if isinstance(resultado.data, list) else resultado.data
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    if completo.data:
        row = completo.data[0]
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA} | _projetar_prazo(row, agora, feriados)


@router.get("/manifestacoes/{manifestacao_id}/notificacoes")
@limiter.limit("60/minute")
async def listar_notificacoes(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Toda notificação que o caso já gerou, da mais recente para a mais antiga.

    É o que prova a cobrança (ADR 0034, decisão 7) e o que alimenta o botão de
    reenvio."""
    carregar_manifestacao(supabase, manifestacao_id)
    result = (
        supabase.table("ouvidoria_notificacoes")
        .select(ouvidoria_notificacoes.CAMPOS_NOTIFICACAO)
        .eq("manifestacao_id", manifestacao_id)
        .order("criada_em", desc=True)
        .execute()
    )
    return {
        "notificacoes": [
            {campo: row.get(campo) for campo in ouvidoria_notificacoes.CAMPOS_NOTIFICACAO_TUPLA}
            for row in (result.data or [])
        ]
    }


@router.post("/manifestacoes/{manifestacao_id}/notificacoes/{notificacao_id}/reenviar", status_code=201)
@limiter.limit("30/minute")
async def reenviar_notificacao(
    request: Request,
    manifestacao_id: str,
    notificacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Manda a mesma notificação de novo, quando o setor diz que não recebeu.

    O reenvio nasce como registro próprio em vez de reescrever o original: a
    data do primeiro envio é o que prova quando a cobrança começou.

    Sai na hora, mesmo fora do expediente: a janela comercial existe para o
    disparo automático não acordar ninguém de madrugada, e aqui há uma pessoa
    da Ouvidoria decidindo mandar."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .select(ouvidoria_notificacoes.CAMPOS_NOTIFICACAO)
            .eq("id", notificacao_id)
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada")

    anterior = result.data[0]
    agora = agora_utc()
    copia = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=anterior["gatilho"],
        destinatario_nome=anterior["destinatario_nome"],
        destinatario_email=anterior["destinatario_email"],
        papel_destinatario=anterior.get("papel_destinatario"),
        enviar_a_partir_de=agora,
        detalhe=anterior.get("detalhe"),
    )
    if copia is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar o reenvio",
        )

    entregue = ouvidoria_notificacoes.despachar(supabase, copia, agora, carregar_feriados(supabase))
    registrar_acesso(supabase, me, manifestacao_id, "reenviar_notificacao")
    return {"id": copia["id"], "gatilho": copia["gatilho"], "entregue": entregue}


# =====================================================================
# Prorrogação de prazo (issue #333, PRD #318, ADR 0034 decisão 12)
# =====================================================================


class DecisaoDeProrrogacao(BaseModel):
    """A decisão do ouvidor sobre o pedido da área. A justificativa é
    opcional, mas vai por email a quem pediu quando existir."""

    aprovada: bool
    justificativa: str | None = None

    @field_validator("justificativa")
    @classmethod
    def _justificativa_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None


@router.get("/manifestacoes/{manifestacao_id}/prorrogacoes")
@limiter.limit("60/minute")
async def listar_prorrogacoes(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O pedido de prorrogação do caso, quando existe. É uma lista de zero ou
    um: a regra da casa permite um pedido por manifestação."""
    carregar_manifestacao(supabase, manifestacao_id)
    pedido = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    return {"prorrogacoes": [pedido] if pedido else []}


@router.post("/manifestacoes/{manifestacao_id}/prorrogacoes/{prorrogacao_id}/decidir")
@limiter.limit("30/minute")
async def decidir_prorrogacao(
    request: Request,
    manifestacao_id: str,
    prorrogacao_id: str,
    decisao: DecisaoDeProrrogacao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O ouvidor aprova ou nega o pedido da área (PRD #318, história 3).

    Aprovar move o vencimento do caso; negar deixa o prazo onde estava. Nos
    dois caminhos o ato vira movimento na trilha e email registrado a quem
    pediu. O prazo novo é recalculado aqui, e não copiado do pedido: entre o
    pedido e a decisão o teto de 30 dias úteis da entrada pode ter ficado mais
    perto, e quem manda é ele."""
    # O Dossiê inteiro, não só o `id`: a decisão precisa de estado, entrada,
    # prazo e gravidade, e o email é montado a partir do caso.
    encontrado = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    if not encontrado.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    caso = encontrado.data[0]
    pedido = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    if pedido is None or pedido["id"] != prorrogacao_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido de prorrogação não encontrado")
    if pedido["status"] != ouvidoria_prorrogacao.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido de prorrogação já foi decidido.",
        )
    if caso.get("status") != ouvidoria_prorrogacao.AGUARDANDO_AREA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O caso não está mais aguardando a área, então o pedido de prorrogação perdeu o objeto.",
        )

    agora = agora_utc()
    feriados = carregar_feriados(supabase)
    mudanca = {
        "status": ouvidoria_prorrogacao.APROVADA if decisao.aprovada else ouvidoria_prorrogacao.NEGADA,
        "decidida_em": agora.isoformat(),
        "decidida_por": me["id"],
        "decidida_por_nome": me.get("nome_completo") or me["id"],
        "decisao_justificativa": decisao.justificativa,
    }

    prazo_novo = None
    if decisao.aprovada:
        entrada = ouvidoria_prorrogacao.entrada_da_manifestacao(caso)
        bruto = caso.get("prazo_area_em")
        if entrada is None or not bruto:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este caso não tem entrada e prazo registrados, então não há prorrogação a aprovar.",
            )
        prazo_novo = vencimento_prorrogado(
            entrada, dt.datetime.fromisoformat(str(bruto)), int(pedido["dias_uteis_pedidos"]), feriados
        )
        if prazo_novo is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"O prazo deste caso já alcançou o teto de {TETO_PRORROGACAO_DIAS_UTEIS} dias úteis da entrada. "
                    "Não há prorrogação a aprovar."
                ),
            )
        mudanca["prazo_novo"] = prazo_novo.isoformat()

    # O prazo do caso muda ANTES de a decisão ser gravada: o email da decisão é
    # montado a partir do caso, e ele precisa dizer o prazo que passa a valer.
    # Falha aqui não deixa pedido aprovado com prazo antigo, porque a linha do
    # pedido ainda está pendente.
    if prazo_novo is not None:
        try:
            supabase.table("ouvidoria_protocolos").update({"prazo_area_em": prazo_novo.isoformat()}).eq(
                "id", manifestacao_id
            ).execute()
        except APIError as exc:
            logger.error("Falha ao mover o prazo da manifestação %s (código %s)", manifestacao_id, exc.code)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Não foi possível mover o prazo agora. Tente de novo.",
            ) from exc

    try:
        supabase.table("ouvidoria_prorrogacoes").update(mudanca).eq("id", prorrogacao_id).execute()
    except APIError as exc:
        logger.error("Falha ao gravar a decisão da prorrogação %s (código %s)", prorrogacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar a decisão agora. Tente de novo.",
        ) from exc

    veredito = "aprovada" if decisao.aprovada else "negada"
    observacao = f"Prorrogação {veredito} pela Ouvidoria"
    if prazo_novo is not None:
        quando = prazo_novo.astimezone(FUSO_HOSPITAL).strftime("%d/%m/%Y às %Hh%M")
        observacao = f"{observacao}. Prazo novo: {quando}"
    if decisao.justificativa:
        observacao = f"{observacao}. {decisao.justificativa}"
    ouvidoria_prorrogacao.registrar_movimento(
        supabase,
        manifestacao_id,
        autor_id=me["id"],
        autor_nome=me.get("nome_completo") or me["id"],
        observacao=observacao,
    )

    if (pedido.get("solicitante_email") or "").strip():
        aviso = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=ouvidoria_notificacoes.GATILHO_PRORROGACAO_DECIDIDA,
            destinatario_nome=pedido["solicitante_nome"],
            destinatario_email=pedido["solicitante_email"],
            papel_destinatario="setor",
            enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, caso.get("gravidade"), feriados),
        )
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, aviso, agora, feriados)
    else:
        logger.warning("Prorrogação %s decidida sem email do solicitante para avisar", prorrogacao_id)

    registrar_acesso(supabase, me, manifestacao_id, "decidir_prorrogacao")
    atualizado = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    row = completo.data[0] if completo.data else caso
    return {"prorrogacao": atualizado} | _projetar_prazo(row, agora, feriados)


# Anexos da Manifestação (issue #321): metadados no banco, binário no storage,
# leitura por URL assinada (ADR 0034).
_CAMPOS_ANEXO_TUPLA = ("id", "filename", "content_type", "tamanho_bytes", "enviado_por_nome", "created_at")

# Meia hora: o ouvidor abre o anexo, lê e fecha. Link colado em conversa alheia
# expira antes de virar acesso permanente à evidência.
EXPIRACAO_URL_ANEXO_SEGUNDOS = 1800


def carregar_manifestacao(supabase, manifestacao_id: str) -> dict:
    """Confirma que a manifestação existe antes de qualquer efeito colateral.
    Levanta 404 quando não existe."""
    try:
        result = supabase.table("ouvidoria_protocolos").select("id, protocolo").eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    return result.data[0]


def _recusa_de_anexo(exc: AnexoRecusadoError) -> HTTPException:
    """Traduz a recusa do módulo de anexo para o status HTTP certo, mantendo a
    mensagem que o ouvidor lê na tela."""
    if isinstance(exc, TipoNaoPermitidoError):
        codigo = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(exc, AnexoGrandeDemaisError):
        codigo = status.HTTP_413_CONTENT_TOO_LARGE
    else:
        codigo = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=codigo, detail=str(exc))


@router.post("/manifestacoes/{manifestacao_id}/anexos", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def anexar_arquivo(
    request: Request,
    manifestacao_id: str,
    file: UploadFile = File(...),
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Guarda a evidência junto do caso: foto, PDF, áudio ou documento.

    O binário vai ao storage privado e só os metadados ficam no banco. Arquivo
    recusado não deixa rastro: a validação vem antes do upload."""
    manifestacao = carregar_manifestacao(supabase, manifestacao_id)

    # `file.size` vem do Content-Length da parte multipart: recusar por ele
    # evita puxar 200 MB para a memória só para depois dizer não.
    try:
        extensao, content_type = validar_anexo(file.filename or "", file.size or 0)
    except AnexoRecusadoError as exc:
        raise _recusa_de_anexo(exc) from exc

    conteudo = await file.read()
    # O tamanho real manda: o Content-Length é do cliente e pode não bater com
    # o que veio no corpo.
    try:
        validar_anexo(file.filename or "", len(conteudo))
    except AnexoRecusadoError as exc:
        raise _recusa_de_anexo(exc) from exc

    # Caminho sorteado: o nome original é dado da manifestação (pode conter o
    # nome de quem reclamou) e não vira parte de caminho no storage.
    path = f"manifestacao-{manifestacao_id}/{uuid.uuid4().hex}{extensao}"
    subiu = storage.upload_private(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=path,
        content=conteudo,
        content_type=content_type,
    )
    if not subiu:
        # Sem binário não existe anexo: melhor recusar do que registrar
        # metadado que aponta para o vazio.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível guardar o anexo agora. Tente de novo em instantes.",
        )

    try:
        inserido = (
            supabase.table("ouvidoria_anexos")
            .insert(
                {
                    "manifestacao_id": manifestacao["id"],
                    "filename": file.filename,
                    "content_type": content_type,
                    "tamanho_bytes": len(conteudo),
                    "storage_path": path,
                    "enviado_por": me["id"],
                    "enviado_por_nome": me.get("nome_completo") or me["id"],
                }
            )
            .execute()
        )
        row = inserido.data[0]
    except (APIError, IndexError) as exc:
        # Sem a linha no banco, o binário no bucket vira órfão que ninguém
        # alcança e nada recolhe (ON DELETE RESTRICT não ajuda aqui). Limpar
        # agora é a única chance.
        storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, path)
        logger.error("Falha ao registrar o anexo da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível guardar o anexo. Tente de novo.",
        ) from exc

    registrar_acesso(supabase, me, manifestacao_id, "anexar_arquivo")
    return {campo: row.get(campo) for campo in _CAMPOS_ANEXO_TUPLA}


@router.get("/manifestacoes/{manifestacao_id}/anexos")
@limiter.limit("60/minute")
async def listar_anexos(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Anexos do caso, sem o caminho no storage: o acesso ao binário é sempre
    pela rota que assina a URL."""
    carregar_manifestacao(supabase, manifestacao_id)
    result = (
        supabase.table("ouvidoria_anexos")
        .select(", ".join(_CAMPOS_ANEXO_TUPLA))
        .eq("manifestacao_id", manifestacao_id)
        .order("created_at")
        .execute()
    )
    # O nome original do arquivo pode identificar quem manifestou, então ler a
    # lista já é acesso a dado do caso e entra na trilha.
    registrar_acesso(supabase, me, manifestacao_id, "listar_anexos")
    return {"anexos": [{campo: row.get(campo) for campo in _CAMPOS_ANEXO_TUPLA} for row in (result.data or [])]}


@router.get("/manifestacoes/{manifestacao_id}/anexos/{anexo_id}/url")
@limiter.limit("60/minute")
async def abrir_anexo(
    request: Request,
    manifestacao_id: str,
    anexo_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """URL assinada, com expiração, para abrir o anexo.

    O anexo precisa ser DESTE caso: sem esse casamento, o id de um anexo viraria
    caminho lateral para a evidência de outra manifestação."""
    try:
        result = (
            supabase.table("ouvidoria_anexos")
            .select("id, storage_path, manifestacao_id, filename")
            .eq("id", anexo_id)
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        # Id que não é UUID faz o PostgREST recusar o filtro (22P02). Do lado
        # de fora isso é o mesmo que anexo inexistente.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado")

    url = storage.signed_url(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=result.data[0]["storage_path"],
        expires_in=EXPIRACAO_URL_ANEXO_SEGUNDOS,
    )
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o anexo agora. Tente de novo em instantes.",
        )
    registrar_acesso(supabase, me, manifestacao_id, "abrir_anexo")
    return {
        "url": url,
        "filename": result.data[0]["filename"],
        "expira_em_segundos": EXPIRACAO_URL_ANEXO_SEGUNDOS,
    }


# =====================================================================
# Parâmetros do motor de prazos (issue #322, RN-21 e RN-22)
# =====================================================================

_CAMPOS_PRAZO_TUPLA = ("gravidade", "marco", "valor", "unidade")
_CAMPOS_PRAZO = ", ".join(_CAMPOS_PRAZO_TUPLA)
_CAMPOS_FERIADO_TUPLA = ("data", "nome", "abrangencia")
_CAMPOS_FERIADO = ", ".join(_CAMPOS_FERIADO_TUPLA)
# Teto de sanidade do prazo. A spec limita a prorrogação a 30 dias úteis de
# T0; 365 dá folga de sobra e ainda impede que um valor absurdo faça o motor
# caminhar milhões de dias pelo calendário.
TETO_DO_PRAZO = 365
_CAMPOS_HISTORICO_PRAZO_TUPLA = (
    "id",
    "gravidade",
    "marco",
    "valor_anterior",
    "unidade_anterior",
    "valor_novo",
    "unidade_nova",
    "autor_nome",
    "ocorrido_em",
)
_CAMPOS_HISTORICO_PRAZO = ", ".join(_CAMPOS_HISTORICO_PRAZO_TUPLA)


@router.get("/prazos")
@limiter.limit("60/minute")
async def listar_prazos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """A tabela de prazos por gravidade que alimenta o motor. Leitura para
    quem trabalha na Ouvidoria; edição só para a Diretoria Executiva."""
    result = supabase.table("ouvidoria_prazos").select(_CAMPOS_PRAZO).execute()
    linhas = result.data or []
    return {"prazos": [{campo: row.get(campo) for campo in _CAMPOS_PRAZO_TUPLA} for row in linhas]}


class PedidoPrazo(BaseModel):
    """Uma célula da tabela. `valor` nulo significa sem prazo (crítico não tem
    conclusiva fixa; baixo não passa pela área)."""

    valor: int | None = None
    unidade: Literal["horas_uteis", "dias_uteis"]


@router.put("/prazos/{gravidade}/{marco}")
@limiter.limit("30/minute")
async def editar_prazo(
    request: Request,
    gravidade: Literal["critico", "alto", "medio", "baixo"],
    marco: Literal["triagem", "area_resposta", "conclusiva"],
    pedido: PedidoPrazo,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Edita um prazo (RN-21). A mudança vale para validação nova: nenhum caso
    já despachado é recalculado, porque o vencimento deles está congelado em
    `prazo_area_em` desde o acionamento."""
    if pedido.valor is not None and not (0 <= pedido.valor <= TETO_DO_PRAZO):
        # O teto não é burocracia: o motor caminha dia a dia pelo calendário, e
        # valor sem limite vira request travado na hora de validar o caso.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Prazo precisa estar entre 0 e {TETO_DO_PRAZO}",
        )

    atual = (
        supabase.table("ouvidoria_prazos").select(_CAMPOS_PRAZO).eq("gravidade", gravidade).eq("marco", marco).execute()
    )
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prazo não encontrado")
    anterior = atual.data[0]

    if anterior.get("valor") == pedido.valor and anterior.get("unidade") == pedido.unidade:
        # Salvar o que já estava lá não é alteração. O histórico é append-only
        # e não se limpa depois: passar pelas células sem mudar nada não pode
        # encher de "mudou de 2 para 2" o que a Diretoria vai ler amanhã.
        return {"gravidade": gravidade, "marco": marco, "valor": pedido.valor, "unidade": pedido.unidade}

    supabase.table("ouvidoria_prazos").update({"valor": pedido.valor, "unidade": pedido.unidade}).eq(
        "gravidade", gravidade
    ).eq("marco", marco).execute()

    # O histórico é o que prova quem mudou o prazo e quando (RN-21). Escrito
    # depois da mudança valer, para não registrar edição que não aconteceu.
    supabase.table("ouvidoria_prazos_historico").insert(
        {
            "gravidade": gravidade,
            "marco": marco,
            "valor_anterior": anterior.get("valor"),
            "unidade_anterior": anterior.get("unidade"),
            "valor_novo": pedido.valor,
            "unidade_nova": pedido.unidade,
            "autor_id": me["id"],
            "autor_nome": me.get("nome_completo") or me["id"],
        }
    ).execute()

    return {"gravidade": gravidade, "marco": marco, "valor": pedido.valor, "unidade": pedido.unidade}


@router.get("/prazos/historico")
@limiter.limit("60/minute")
async def listar_historico_de_prazos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Quem mudou qual prazo, quando, de quanto para quanto."""
    result = (
        supabase.table("ouvidoria_prazos_historico")
        .select(_CAMPOS_HISTORICO_PRAZO)
        .order("ocorrido_em", desc=True)
        .execute()
    )
    # Projetada campo a campo como as demais rotas do módulo: coluna nova na
    # tabela não vira campo novo na resposta sem alguém decidir isso.
    return {
        "historico": [{campo: row.get(campo) for campo in _CAMPOS_HISTORICO_PRAZO_TUPLA} for row in (result.data or [])]
    }


@router.get("/feriados")
@limiter.limit("60/minute")
async def listar_feriados(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os dias que saem do calendário útil (RN-22)."""
    result = supabase.table("ouvidoria_feriados").select(_CAMPOS_FERIADO).order("data").execute()
    linhas = result.data or []
    return {"feriados": [{campo: row.get(campo) for campo in _CAMPOS_FERIADO_TUPLA} for row in linhas]}


class PedidoFeriado(BaseModel):
    data: dt.date
    nome: str
    abrangencia: Literal["nacional", "estadual_rj", "municipal_rio"]

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Feriado sem nome não é administrável")
        return v.strip()


@router.post("/feriados", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def cadastrar_feriado(
    request: Request,
    pedido: PedidoFeriado,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Cadastra um feriado. A partir daqui o motor deixa de contar esse dia."""
    try:
        supabase.table("ouvidoria_feriados").insert(
            {"data": pedido.data.isoformat(), "nome": pedido.nome, "abrangencia": pedido.abrangencia}
        ).execute()
    except APIError as exc:
        if exc.code == "23505":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feriado já cadastrado") from exc
        raise
    return {"data": pedido.data.isoformat(), "nome": pedido.nome, "abrangencia": pedido.abrangencia}


@router.delete("/feriados/{data}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def remover_feriado(
    request: Request,
    data: dt.date,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Remove um feriado: o dia volta a contar no calendário útil."""
    supabase.table("ouvidoria_feriados").delete().eq("data", data.isoformat()).execute()
