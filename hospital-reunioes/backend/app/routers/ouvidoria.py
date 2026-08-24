"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. Índice, não dossiê:
o painel expõe os mesmos campos da API da Ana e nada além deles; protocolo
nasce só pelo registro da Ana (não existe rota de criação aqui).
"""

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, field_validator
from supabase import Client

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO_TUPLA
from app.services.ouvidoria_estados import (
    DadosInsuficientesError,
    TransicaoInvalidaError,
    validar_transicao,
)
from app.services.ouvidoria_prazos import esta_vencido, minutos_uteis_entre, rotular_vencimento

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria"])


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
_CAMPOS_INDICE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + ("gravidade", "prazo_area_em")
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
    return {
        "rotulo_prazo": rotular_vencimento(vencimento, agora, feriados),
        "prazo_estourado": estourado,
        "minutos_uteis_restantes": restantes,
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
    agora = dt.datetime.now(dt.UTC)
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
    registrar_acesso(supabase, me, manifestacao_id, "transicionar")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


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
