"""Schemas Pydantic da aba Tecnologia (PRD #634, ADR 0050).

Arquivo proprio, e nao mais um bloco em `admin_schemas.py`, porque a aba
Tecnologia e um contexto inteiro (Produto, Demanda, Conversa) que cresce nas
fatias seguintes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PessoaDaAba(BaseModel):
    """Alguem com acesso a aba: participante ativo com Super admin.

    A mesma lista serve para dono de Produto, responsavel de Demanda e
    @mencao (PRD #634).
    """

    id: str
    nome_completo: str
    email: str


class ProdutoResponse(BaseModel):
    """Produto como a tela o le."""

    id: str
    nome: str
    ativo: bool
    ordem: int
    dono_id: str | None = None
    # Resolvido pelo backend: o dono pode ter deixado de ser Super admin, e ai
    # o nome dele nao estaria na lista de pessoas que a tela carrega.
    dono_nome: str | None = None


class ProdutoCreatePayload(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    dono_id: str | None = None
    ordem: int | None = None


class ProdutoUpdatePayload(BaseModel):
    """Campos ausentes ficam como estao.

    `dono_id: null` explicito no JSON tira o dono, e por isso o router olha
    `model_fields_set` em vez de tratar `None` como "nao informado".
    """

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ativo: bool | None = None
    dono_id: str | None = None
    ordem: int | None = None
