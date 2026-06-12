"""Schemas Pydantic do contexto POPs (ADR 0007).

Terminologia conforme docs/pops/CONTEXT.md: Setor é a unidade do organograma
do HSM (entidade própria, com nome e sigla únicos — a sigla é a base do
Código travado HSM_[SIGLA]-[NNN]). Não confundir com o campo livre `setor`
nem com a tabela `setores` (taxonomia do contexto Reuniões).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
