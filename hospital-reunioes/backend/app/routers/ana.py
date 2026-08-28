"""API da Ana (ADR 0031): endpoints de serviço consumidos pela agente de IA.

Autenticação por API key de serviço dedicada (header X-API-Key, validado
contra ANA_API_KEY), fora do fluxo JWT. Leitura direta do banco, sem cache:
edição no admin vale na chamada seguinte.
"""

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.dependencies import get_supabase_client, require_ana_api_key
from app.limiter import limiter
from app.services.ouvidoria_taxonomia import SETOR_PENDENTE, nasce_sigilosa
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

# O que sai de um caso sigiloso: o andamento, e nada mais (issue #372). Quem
# consulta é quem tem o número, e o que ele precisa saber é se o caso anda.
_CAMPOS_PROTOCOLO_SIGILOSO_TUPLA = ("protocolo", "status", "data_abertura")

# O que a Ana não decide: o rumo do caso (estado e desfecho), a proteção do
# manifestante (sigilo, anonimato), a completude do Dossiê, a classificação
# pronta e a identidade do registro, que é o banco quem emite.
_CAMPOS_DE_DECISAO = frozenset(
    {
        "id",
        "numero",
        "protocolo",
        "data_abertura",
        "prazo_resposta",
        "status",
        "desfecho",
        "desfecho_descricao",
        "sigilo_reforcado",
        "tipo_manifestacao",
        "anonimo",
        "dados_incompletos",
        "classificacao_ia",
    }
)


class RegistroProtocolo(BaseModel):
    """Registro de manifestação de ouvidoria. Campos críticos validados aqui e
    NOT NULL + CHECK no banco (defesa contra a falha silenciosa de interpolação
    do cliente da Ana, que enviaria vazio com sucesso aparente).

    Os campos do Dossiê (ADR 0034, decisão 11) são todos opcionais: a Ana de
    hoje não os manda, e o POST antigo continua sendo um POST válido, com o
    caso entrando com dados incompletos para o ouvidor completar na validação.

    A Ana registra manifestação, não classifica caso nem encerra nada: status,
    desfecho, sigilo e a própria classificacao_ia são decisão do ouvidor e o
    POST recusa quem tentar mandá-los (ADR 0034, decisão 10). Campo
    desconhecido que não seja decisão do ouvidor é ignorado, não recusado: o
    cliente da Ana vive em outro repo e sobe em outra hora, e derrubar o
    registro por uma chave a mais deixaria paciente sem protocolo."""

    model_config = ConfigDict(extra="allow")

    categoria: str
    setor: str
    resumo: str
    conversa_id: str = ""

    relato_integral: str | None = None
    manifestante_nome: str | None = None
    manifestante_contato: str | None = None
    manifestante_vinculo: Literal["paciente", "acompanhante", "colaborador", "terceiro", "outro"] | None = None
    # Sugestão da Ana, não decisão: vai para classificacao_ia, à parte.
    gravidade_sugerida: Literal["critico", "alto", "medio", "baixo"] | None = None
    confianca_sugestao: Annotated[float, Field(ge=0, le=1)] | None = None

    @field_validator("categoria", "setor", "resumo")
    @classmethod
    def campo_critico_nao_vazio(cls, valor: str) -> str:
        # Tipografia sanitizada ANTES da validação (ADR 0013): o texto vem de
        # IA e aparece no painel; travessão sozinho não vira registro válido.
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo crítico não pode ser vazio")
        return valor

    @field_validator("relato_integral", "manifestante_nome", "manifestante_contato")
    @classmethod
    def opcional_vazio_e_ausencia(cls, valor: str | None) -> str | None:
        """A mesma falha silenciosa alcança os campos novos: vazio, espaço em
        branco ou travessão sozinho é ausência, não conteúdo. Gravar o vazio
        faria o Dossiê parecer preenchido para o ouvidor."""
        if valor is None:
            return None
        valor = sanitizar_travessao(valor).strip()
        return valor if re.search(r"\w", valor) else None

    @field_validator("manifestante_vinculo", "gravidade_sugerida", "confianca_sugestao", mode="before")
    @classmethod
    def opcional_em_branco_e_ausencia(cls, valor):
        """Antes da taxonomia, a mesma leitura: string em branco é o campo que
        a Ana não preencheu. Sem isto o vazio derrubaria o registro inteiro,
        e a manifestação se perderia por causa de um opcional (o CHECK da
        migration 064 aceita NULL de propósito)."""
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @model_validator(mode="after")
    def decisao_do_ouvidor_nao_entra(self) -> "RegistroProtocolo":
        """Quem decide o rumo do caso é o ouvidor. A Ana pode sugerir (e a
        sugestão vai para classificacao_ia), nunca decidir: mandar status,
        desfecho, sigilo ou a classificação pronta é recusado, mesmo que o
        insert já escreva só a lista fechada de colunas."""
        intrusos = _CAMPOS_DE_DECISAO & set(self.model_extra or {})
        if intrusos:
            raise ValueError(f"campo de decisão do ouvidor não entra pela API da Ana: {', '.join(sorted(intrusos))}")
        return self

    def _classificacao_ia(self) -> dict | None:
        """A sugestão da Ana, guardada à parte (ADR 0034, decisão 10). Sem
        gravidade sugerida não há sugestão nenhuma, e o grau de confiança que
        vier sozinho não é gravado: número sem o que graduar não diz nada, e
        recusar a manifestação por causa dele seria perder o caso."""
        if self.gravidade_sugerida is None:
            return None
        return {"gravidade": self.gravidade_sugerida, "confianca": self.confianca_sugestao}

    def _dados_incompletos(self) -> bool:
        """Sem relato, sem nome ou sem contato o ouvidor ainda tem o que
        completar antes de validar."""
        return not all((self.relato_integral, self.manifestante_nome, self.manifestante_contato))

    def para_linha(self) -> dict:
        """As colunas que a API da Ana escreve, e nada além delas: o resto da
        tabela fica com o default do banco, à espera do ouvidor."""
        return {
            "categoria": self.categoria,
            "setor": self.setor,
            "resumo": self.resumo,
            "conversa_id": self.conversa_id,
            "relato_integral": self.relato_integral,
            "manifestante_nome": self.manifestante_nome,
            "manifestante_contato": self.manifestante_contato,
            "manifestante_vinculo": self.manifestante_vinculo,
            "classificacao_ia": self._classificacao_ia(),
            "dados_incompletos": self._dados_incompletos(),
            # Fail-closed (issue #372). O caso entra SEM tipo, porque a Ana
            # registra mas não classifica (ADR 0034, decisão 10), e o `resumo`
            # que o índice mostra é texto gerado a partir da conversa com quem
            # manifestou: uma denúncia viraria texto visível na fila de todo
            # mundo até alguém classificar. Quem devolve o caso ao índice geral
            # é o ouvidor, pela porta de classificação.
            "sigilo_reforcado": nasce_sigilosa(None),
        }


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


