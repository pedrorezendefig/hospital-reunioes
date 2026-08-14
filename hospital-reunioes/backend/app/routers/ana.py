"""API da Ana (ADR 0031): endpoints de serviço consumidos pela agente de IA.

Autenticação por API key de serviço dedicada (header X-API-Key, validado
contra ANA_API_KEY), fora do fluxo JWT. Leitura direta do banco, sem cache:
edição no admin vale na chamada seguinte.
"""

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_supabase_client, require_ana_api_key
from app.limiter import limiter

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
