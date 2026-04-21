from __future__ import annotations
from datetime import date, time, datetime
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, EmailStr, Field


# === Enums ===

class UserRole(str, Enum):
    DIRETOR = "diretor"
    PRESIDENTE = "presidente"
    GERENTE = "gerente"
    COORDENADOR = "coordenador"


class StatusAta(str, Enum):
    PROGRAMADA = "PROGRAMADA"
    PROCESSANDO = "PROCESSANDO"
    ERRO = "ERRO"
    ERRO_UPLOAD_TRANSCRICAO = "ERRO_UPLOAD_TRANSCRICAO"
    ERRO_GERACAO_PDF = "ERRO_GERACAO_PDF"
    ERRO_ENVIO_EMAIL = "ERRO_ENVIO_EMAIL"
    AGUARDANDO_RESOLUCAO = "AGUARDANDO_RESOLUCAO"
    AGUARDANDO_VALIDACAO = "AGUARDANDO_VALIDACAO"
    AGUARDANDO_ASSINATURA = "AGUARDANDO_ASSINATURA"
    ASSINADA = "ASSINADA"
    CANCELADA = "CANCELADA"
    MIGRADA = "MIGRADA"


class StatusPendencia(str, Enum):
    PENDENTE = "PENDENTE"
    EM_PROGRESSO = "EM_PROGRESSO"
    CONCLUIDO = "CONCLUIDO"
    ATRASADO = "ATRASADO"
    CANCELADO = "CANCELADO"
    REPACTUADA = "REPACTUADA"


class TipoReuniao(str, Enum):
    DIRETORIA = "Diretoria"
    GERENCIAL = "Gerencial"
    COORDENACAO = "Coordenação"
    MENSAL = "Mensal"
    EXTRAORDINARIA = "Extraordinária"


class FonteTranscricao(str, Enum):
    FIREFLIES = "FIREFLIES"
    MOCK = "MOCK"
    IMPORTACAO_LEGADA = "IMPORTACAO_LEGADA"


# === Participante ===

