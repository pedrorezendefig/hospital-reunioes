"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. O painel lista o
índice para toda a equipe e abre o Dossiê só para a Ouvidoria (ADR 0034).

Desde a issue #321 a Manifestação também nasce aqui: o ouvidor registra o que
chegou por telefone, balcão ou email, com a data e hora reais do contato.
"""

import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, field_validator
from supabase import Client

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO, _CAMPOS_PROTOCOLO_TUPLA
from app.services import storage
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
from app.utils.text_sanitizer import sanitizar_travessao

# O T0 é hora de relógio de parede do hospital: o ouvidor digita "14/08 16h50"
# pensando em Brasília, e a persistência é em UTC.
FUSO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Folga para relógio de máquina adiantado, ao recusar contato "no futuro".
TOLERANCIA_RELOGIO = timedelta(minutes=5)

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
    # decide o filtro abaixo, e o índice segue fechado em _CAMPOS_PROTOCOLO.
    query = (
        supabase.table("ouvidoria_protocolos")
        .select(f"{_CAMPOS_PROTOCOLO}, sigilo_reforcado")
        .order("numero", desc=True)
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
    return {"protocolos": [{campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_TUPLA} for row in linhas]}


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
    registrar_acesso(supabase, me, manifestacao_id, "transicionar")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


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
