"""Schemas Pydantic do contexto POPs (ADR 0007).

Terminologia conforme docs/pops/CONTEXT.md: Setor é a unidade do organograma
do HSM (entidade própria, com nome e sigla únicos — a sigla é a base do
Código travado HSM_[SIGLA]-[NNN]). Não confundir com o campo livre `setor`
nem com a tabela `setores` (taxonomia do contexto Reuniões).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.schemas import ChatMessageSchema

PerfilPop = Literal["superadmin", "gestor_qualidade", "gerente", "coordenador"]
PERFIS_POP: tuple[str, ...] = ("superadmin", "gestor_qualidade", "gerente", "coordenador")


# === Setor ===


class PopsSetorCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    sigla: str = Field(..., min_length=1, max_length=20)


class PopsSetorUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    sigla: str | None = Field(None, min_length=1, max_length=20)


class PopsSetorResponse(BaseModel):
    id: str
    nome: str
    sigla: str


# === Perfil POP (eixo de permissão do contexto, em participantes) ===


class PerfilPopUpdate(BaseModel):
    """`perfil_pop: null` revoga o perfil (encerra o acesso ao contexto)."""

    perfil_pop: PerfilPop | None = None
    reason: str | None = Field(None, max_length=500)


class PerfilPopResponse(BaseModel):
    participante_id: str
    perfil_pop: PerfilPop | None
    provisionado: bool = False
    new_password: str | None = None


class PopsUsuarioResponse(BaseModel):
    """Pessoa na listagem do admin POPs. auth_user_id presente = já loga."""

    id: str
    nome_completo: str | None = None
    email: str | None = None
    perfil_pop: PerfilPop | None = None
    auth_user_id: str | None = None
    ativo: bool = True


# === Vínculos pessoa↔Setor ===


class VinculosSetorUpdate(BaseModel):
    """Substitui o conjunto de Setores da pessoa (Gerente: vários;
    Coordenador: normalmente um — sem trava artificial)."""

    setor_ids: list[str] = Field(default_factory=list)


# === POP e Versão (issue #82) ===

CriticidadePop = Literal["CRITICA", "ALTA", "MEDIA"]
PeriodicidadeRevisao = Literal["3_meses", "6_meses", "1_ano", "2_anos"]

# Enum completo do fluxo da Versão (PRD #76) — as transições chegam nas
# fatias seguintes; nesta, a Versão 1.0 nasce em A_ELABORAR.
EstadoVersaoPop = Literal["A_ELABORAR", "EM_ELABORACAO", "EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO"]
ESTADOS_VERSAO_POP: tuple[str, ...] = (
    "A_ELABORAR",
    "EM_ELABORACAO",
    "EM_REVISAO",
    "EM_VALIDACAO",
    "EM_ASSINATURA",
    "PUBLICADO",
)


class PopCreate(BaseModel):
    """Formulário institucional de criação (DRF §3.2). O Código não entra:
    é gerado e travado pelo sistema (HSM_[SIGLA]-[NNN], sequência por Setor)."""

    setor_id: str
    nome: str = Field(..., min_length=1, max_length=255)
    elaborador_id: str
    revisor_id: str
    validador_id: str
    criticidade: CriticidadePop
    periodicidade_revisao: PeriodicidadeRevisao
    base_normativa: str | None = Field(None, max_length=2000)
    prazo_elaboracao_dias: int = Field(15, ge=1, le=365)
    prazo_revisao_dias: int = Field(30, ge=1, le=365)


class DesignavelResponse(BaseModel):
    """Usuário elegível a Elaborador/Revisor/Validador (tem perfil POP).

    Sem email no payload: o select usa nome + perfil; PII mínima na resposta
    (security-review do PR #100)."""

    id: str
    nome_completo: str | None = None
    perfil_pop: PerfilPop


class PopVersaoResponse(BaseModel):
    id: str
    numero_versao: str
    estado: EstadoVersaoPop


class PopResponse(BaseModel):
    id: str
    codigo: str
    nome: str
    setor_id: str
    setor_nome: str | None = None
    setor_sigla: str | None = None
    criticidade: CriticidadePop
    base_normativa: str | None = None
    periodicidade_revisao: PeriodicidadeRevisao
    prazo_elaboracao_dias: int
    prazo_revisao_dias: int
    elaborador_id: str
    revisor_id: str
    validador_id: str
    criado_por: str | None = None
    created_at: str | None = None
    versao: PopVersaoResponse | None = None


# === Elaboração — POP vivo com chat do agente (issue #83) ===

# Seções de CONTEÚDO do template institucional (DRF §4.2, seções 2–11) — as
# chaves do rascunho que o agente elabora. A seção 1 (Identificação: código
# travado, nome, setor, versão, responsáveis) deriva do POP e NÃO vive no
# rascunho — imune ao agente por construção.
SECOES_POP_CONTEUDO: tuple[tuple[str, str], ...] = (
    ("objetivo", "Objetivo"),
    ("abrangencia", "Abrangência"),
    ("definicoes_siglas", "Definições e siglas"),
    ("responsabilidades", "Responsabilidades"),
    ("materiais_equipamentos", "Materiais e equipamentos necessários"),
    ("descricao_procedimento", "Descrição do procedimento"),
    ("fluxograma", "Fluxograma"),
    ("indicadores_adesao", "Indicadores de adesão"),
    ("referencias_normativas", "Referências normativas"),
    ("historico_revisoes", "Histórico de revisões"),
)
CHAVES_RASCUNHO_POP: tuple[str, ...] = tuple(chave for chave, _ in SECOES_POP_CONTEUDO)


class PopElaboracaoChatRequest(BaseModel):
    """Body do POST /pops/{pop_id}/elaboracao/chat — stateless no padrão da
    Ata Guiada (ADR 0006): rascunho atual + mensagens + seção apontada (⌖).

    Diferença deliberada (PRD #76): o rascunho devolvido pelo agente PERSISTE
    na Versão a cada interação; só o histórico de mensagens é efêmero.
    """

    rascunho: dict = Field(default_factory=dict)
    messages: list[ChatMessageSchema] = Field(..., min_length=1)
    section_context: str | None = None


class PeriodicidadeEscolhaRequest(BaseModel):
    """Escolha final do Elaborador para a Periodicidade de revisão — o agente
    sugere (fica em pops_versoes.periodicidade_sugerida), ele decide."""

    periodicidade_revisao: PeriodicidadeRevisao


class PopElaboracaoPopInfo(BaseModel):
    """Dados do POP que alimentam a seção 1 (Identificação) da tela de
    elaboração — com os nomes dos designados resolvidos."""

    id: str
    codigo: str
    nome: str
    setor_nome: str | None = None
    setor_sigla: str | None = None
    criticidade: CriticidadePop
    base_normativa: str | None = None
    periodicidade_revisao: PeriodicidadeRevisao
    prazo_elaboracao_dias: int
    prazo_revisao_dias: int
    elaborador_id: str
    revisor_id: str
    validador_id: str
    elaborador_nome: str | None = None
    revisor_nome: str | None = None
    validador_nome: str | None = None
    created_at: str | None = None


class PopElaboracaoResponse(BaseModel):
    """GET /pops/{pop_id}/elaboracao — o estado completo da tela: reabrir
    recupera exatamente onde a elaboração parou."""

    pop: PopElaboracaoPopInfo
    versao: PopVersaoResponse
    rascunho: dict | None = None
    periodicidade_sugerida: PeriodicidadeRevisao | None = None