class ParticipanteBase(BaseModel):
    nome_completo: str = Field(..., max_length=255)
    cargo: str = Field(..., max_length=255)
    email: str = Field(..., max_length=320)
    area: Optional[str] = Field(None, max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    role: UserRole = UserRole.COORDENADOR


class ParticipanteCreate(ParticipanteBase):
    pass


class ParticipanteResponse(ParticipanteBase):
    id: str
    ativo: bool = True
    is_externo: bool = False
    is_super_admin: bool = False
    data_cadastro: Optional[date] = None


# === Reunião ===

class ReuniaoBase(BaseModel):
    data: date
    tipo: Optional[TipoReuniao] = None
    objetivo: Optional[str] = Field(None, max_length=500)


class UploadTranscricaoRequest(ReuniaoBase):
    titulo: str = Field(..., max_length=255)


class ReuniaoResponse(ReuniaoBase):
    id_reuniao: str
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    facilitador_id: Optional[str] = None
    setor: Optional[str] = None
    local: Optional[str] = None
    status_ata: StatusAta = StatusAta.PROCESSANDO
    total_acoes: int = 0
    acoes_concluidas: int = 0
    fonte: FonteTranscricao = FonteTranscricao.MOCK
    url_pdf_preliminar: Optional[str] = None
    url_pdf_assinado: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id_grupo_recorrencia: Optional[str] = None
    nome_grupo_recorrencia: Optional[str] = None


# === Agendamento ===

class AgendarReuniaoRequest(BaseModel):
    titulo: str = Field(..., max_length=255)
    data: date
    hora_inicio: Optional[time] = None
    tipo: Optional[TipoReuniao] = None
    objetivo: Optional[str] = Field(None, max_length=500)
    local: Optional[str] = Field(None, max_length=255)
    participante_ids: list[str] = []
    id_grupo_recorrencia: Optional[str] = None
    nome_grupo_recorrencia: Optional[str] = Field(None, max_length=255)


class EditarReuniaoRequest(BaseModel):
    """Partial update — todos os campos opcionais."""
    titulo: Optional[str] = Field(None, max_length=255)
    data: Optional[date] = None
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    tipo: Optional[TipoReuniao] = None
    objetivo: Optional[str] = Field(None, max_length=500)
    local: Optional[str] = Field(None, max_length=255)


class AdicionarParticipantesRequest(BaseModel):
    participante_ids: list[str]


# === Pendência ===

class PendenciaBase(BaseModel):
    descricao_acao: str = Field(..., max_length=500)
    responsavel_nome: Optional[str] = Field(None, max_length=500)
    cargo: Optional[str] = Field(None, max_length=255)
    prazo: Optional[date] = None
    meta_entregavel: Optional[str] = Field(None, max_length=500)


class PendenciaResponse(PendenciaBase):
    id_acao: str
    id_reuniao: str
    responsavel_id: Optional[str] = None
    responsavel_is_externo: Optional[bool] = None
    co_responsavel_id: Optional[str] = None
    co_responsavel_nome: Optional[str] = None
    status: StatusPendencia = StatusPendencia.PENDENTE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PendenciaUpdate(BaseModel):
    status: Optional[StatusPendencia] = None
    descricao_acao: Optional[str] = Field(None, max_length=500)
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = Field(None, max_length=500)
    co_responsavel_id: Optional[str] = None
    co_responsavel_nome: Optional[str] = None
    prazo: Optional[date] = None
    cargo: Optional[str] = Field(None, max_length=255)
    meta_entregavel: Optional[str] = Field(None, max_length=500)


class PendenciaStats(BaseModel):
    pendente: int = 0
    em_progresso: int = 0
    concluido: int = 0
    atrasado: int = 0
    cancelado: int = 0
    repactuada: int = 0
    total: int = 0


# === Comentário ===

class ComentarioCreate(BaseModel):
    conteudo: str = Field(..., max_length=5000)


class ComentarioResponse(BaseModel):
    id: str
    id_acao: str
    autor_id: str
    autor_nome: str
    conteudo: str
    mencoes: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# === Notificação ===

class TipoNotificacao(str, Enum):
    MENCAO = "MENCAO"
    STATUS_ALTERADO = "STATUS_ALTERADO"
    COMENTARIO = "COMENTARIO"
    PRAZO_PROXIMO = "PRAZO_PROXIMO"
    RESPONSAVEL_ATRIBUIDO = "RESPONSAVEL_ATRIBUIDO"


class NotificacaoResponse(BaseModel):
    id: str
    destinatario_id: str
    tipo: TipoNotificacao
    titulo: str
    mensagem: Optional[str] = None
    referencia_id: Optional[str] = None
    lida: bool = False
    created_at: Optional[datetime] = None


class NotificacaoCount(BaseModel):
    nao_lidas: int = 0


# === Health ===

class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


# === Chat Correção (ATA) ===

class ChatMessageSchema(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=5000)


class CorrectionItem(BaseModel):
    field: str = Field(..., max_length=255)
    action: str = Field(..., max_length=255)
    description: str = Field(..., max_length=500)


class ChatCorrecaoRequest(BaseModel):
    messages: list[ChatMessageSchema]
    section_context: Optional[str] = None


class ChatCorrecaoResponse(BaseModel):
    reply: str
    correction_plan: list[CorrectionItem]


# === Registro de Participantes ===

class RegistrarParticipanteRequest(BaseModel):
    nome_completo: str = Field(..., max_length=255)
    email: EmailStr = Field(..., max_length=320)
    cargo: str = Field(..., max_length=255)  # validated against CARGOS_MAP to derive setor, area, role


class ResolverParticipantesRequest(BaseModel):
    participantes: list[RegistrarParticipanteRequest]


# === Perfil ===

class PerfilStats(BaseModel):
    reunioes: int = 0
    pendencias_ativas: int = 0
    concluidas: int = 0
    no_prazo_percentual: float = 0.0


# === Preferências ===

class NotificacaoPreferences(BaseModel):
    mencao: bool = True
    prazo_proximo: bool = True
    comentario: bool = True
    responsavel_atribuido: bool = True


class EmailPreferences(BaseModel):
    """Placeholder vazio — triggers de email customizados serao adicionados conforme necessario."""
    pass


class UserPreferencesResponse(BaseModel):
    notificacoes: NotificacaoPreferences = NotificacaoPreferences()
    emails: EmailPreferences = EmailPreferences()


class UserPreferencesUpdate(BaseModel):
    notificacoes: Optional[NotificacaoPreferences] = None
    emails: Optional[EmailPreferences] = None


# === Admin ===

class PasseResponse(BaseModel):
    passe_mascarado: str
    passe: str
    comprimento: int


class EmailStatusResponse(BaseModel):
    provedor_primario: str
    email_envio: str
    resend_configurado: bool
    smtp_configurado: bool


class IntegracaoStatus(BaseModel):
    nome: str
    conectado: bool
    ambiente: Optional[str] = None
    descricao: str


class TestResult(BaseModel):
    sucesso: bool
    mensagem: str


# === Importação de ATA antiga ===

class MetadadosImportacao(BaseModel):
    """Metadados da reunião migrada — editáveis pelo usuário no preview."""
    titulo: str = Field(..., max_length=255)
    tipo: TipoReuniao = TipoReuniao.COORDENACAO
    data: date
    hora_inicio: Optional[str] = Field(None, max_length=5)
    hora_fim: Optional[str] = Field(None, max_length=5)
    facilitador_id: Optional[str] = None
    assunto: Optional[str] = Field(None, max_length=500)
    objetivo: Optional[str] = Field(None, max_length=500)


class ParticipanteMatchedPreview(BaseModel):
    nome: str = Field(..., max_length=255)
    participante_id: str
    cargo: Optional[str] = None


class ParticipanteExternoPreview(BaseModel):
    nome: str = Field(..., max_length=255)
    cargo: str = Field(..., max_length=255)
    setor: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None


class PendenciaImportacao(BaseModel):
    acao: str = Field(..., max_length=1000)
    responsavel_nome: str = Field(..., max_length=255)
    # responsavel_id preenchido se matched; senão referencia externo por índice
    responsavel_id: Optional[str] = None
    responsavel_externo_idx: Optional[int] = None
    cargo: Optional[str] = Field(None, max_length=255)
    prazo: Optional[date] = None
    prazo_original: Optional[str] = Field(None, max_length=100)
    meta_entregavel: Optional[str] = Field(None, max_length=500)
    status: StatusPendencia = StatusPendencia.PENDENTE
    co_responsavel_id: Optional[str] = None


class AtaMigradaPreview(BaseModel):
    """Response de POST /reunioes/importacao/preparar (stateless, nada persiste)."""
    arquivo_hash: str
    documento_id_origem: Optional[str] = None
    nome_arquivo_original: str
    metadados: MetadadosImportacao
    participantes_matched: list[ParticipanteMatchedPreview] = []
    participantes_externos: list[ParticipanteExternoPreview] = []
    pendencias: list[PendenciaImportacao] = []
    registro_narrativo: Optional[str] = None
    resumo_executivo: Optional[str] = None
    paginas: int = 0
    is_mock: bool = False


class ConfirmarImportacaoRequest(BaseModel):
    """Body JSON do POST /reunioes/importacao/confirmar.
    Enviado junto ao arquivo PDF re-uploadado (multipart/form-data).
    """
    arquivo_hash: str
    documento_id_origem: Optional[str] = None
    nome_arquivo_original: str
    metadados: MetadadosImportacao
    participantes_matched: list[ParticipanteMatchedPreview] = []
    participantes_externos: list[ParticipanteExternoPreview] = []
    pendencias: list[PendenciaImportacao] = []
    registro_narrativo: Optional[str] = None
    resumo_executivo: Optional[str] = None


class PendenciaIgnorada(BaseModel):
    """Pendência que não pôde ser persistida na confirmação de importação.

    `motivo` atualmente assume:
      - "sem_responsavel": nem responsavel_id nem externo resolvido
      - "responsavel_nao_encontrado": id informado não existe em participantes
    """
    acao: str
    motivo: str


class ConfirmarImportacaoResponse(BaseModel):
    id_reuniao: str
    total_pendencias: int
    total_externos_criados: int
    total_externos_stub: int = 0
    pendencias_ignoradas: list[PendenciaIgnorada] = []
    url_pdf: Optional[str] = None


class CheckDuplicataResponse(BaseModel):
    duplicada: bool
    id_reuniao: Optional[str] = None
    titulo: Optional[str] = None
    data: Optional[date] = None
    motivo: Optional[str] = None  # "hash" | "documento_id"


class HistoricoImportacaoItem(BaseModel):
    """Item do histórico de importações (last N ATAs MIGRADA)."""
    id_reuniao: str
    titulo: Optional[str] = None
    data: Optional[date] = None
    documento_id_origem: Optional[str] = None
    nome_arquivo_original: Optional[str] = None
    total_pendencias: int = 0
    importado_por_id: Optional[str] = None
    importado_por_nome: Optional[str] = None
    importado_em: Optional[str] = None  # ISO timestamp (created_at)
