"""Schemas Pydantic da camada administrativa (super admin).

Usados pelos routers em `app.routers.admin.*`. Mantidos isolados dos schemas
do fluxo normal (`schemas.py`) para facilitar o versionamento da superficie
administrativa.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models.schemas import StatusAta, StatusPendencia, TipoReuniao, UserRole

# ─── Super Admins ────────────────────────────────────────────────────────────


class SuperAdminResponse(BaseModel):
    """Participante listado em GET /admin/super-admins."""

    id: str
    nome_completo: str
    email: str
    cargo: str | None = None
    setor: str | None = None
    role: str | None = None


class ReasonRequest(BaseModel):
    """Body padrao para acoes administrativas criticas — exige motivo."""

    reason: str = Field(..., min_length=1, max_length=1000)


# ─── Logs (audit_log viewer) ─────────────────────────────────────────────────


class AuditLogRow(BaseModel):
    """Linha do audit_log retornada pela API."""

    id: str
    timestamp: datetime
    actor_id: str | None = None
    actor_email: str
    action: str
    target_type: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    reason: str | None = None


# ─── Usuarios (CRUD admin cross-user) ────────────────────────────────────────


class AdminUsuarioResponse(BaseModel):
    """Participante retornado pelos endpoints de /admin/usuarios.

    Inclui campos administrativos (is_super_admin, ativo) que o schema
    publico nem sempre expoe ao frontend.

    nome_completo e email sao Optional porque participantes externos
    (criados pelo resolver STT) podem ter email=NULL; /admin/usuarios e
    justamente a tela para gerenciar esses casos, entao precisam aparecer.
    """

    id: str
    nome_completo: str | None = None
    email: str | None = None
    cargo: str | None = None
    area: str | None = None
    setor: str | None = None
    role: str | None = None
    ativo: bool = True
    is_externo: bool = False
    is_super_admin: bool = False
    auth_user_id: str | None = None
    data_cadastro: date | None = None


class AdminUsuarioCreate(BaseModel):
    """Payload de POST /admin/usuarios — cria um novo participante.

    is_super_admin NAO e aceito aqui (gerenciado por /admin/super-admins).
    """

    nome_completo: str = Field(..., min_length=1, max_length=255)
    email: EmailStr = Field(..., max_length=320)
    cargo: str = Field(..., min_length=1, max_length=255)
    area: str | None = Field(None, max_length=255)
    setor: str | None = Field(None, max_length=255)
    role: UserRole = UserRole.COORDENADOR
    is_externo: bool = False
    ativo: bool = True


class AdminUsuarioUpdate(BaseModel):
    """Payload de PATCH /admin/usuarios/{id}. Todos os campos opcionais.

    is_super_admin NAO e aceito aqui — gerenciado por /admin/super-admins.
    """

    nome_completo: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = Field(None, max_length=320)
    cargo: str | None = Field(None, min_length=1, max_length=255)
    area: str | None = Field(None, max_length=255)
    setor: str | None = Field(None, max_length=255)
    role: UserRole | None = None
    is_externo: bool | None = None
    ativo: bool | None = None
    reason: str | None = Field(None, max_length=1000)


class AdminUsuarioDeleteRequest(BaseModel):
    """Body de DELETE /admin/usuarios/{id}. Motivo obrigatorio."""

    reason: str = Field(..., min_length=1, max_length=1000)


class AdminResetPasswordRequest(BaseModel):
    """Body de POST /admin/usuarios/{id}/reset-password. Motivo obrigatorio.

    Se `new_password` for omitido, o backend gera uma senha aleatoria.
    """

    reason: str = Field(..., min_length=1, max_length=1000)
    new_password: str | None = Field(None, min_length=8, max_length=128)


class AdminResetPasswordResponse(BaseModel):
    """Resposta do reset-password — inclui a senha nova (exibir so 1 vez)."""

    participante_id: str
    email: str
    new_password: str


class AdminUsuarioDetalhe(BaseModel):
    """Resposta de GET /admin/usuarios/{id} — dados + ultimos 20 logs."""

    usuario: AdminUsuarioResponse
    audit_logs: list[AuditLogRow] = Field(default_factory=list)


# ─── Force Reuniao ───────────────────────────────────────────────────────────


class ForceStatusReuniaoRequest(BaseModel):
    """Body do PATCH /reunioes/{id}/force-status — forca transicao de status."""

    novo_status: StatusAta
    reason: str = Field(..., min_length=1, max_length=1000)


class ForceEditReuniaoRequest(BaseModel):
    """Body do PATCH /reunioes/{id}/force — edicao irrestrita por super admin.

    Todos os campos sao opcionais; so os enviados sao atualizados.
    Motivo obrigatorio.
    """

    titulo: str | None = Field(None, max_length=255)
    data: date | None = None
    hora_inicio: time | None = None
    hora_fim: time | None = None
    tipo: TipoReuniao | None = None
    objetivo: str | None = Field(None, max_length=500)
    facilitador_id: str | None = None
    participante_ids: list[str] | None = None
    reason: str = Field(..., min_length=1, max_length=1000)


# ─── Force Pendencia ─────────────────────────────────────────────────────────


class ForceEditPendenciaRequest(BaseModel):
    """Body do PATCH /pendencias/{id}/force — edicao irrestrita por super admin.

    Motivo e obrigatorio apenas quando status ou responsavel_id sao alterados.
    """

    descricao_acao: str | None = Field(None, max_length=500)
    status: StatusPendencia | None = None
    responsavel_id: str | None = None
    responsavel_nome: str | None = Field(None, max_length=500)
    co_responsavel_id: str | None = None
    co_responsavel_nome: str | None = None
    prazo: date | None = None
    cargo: str | None = Field(None, max_length=255)
    setor: str | None = Field(None, max_length=255)
    meta_entregavel: str | None = Field(None, max_length=500)
    reason: str | None = Field(None, max_length=1000)


# ─── Taxonomia (setores, cargos, tipos_reuniao) ──────────────────────────────


class TaxonomyItem(BaseModel):
    """Item de uma tabela de taxonomia (setores, cargos, tipos_reuniao)."""

    id: str
    nome: str
    ativo: bool = True
    created_at: datetime
    updated_at: datetime


class TaxonomyCreatePayload(BaseModel):
    """Body de POST /admin/{setores|cargos|tipos-reuniao}."""

    nome: str = Field(..., min_length=1, max_length=200)


class TaxonomyUpdatePayload(BaseModel):
    """Body de PATCH /admin/{setores|cargos|tipos-reuniao}/{id}."""

    nome: str | None = Field(None, min_length=1, max_length=200)
    ativo: bool | None = None


class TaxonomyListResponse(BaseModel):
    """Pagina de itens de taxonomia."""

    data: list[TaxonomyItem]
    total: int
    page: int
    limit: int


# ─── Resolver externo (merge / promote) ──────────────────────────────────────


class MergeExternoPayload(BaseModel):
    """Body de POST /admin/usuarios/{externo_id}/merge.

    Transfere todas as FKs do externo para o interno e deleta o externo
    via RPC atomica `merge_participante_externo`. Motivo obrigatorio.
    """

    interno_id: str = Field(..., min_length=1, max_length=10)
    reason: str = Field(..., min_length=1, max_length=1000)


class MergeExternoResult(BaseModel):
    """Resultado do merge — contadores por tabela afetada (para UX)."""

    externo_id: str
    interno_id: str
    reuniao_participantes_moved: int
    reuniao_participantes_dropped: int
    reunioes_facilitador: int
    reunioes_importado_por: int
    pendencias_responsavel: int
    pendencias_co_responsavel: int
    comentarios_autor: int
    comentarios_mencoes: int
    notificacoes: int


class PromoteExternoPayload(BaseModel):
    """Body de PATCH /admin/usuarios/{externo_id}/promote.

    Converte externo em interno (is_externo=false, ativo=true),
    preenchendo dados faltantes. O envio de senha/convite e uma acao
    separada (reset-password) — promote nao cria auth user sozinho.
    """

    email: EmailStr | None = Field(None, max_length=320)
    cargo: str | None = Field(None, min_length=1, max_length=255)
    setor: str | None = Field(None, max_length=255)
    area: str | None = Field(None, max_length=255)
    role: UserRole | None = None
    ativo: bool | None = None
    reason: str | None = Field(None, max_length=1000)