@router.post("/ouvidoria/protocolos", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def registrar_protocolo(
    request: Request,
    registro: RegistroProtocolo,
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação e devolve o protocolo ANO-NNNN gerado pelo banco
    (sequence + coluna gerada; a aplicação nunca compõe o número).

    Aceita o contrato de sempre e, opcionalmente, o Dossiê que a Ana passa a
    preencher (ADR 0034, decisão 11). A resposta continua fechada no índice: a
    Ana fala com pacientes e não recebe de volta o que gravou do Dossiê."""
    linha = registro.para_linha()
    # A área que a IA escreveu passa pela taxonomia da casa (issue #419). Esta
    # porta NÃO recusa: a Ana fala com paciente, e derrubar o registro por um
    # nome de área deixaria gente sem protocolo. O que não casa vira o marcador
    # de pendente, exatamente como no canal aberto, e o ouvidor escolhe a área
    # na validação. Sem isto, "recepcao" vindo da IA viraria uma segunda
    # Recepção no relatório da Diretoria, que é a causa que esta issue fecha.
    #
    # Import na função: `ouvidoria_publica` é o dono da resolução de setor.
    from app.routers.ouvidoria_publica import _setor_da_taxonomia

    linha["setor"] = _setor_da_taxonomia(supabase, linha.get("setor")) or SETOR_PENDENTE

    try:
        result = supabase.table("ouvidoria_protocolos").insert(linha).execute()
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

    Números já informados a pacientes seguem consultáveis após o import.

    Do caso sigiloso sai só o andamento (issue #372, decisão 6). Esta rota é
    aberta a quem tem a chave de serviço e os números são sequenciais, logo
    enumeráveis: devolver `resumo`, `categoria` e `setor` de uma denúncia
    entregaria de bandeja o que a RN-40 protege, porque o resumo com frequência
    já identifica quem relatou."""
    result = (
        supabase.table("ouvidoria_protocolos")
        .select(f"{_CAMPOS_PROTOCOLO}, sigilo_reforcado")
        .eq("protocolo", protocolo)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocolo não encontrado")
    row = result.data[0]
    if row.get("sigilo_reforcado"):
        return {campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_SIGILOSO_TUPLA}
    return {campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_TUPLA}
