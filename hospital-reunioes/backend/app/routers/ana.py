"""API da Ana (ADR 0031): endpoints de serviço consumidos pela agente de IA.

Autenticação por API key de serviço dedicada (header X-API-Key, validado
contra ANA_API_KEY), fora do fluxo JWT. Leitura direta do banco, sem cache:
edição no admin vale na chamada seguinte.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from app.dependencies import get_supabase_client, require_ana_api_key
from app.limiter import limiter
from app.utils.text_sanitizer import sanitizar_estrutura

router = APIRouter(prefix="/ana", tags=["ana"], dependencies=[Depends(require_ana_api_key)])

# Colunas explícitas: coluna nova na tabela só entra na API por decisão revisada.
_CAMPOS_CONSULTA = (
    "id, especialidade, valor_rs, descricao_servico, diferencial_1, diferencial_2, "
    "diferencial_3, alta_demanda, observacoes_ana, ultima_atualizacao"
)

_CAMPOS_EXAME = (
    "id, nome_exame, tipo_exame, convenio_aceito, valor_particular_rs, "
    "requer_pedido_medico, preparo_necessario, instrucoes_preparo_completas, "
    "tempo_resultado, local_realizacao, diferencial_1, diferencial_2, "
    "observacoes_ana, ultima_atualizacao"
)

_CAMPOS_CIRURGIA = (
    "id, procedimento, descricao_procedimento, honorarios_equipe_rs, "
    "valor_internacao_rs, estimativa_total_rs, o_que_inclui_honorarios, "
    "o_que_inclui_internacao, diferencial_1, diferencial_2, "
    "caveat_obrigatorio_ana, observacoes_ana, ultima_atualizacao"
)

_CAMPOS_CONVENIO = "id, convenio, especialidade, cobre, observacao, ultima_atualizacao"

# Índice, não dossiê (ADR 0031 decisão 3): nenhuma coluna de dado pessoal existe.
_CAMPOS_PROTOCOLO = (
    "id, numero, protocolo, data_abertura, prazo_resposta, status, categoria, setor, resumo, conversa_id"
)


class RegistroProtocolo(BaseModel):
    """Registro de manifestação de ouvidoria. Campos críticos validados aqui e
    NOT NULL + CHECK no banco (defesa contra a falha silenciosa de interpolação
    do cliente da Ana, que enviaria vazio com sucesso aparente)."""

    categoria: str
    setor: str
    resumo: str
    conversa_id: str = ""

    @field_validator("categoria", "setor", "resumo")
    @classmethod
    def campo_critico_nao_vazio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("campo crítico não pode ser vazio")
        return valor.strip()


@router.get("/consultas-particulares")
@limiter.limit("60/minute")
async def listar_consultas_particulares(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Consultas particulares ativas, com preços e diferenciais."""
    result = (
        supabase.table("consultas_particulares")
        .select(_CAMPOS_CONSULTA)
        .eq("ativo", True)
        .order("especialidade")
        .execute()
    )
    return {"consultas_particulares": result.data or []}


@router.get("/exames")
@limiter.limit("60/minute")
async def listar_exames(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Exames ativos, com valores, preparo e local de realização."""
    result = supabase.table("exames").select(_CAMPOS_EXAME).eq("ativo", True).order("nome_exame").execute()
    return {"exames": result.data or []}


@router.get("/cirurgias-estimativas")
@limiter.limit("60/minute")
async def listar_cirurgias_estimativas(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Estimativas de cirurgias ativas, com valores e caveat obrigatório."""
    result = (
        supabase.table("cirurgias_estimativas")
        .select(_CAMPOS_CIRURGIA)
        .eq("ativo", True)
        .order("procedimento")
        .execute()
    )
    return {"cirurgias_estimativas": result.data or []}


@router.get("/convenios-especialidade")
@limiter.limit("60/minute")
async def listar_convenios_especialidade(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Cobertura de convênios por especialidade (registros ativos)."""
    result = (
        supabase.table("convenios_especialidade")
        .select(_CAMPOS_CONVENIO)
        .eq("ativo", True)
        .order("convenio")
        .order("especialidade")
        .execute()
    )
    return {"convenios_especialidade": result.data or []}


@router.post("/ouvidoria/protocolos", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def registrar_protocolo(
    request: Request,
    registro: RegistroProtocolo,
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação e devolve o protocolo ANO-NNNN gerado pelo banco
    (sequence + coluna gerada; a aplicação nunca compõe o número)."""
    # Tipografia sanitizada (ADR 0013): o resumo é texto gerado por IA e
    # aparece no painel de ouvidoria.
    payload = sanitizar_estrutura(registro.model_dump())
    result = supabase.table("ouvidoria_protocolos").insert(payload).execute()
    return result.data[0]


@router.get("/ouvidoria/protocolos/{protocolo}")
@limiter.limit("60/minute")
async def consultar_protocolo(
    request: Request,
    protocolo: str,
    supabase=Depends(get_supabase_client),
):
    """Consulta o índice da manifestação pelo número de protocolo (ANO-NNNN).

    Números já informados a pacientes seguem consultáveis após o import."""
    result = supabase.table("ouvidoria_protocolos").select(_CAMPOS_PROTOCOLO).eq("protocolo", protocolo).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocolo não encontrado")
    return result.data[0]
