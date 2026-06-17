"""Schemas Pydantic do contexto POPs (ADR 0007).

Terminologia conforme docs/pops/CONTEXT.md: Setor é a unidade do organograma
do HSM (entidade própria, com nome e sigla únicos — a sigla é a base do
Código travado HSM_[SIGLA]-[NNN]). Não confundir com o campo livre `setor`
nem com a tabela `setores` (taxonomia do contexto Reuniões).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class PopPapeisUpdate(BaseModel):
    """Edição dos papéis do fluxo de um POP, antes da assinatura (ADR 0015).

    Cobre SOMENTE Elaborador, Revisor e Validador. `extra="forbid"` sela a
    imutabilidade do Código (e de todo o resto): qualquer campo fora dos três
    papéis vira 422. Pelo menos um papel é exigido na regra do endpoint."""

    model_config = ConfigDict(extra="forbid")

    elaborador_id: str | None = None
    revisor_id: str | None = None
    validador_id: str | None = None


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


# === Revisão e Validação — aprovar/devolver com retorno direto (issue #85) ===


class PopDevolucaoCreate(BaseModel):
    """Body do devolver (Revisão ou Validação): os comentários são a essência
    da Devolução — sem eles o Elaborador não sabe o que ajustar."""

    comentarios: str = Field(..., min_length=1, max_length=4000)


class PopDevolucaoResponse(BaseModel):
    """Devolução registrada com nome e timestamp (PRD #76) — visível na
    elaboração, na leitura da Versão e auditável pelo Gestor de Qualidade."""

    id: str
    autor_id: str
    autor_nome: str | None = None
    etapa_retorno: Literal["EM_REVISAO", "EM_VALIDACAO"]
    comentarios: str
    created_at: str | None = None


# === Elaboração — POP vivo com chat do agente (issue #83) ===

# Template institucional de CONTEÚDO (DRF §4.2, seções 2–11): as chaves legadas
# com o título canônico de cada uma. Com a estrutura dinâmica (ADR 0016) deixou
# de ser o shape do rascunho; segue como base de DUAS coisas: a migração dos
# rascunhos legados (chave → seção) e a estrutura institucional que o agente
# propõe quando não há modelo anexado. A seção 1 (Identificação) deriva do POP,
# fora da lista — imune ao agente por construção.
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


class PopElaboracaoChatRequest(BaseModel):
    """Body do POST /pops/{pop_id}/elaboracao/chat — stateless no padrão da
    Ata Guiada (ADR 0006): rascunho atual + mensagens + seção apontada (⌖).

    Diferença deliberada (PRD #76): o rascunho devolvido pelo agente PERSISTE
    na Versão a cada interação; só o histórico de mensagens é efêmero.
    """

    rascunho: dict = Field(default_factory=dict)
    messages: list[ChatMessageSchema] = Field(..., min_length=1)
    section_context: str | None = None


class PopFluxogramaSvgRequest(BaseModel):
    """Body do POST /elaboracao/fluxograma-svg (ADR 0017): o SVG do diagrama
    Mermaid renderizado pelo mermaid.js no cliente, capturado e persistido na
    seção de fluxograma (campo `svg`) para o PDF embutir o mesmo do preview.
    """

    section_id: str = Field(..., min_length=1)
    svg: str = Field(..., min_length=1, max_length=2_000_000)


class PopMaterialReferenciaResponse(BaseModel):
    """Material de referência na lista da tela — payload enxuto, sem o texto
    extraído (que é insumo do agente, não da UI)."""

    id: str
    filename: str
    extensao: str
    tamanho_bytes: int
    created_at: str | None = None


class PopMaterialUploadErro(BaseModel):
    """Arquivo recusado no upload múltiplo — mensagem do extractor, clara e
    por arquivo (um inválido não derruba os demais)."""

    filename: str
    detail: str


class PopMateriaisUploadResponse(BaseModel):
    """POST /materiais é por-arquivo: os válidos entram, os recusados voltam
    com o motivo. Sempre 200 estruturado — a tela nunca quebra."""

    materiais: list[PopMaterialReferenciaResponse] = Field(default_factory=list)
    erros: list[PopMaterialUploadErro] = Field(default_factory=list)


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
    """A Versão completa de um POP — mesma renderização nas telas de
    elaboração (GET /elaboracao) e de leitura da Revisão/Validação
    (GET /versao). Reabrir recupera exatamente onde a elaboração parou;
    as Devoluções acompanham, da mais recente à mais antiga."""

    pop: PopElaboracaoPopInfo
    versao: PopVersaoResponse
    rascunho: dict | None = None
    periodicidade_sugerida: PeriodicidadeRevisao | None = None
    devolucoes: list[PopDevolucaoResponse] = Field(default_factory=list)
    materiais: list[PopMaterialReferenciaResponse] = Field(default_factory=list)


class BibliotecaItemResponse(BaseModel):
    """Um POP Publicado na Biblioteca (issue #87): identificação, versão
    vigente, responsáveis designados e as datas de cada etapa do ciclo —
    criação, fim da elaboração, aprovações e publicação (da auditoria das
    transições + data_publicacao da Versão)."""

    pop_id: str
    codigo: str
    nome: str
    setor_id: str
    setor_nome: str | None = None
    setor_sigla: str | None = None
    numero_versao: str
    criticidade: CriticidadePop
    periodicidade_revisao: PeriodicidadeRevisao
    elaborador_nome: str | None = None
    revisor_nome: str | None = None
    validador_nome: str | None = None
    criado_em: str | None = None
    elaboracao_concluida_em: str | None = None
    revisao_aprovada_em: str | None = None
    validacao_aprovada_em: str | None = None
    publicado_em: str | None = None
