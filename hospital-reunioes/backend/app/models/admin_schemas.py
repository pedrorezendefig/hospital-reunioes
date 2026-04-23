"""Schemas Pydantic da camada administrativa (super admin).

Usados pelos routers em `app.routers.admin.*`. Mantidos isolados dos schemas
do fluxo normal (`schemas.py`) para facilitar o versionamento da superficie
administrativa.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.schemas import StatusAta, StatusPendencia, TipoReuniao, UserRole


# ─── Super Admins ────────────────────────────────────────────────────────────


class SuperAdminResponse(BaseModel):
    """Participante listado em GET /admin/super-admins."""

    id: str
    nome_completo: str
    email: str
    cargo: Optional[str] = None
    setor: Optional[str] = None
    role: Optional[str] = None


class ReasonRequest(BaseModel):
    """Body padrao para acoes administrativas criticas — exige motivo."""

    reason: str = Field(..., min_length=1, max_length=1000)


# ─── Logs (audit_log viewer) ─────────────────────────────────────────────────


class AuditLogRow(BaseModel):
    """Linha do audit_log retornada pela API."""

    id: str
    timestamp: datetime
    actor_id: Optional[str] = None
    actor_email: str
    action: str
    target_type: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    reason: Optional[str] = None


class AuditLogPage(BaseModel):
    """Pagina paginada de linhas do audit_log."""

    total: int
    rows: list[AuditLogRow]
    limit: int
    offset: int


# ─── Acoes em massa ──────────────────────────────────────────────────────────


class BulkReuniaoRequest(BaseModel):
    """Body de acoes em massa sobre reunioes (reenvio ClickSign, reprocessar IA)."""

    reuniao_ids: list[str] = Field(..., min_length=1, max_length=500)
    reason: Optional[str] = Field(default=None, max_length=1000)


class BulkEmailRequest(BaseModel):
    """Body de disparo de email em massa a participantes."""

    participante_ids: list[str] = Field(..., min_length=1, max_length=500)
    assunto: str = Field(..., min_length=1, max_length=300)
    corpo: str = Field(..., min_length=1, max_length=20000)
    reason: Optional[str] = Field(default=None, max_length=1000)


class BulkFailure(BaseModel):
    """Item com falha em operacao em massa."""

    id: str
    erro: str


class BulkResult(BaseModel):
    """Resumo de uma acao em massa."""

    sucessos: int
    falhas: list[BulkFailure] = Field(default_factory=list)


class BulkJobAccepted(BaseModel):
    """Resposta 202 de POST /admin/bulk/* — job agendado em background."""

    job_id: str
    status: str = "pending"
    total: int


class BulkJobStatus(BaseModel):
    """Linha de bulk_jobs retornada por GET /admin/bulk/jobs/{id}."""

    id: str
    created_at: datetime
    updated_at: datetime
    actor_id: Optional[str] = None
    actor_email: str
    job_type: str
    status: str
    target_ids: list[str] = Field(default_factory=list)
    total: int
    sucessos: int
    falhas: list[BulkFailure] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class BulkJobList(BaseModel):
    """Pagina simples de jobs retornada por GET /admin/bulk/jobs."""

    total: int
    rows: list[BulkJobStatus]
    limit: int
    offset: int


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
    nome_completo: Optional[str] = None
    email: Optional[str] = None
    cargo: Optional[str] = None
    area: Optional[str] = None
    setor: Optional[str] = None
    role: Optional[str] = None
    ativo: bool = True
    is_externo: bool = False
    is_super_admin: bool = False
    auth_user_id: Optional[str] = None
    data_cadastro: Optional[date] = None


class AdminUsuarioCreate(BaseModel):
    """Payload de POST /admin/usuarios — cria um novo participante.

    is_super_admin NAO e aceito aqui (gerenciado por /admin/super-admins).
    """

    nome_completo: str = Field(..., min_length=1, max_length=255)
    email: EmailStr = Field(..., max_length=320)
    cargo: str = Field(..., min_length=1, max_length=255)
    area: Optional[str] = Field(None, max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    role: UserRole = UserRole.COORDENADOR
    is_externo: bool = False
    ativo: bool = True


class AdminUsuarioUpdate(BaseModel):
    """Payload de PATCH /admin/usuarios/{id}. Todos os campos opcionais.

    is_super_admin NAO e aceito aqui — gerenciado por /admin/super-admins.
    """

    nome_completo: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None, max_length=320)
    cargo: Optional[str] = Field(None, min_length=1, max_length=255)
    area: Optional[str] = Field(None, max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    role: Optional[UserRole] = None
    is_externo: Optional[bool] = None
    ativo: Optional[bool] = None
    reason: Optional[str] = Field(None, max_length=1000)


class AdminUsuarioDeleteRequest(BaseModel):
    """Body de DELETE /admin/usuarios/{id}. Motivo obrigatorio."""

    reason: str = Field(..., min_length=1, max_length=1000)


class AdminResetPasswordRequest(BaseModel):
    """Body de POST /admin/usuarios/{id}/reset-password. Motivo obrigatorio.

    Se `new_password` for omitido, o backend gera uma senha aleatoria.
    """

    reason: str = Field(..., min_length=1, max_length=1000)
    new_password: Optional[str] = Field(None, min_length=8, max_length=128)


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

    titulo: Optional[str] = Field(None, max_length=255)
    data: Optional[date] = None
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    tipo: Optional[TipoReuniao] = None
    objetivo: Optional[str] = Field(None, max_length=500)
    local: Optional[str] = Field(None, max_length=255)
    facilitador_id: Optional[str] = None
    participante_ids: Optional[list[str]] = None
    reason: str = Field(..., min_length=1, max_length=1000)


# ─── Force Pendencia ─────────────────────────────────────────────────────────


class ForceEditPendenciaRequest(BaseModel):
    """Body do PATCH /pendencias/{id}/force — edicao irrestrita por super admin.

    Motivo e obrigatorio apenas quando status ou responsavel_id sao alterados.
    """

    descricao_acao: Optional[str] = Field(None, max_length=500)
    status: Optional[StatusPendencia] = None
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = Field(None, max_length=500)
    co_responsavel_id: Optional[str] = None
    co_responsavel_nome: Optional[str] = None
    prazo: Optional[date] = None
    cargo: Optional[str] = Field(None, max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    meta_entregavel: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=1000)


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

    nome: Optional[str] = Field(None, min_length=1, max_length=200)
    ativo: Optional[bool] = None


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

    email: Optional[EmailStr] = Field(None, max_length=320)
    cargo: Optional[str] = Field(None, min_length=1, max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    area: Optional[str] = Field(None, max_length=255)
    role: Optional[UserRole] = None
    ativo: Optional[bool] = None
    reason: Optional[str] = Field(None, max_length=1000)


# ─── Signup requests (CRUD admin) ────────────────────────────────────────────


class SignupRequestItem(BaseModel):
    """Linha de signup_requests retornada para o super-admin."""

    id: str
    nome_completo: str
    email: str
    cargo: Optional[str] = None
    area: Optional[str] = None
    setor: Optional[str] = None
    role: Optional[str] = None
    confirmado: bool = False
    expires_at: Optional[datetime] = None
    created_at: datetime


class SignupRequestListResponse(BaseModel):
    """Pagina de signup_requests."""

    data: list[SignupRequestItem]
    total: int
    page: int
    limit: int
