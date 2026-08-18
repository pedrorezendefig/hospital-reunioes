"""API da Ana (ADR 0031): endpoints de serviço consumidos pela agente de IA.

Autenticação por API key de serviço dedicada (header X-API-Key, validado
contra ANA_API_KEY), fora do fluxo JWT. Leitura direta do banco, sem cache:
edição no admin vale na chamada seguinte.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, field_validator

from app.dependencies import get_supabase_client, require_ana_api_key
from app.limiter import limiter
from app.utils.ana_resposta import filtrar_por_termo, montar_resposta
from app.utils.text_sanitizer import sanitizar_travessao

router = APIRouter(prefix="/ana", tags=["ana"], dependencies=[Depends(require_ana_api_key)])

# Colunas explícitas: coluna nova na tabela só entra na API por decisão revisada.
_CAMPOS_CONSULTA_TUPLA = (
    "id",
    "especialidade",
    "valor_rs",
    "descricao_servico",
    "diferencial_1",
    "diferencial_2",
    "diferencial_3",
    "alta_demanda",
    "observacoes_ana",
    "ultima_atualizacao",
)
_CAMPOS_CONSULTA = ", ".join(_CAMPOS_CONSULTA_TUPLA)

# Vitrine da consulta: a especialidade e o valor. O índice fica só com o nome.
_DEGRAUS_CONSULTA = {
    "completo": _CAMPOS_CONSULTA_TUPLA,
    "resumo": ("especialidade", "valor_rs"),
    "indice": ("especialidade",),
}

_DICAS_CONSULTA = {
    "completo": "Resposta completa. Para uma especialidade só, chame de novo com ?especialidade=NOME.",
    "resumo": (
        "Resposta resumida por tamanho. Para a descrição e os diferenciais de uma especialidade, "
        "chame de novo com ?especialidade=NOME."
    ),
    "indice": (
        "Só os nomes, por tamanho. Para o valor e os detalhes de uma especialidade, "
        "chame de novo com ?especialidade=NOME."
    ),
    "vazio": (
        "Nenhuma especialidade casou com o termo. As cadastradas estão em disponiveis: chame de novo com uma delas."
    ),
}

_CAMPOS_EXAME_TUPLA = (
    "id",
    "nome_exame",
    "tipo_exame",
    "convenio_aceito",
    "valor_particular_rs",
    "requer_pedido_medico",
    "preparo_necessario",
    "instrucoes_preparo_completas",
    "tempo_resultado",
    "local_realizacao",
    "diferencial_1",
    "diferencial_2",
    "observacoes_ana",
    "ultima_atualizacao",
)
_CAMPOS_EXAME = ", ".join(_CAMPOS_EXAME_TUPLA)

# Vitrine do exame: o nome e o valor. O índice fica só com o nome.
_DEGRAUS_EXAME = {
    "completo": _CAMPOS_EXAME_TUPLA,
    "resumo": ("nome_exame", "valor_particular_rs"),
    "indice": ("nome_exame",),
}

_DICAS_EXAME = {
    "completo": "Resposta completa. Para um exame só, chame de novo com ?exame=NOME.",
    "resumo": "Resposta resumida por tamanho. Para o preparo e os detalhes de um exame, chame de novo com ?exame=NOME.",
    "indice": "Só os nomes, por tamanho. Para o valor e os detalhes de um exame, chame de novo com ?exame=NOME.",
    "vazio": "Nenhum exame casou com o termo. Os nomes cadastrados estão em disponiveis: chame de novo com um deles.",
}

_CAMPOS_CIRURGIA_TUPLA = (
    "id",
    "procedimento",
    "descricao_procedimento",
    "honorarios_equipe_rs",
    "valor_internacao_rs",
    "estimativa_total_rs",
    "o_que_inclui_honorarios",
    "o_que_inclui_internacao",
    "diferencial_1",
    "diferencial_2",
    "caveat_obrigatorio_ana",
    "observacoes_ana",
    "ultima_atualizacao",
)
_CAMPOS_CIRURGIA = ", ".join(_CAMPOS_CIRURGIA_TUPLA)

# Vitrine da cirurgia: o procedimento e a estimativa total. Fora do completo, o
# aviso obrigatório sai da linha e entra uma vez no envelope.
_DEGRAUS_CIRURGIA = {
    "completo": _CAMPOS_CIRURGIA_TUPLA,
    "resumo": ("procedimento", "estimativa_total_rs"),
    "indice": ("procedimento",),
}

_DICAS_CIRURGIA = {
    "completo": "Resposta completa. Para um procedimento só, chame de novo com ?procedimento=NOME.",
    "resumo": (
        "Resposta resumida por tamanho. Diga sempre o caveat_obrigatorio_ana junto do valor. "
        "Para o que está incluso, chame de novo com ?procedimento=NOME."
    ),
    "indice": (
        "Só os nomes, por tamanho. Diga sempre o caveat_obrigatorio_ana junto de qualquer valor. "
        "Para a estimativa de um procedimento, chame de novo com ?procedimento=NOME."
    ),
    "vazio": (
        "Nenhum procedimento casou com o termo. Os cadastrados estão em disponiveis: chame de novo com um deles."
    ),
}

_CAMPOS_CONVENIO_TUPLA = ("id", "convenio", "especialidade", "cobre", "observacao", "ultima_atualizacao")
_CAMPOS_CONVENIO = ", ".join(_CAMPOS_CONVENIO_TUPLA)

# O nome de um registro de convênio é o par convênio + especialidade: nenhum dos
# dois sozinho identifica a linha. Por isso os dois ficam até no índice.
_DEGRAUS_CONVENIO = {
    "completo": _CAMPOS_CONVENIO_TUPLA,
    "resumo": ("convenio", "especialidade", "cobre"),
    "indice": ("convenio", "especialidade"),
}

_DICAS_CONVENIO = {
    "completo": (
        "Resposta completa. Para um convênio ou especialidade só, chame de novo com "
        "?convenio=NOME e/ou ?especialidade=NOME."
    ),
    "resumo": (
        "Resposta resumida por tamanho. Para a observação da cobertura, chame de novo com "
        "?convenio=NOME&especialidade=NOME."
    ),
    "indice": (
        "Só os pares convênio e especialidade, por tamanho. Para saber se cobre, chame de novo com "
        "?convenio=NOME&especialidade=NOME."
    ),
    "vazio": (
        "Nenhuma cobertura casou com o termo. Os pares cadastrados estão em disponiveis, no formato "
        "convênio / especialidade: escolha um e chame de novo com ?convenio=CONVENIO&especialidade=ESPECIALIDADE, "
        "cada parte no seu parâmetro."
    ),
}

# Índice, não dossiê (ADR 0031 decisão 3): nenhuma coluna de dado pessoal existe.
# Contrato fechado nas DUAS respostas (registro e consulta): coluna futura na
# tabela não vaza pela API sem decisão revisada.
_CAMPOS_PROTOCOLO_TUPLA = (
    "id",
    "numero",
    "protocolo",
    "data_abertura",
    "prazo_resposta",
    "status",
    "categoria",
    "setor",
    "resumo",
    "conversa_id",
)
_CAMPOS_PROTOCOLO = ", ".join(_CAMPOS_PROTOCOLO_TUPLA)


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
        # Tipografia sanitizada ANTES da validação (ADR 0013): o texto vem de
        # IA e aparece no painel; travessão sozinho não vira registro válido.
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo crítico não pode ser vazio")
        return valor


@router.get("/consultas-particulares")
@limiter.limit("60/minute")
async def listar_consultas_particulares(
    request: Request,
    especialidade: str = "",
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
    todas = result.data or []
    linhas = filtrar_por_termo(todas, "especialidade", especialidade)
    return montar_resposta("consultas_particulares", linhas, todas, campos=_DEGRAUS_CONSULTA, dicas=_DICAS_CONSULTA)


@router.get("/exames")
@limiter.limit("60/minute")
async def listar_exames(
    request: Request,
    exame: str = "",
    supabase=Depends(get_supabase_client),
):
    """Exames ativos, com valores, preparo e local de realização."""
    result = supabase.table("exames").select(_CAMPOS_EXAME).eq("ativo", True).order("nome_exame").execute()
    todas = result.data or []
    linhas = filtrar_por_termo(todas, "nome_exame", exame)
    return montar_resposta("exames", linhas, todas, campos=_DEGRAUS_EXAME, dicas=_DICAS_EXAME)


@router.get("/cirurgias-estimativas")
@limiter.limit("60/minute")
async def listar_cirurgias_estimativas(
    request: Request,
    procedimento: str = "",
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
    todas = result.data or []
    linhas = filtrar_por_termo(todas, "procedimento", procedimento)
    return montar_resposta(
        "cirurgias_estimativas",
        linhas,
        todas,
        campos=_DEGRAUS_CIRURGIA,
        dicas=_DICAS_CIRURGIA,
        caveat_campo="caveat_obrigatorio_ana",
    )


@router.get("/convenios-especialidade")
@limiter.limit("60/minute")
async def listar_convenios_especialidade(
    request: Request,
    convenio: str = "",
    especialidade: str = "",
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
    todas = result.data or []
    # As duas condições valem juntas: "o plano X cobre cardiologia?" é uma chamada só.
    do_convenio = filtrar_por_termo(todas, "convenio", convenio)
    linhas = filtrar_por_termo(do_convenio, "especialidade", especialidade)
    # Quando o convênio casa e só a especialidade erra, os nomes que ajudam a Ana
    # a reperguntar são os desse convênio, não os da tabela inteira.
    return montar_resposta(
        "convenios_especialidade",
        linhas,
        do_convenio or todas,
        campos=_DEGRAUS_CONVENIO,
        dicas=_DICAS_CONVENIO,
    )


@router.post("/ouvidoria/protocolos", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def registrar_protocolo(
    request: Request,
    registro: RegistroProtocolo,
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação e devolve o protocolo ANO-NNNN gerado pelo banco
    (sequence + coluna gerada; a aplicação nunca compõe o número)."""
    try:
        result = supabase.table("ouvidoria_protocolos").insert(registro.model_dump()).execute()
    except APIError as exc:
        # Detalhe do Postgres (constraint, tabela) não vaza para o cliente:
        # do lado da Ana, qualquer falha aciona a Regra Híbrida (sem número).
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar o protocolo",
        ) from exc
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar o protocolo",
        )
    row = result.data[0]
    return {campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_TUPLA}


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
