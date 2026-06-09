from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

# === Enums ===


class UserRole(StrEnum):
    DIRETOR = "diretor"
    PRESIDENTE = "presidente"
    GERENTE = "gerente"
    COORDENADOR = "coordenador"


class StatusAta(StrEnum):
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
    APROVADA = "APROVADA"
    CANCELADA = "CANCELADA"
    MIGRADA = "MIGRADA"


class StatusPendencia(StrEnum):
    PENDENTE = "PENDENTE"
    EM_PROGRESSO = "EM_PROGRESSO"
    CONCLUIDO = "CONCLUIDO"
    ATRASADO = "ATRASADO"
    CANCELADO = "CANCELADO"
    REPACTUADA = "REPACTUADA"


class TipoReuniao(StrEnum):
    DIRETORIA = "Diretoria"
    GERENCIAL = "Gerencial"
    COORDENACAO = "Coordenação"
    MENSAL = "Mensal"
    EXTRAORDINARIA = "Extraordinária"


class FonteTranscricao(StrEnum):
    FIREFLIES = "FIREFLIES"
    MOCK = "MOCK"
    IMPORTACAO_LEGADA = "IMPORTACAO_LEGADA"


# === Participante ===


class ParticipanteBase(BaseModel):
    nome_completo: str = Field(..., max_length=255)
    cargo: str = Field(..., max_length=255)
    email: str = Field(..., max_length=320)
    area: str | None = Field(None, max_length=255)
    setor: str | None = Field(None, max_length=255)
    role: UserRole = UserRole.COORDENADOR


class ParticipanteCreate(ParticipanteBase):
    pass


class ParticipanteResponse(BaseModel):
    """Response, role e cargo podem ser nulos pra secretárias."""

    id: str
    nome_completo: str
    cargo: str | None = None
    email: str
    area: str | None = None
    setor: str | None = None
    role: UserRole | None = None
    ativo: bool = True
    is_externo: bool = False
    is_super_admin: bool = False
    access_profile: Literal["regular", "secretaria", "super_admin"] = "regular"
    data_cadastro: date | None = None


class FacilitadorOption(BaseModel):
    """Resposta enxuta para o filtro 'Facilitador' das telas de reunião/pendência.

    Lista apenas participantes que JÁ FORAM facilitadores em alguma reunião
    viva (deleted_at IS NULL). Mantém payload pequeno: nada de email/cargo.
    """

    id: str
    nome_completo: str
    setor: str | None = None
    is_externo: bool = False
    ativo: bool = True


# === Reunião ===


class ReuniaoBase(BaseModel):
    data: date
    tipo: TipoReuniao | None = None
    objetivo: str | None = Field(None, max_length=500)


class UploadTranscricaoRequest(ReuniaoBase):
    titulo: str = Field(..., max_length=255)


class ReuniaoResponse(ReuniaoBase):
    id_reuniao: str
    hora_inicio: time | None = None
    hora_fim: time | None = None
    facilitador_id: str | None = None
    setor: str | None = None
    status_ata: StatusAta = StatusAta.PROCESSANDO
    total_acoes: int = 0
    acoes_concluidas: int = 0
    fonte: FonteTranscricao = FonteTranscricao.MOCK
    url_pdf_preliminar: str | None = None
    url_pdf_assinado: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id_grupo_recorrencia: str | None = None
    nome_grupo_recorrencia: str | None = None


# === Agendamento ===


class AgendarReuniaoRequest(BaseModel):
    titulo: str = Field(..., max_length=255)
    data: date
    hora_inicio: time | None = None
    hora_fim: time | None = None
    tipo: TipoReuniao | None = None
    objetivo: str | None = Field(None, max_length=500)
    facilitador_id: str | None = Field(None, min_length=1, max_length=10)
    participante_ids: list[str] = []
    id_grupo_recorrencia: str | None = None
    nome_grupo_recorrencia: str | None = Field(None, max_length=255)


class EditarReuniaoRequest(BaseModel):
    """Partial update, todos os campos opcionais."""

    titulo: str | None = Field(None, max_length=255)
    data: date | None = None
    hora_inicio: time | None = None
    hora_fim: time | None = None
    tipo: TipoReuniao | None = None
    objetivo: str | None = Field(None, max_length=500)
    facilitador_id: str | None = Field(None, min_length=1, max_length=10)


class AdicionarParticipantesRequest(BaseModel):
    participante_ids: list[str]


# === Nota ===


class NotaCreate(BaseModel):
    corpo: str = Field(..., min_length=1, max_length=20000)


class NotaUpdate(BaseModel):
    corpo: str = Field(..., min_length=1, max_length=20000)


class NotaResponse(BaseModel):
    id: str
    corpo: str
    autor_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# === Pendência ===


class PendenciaBase(BaseModel):
    descricao_acao: str = Field(..., max_length=500)
    responsavel_nome: str | None = Field(None, max_length=500)
    cargo: str | None = Field(None, max_length=255)
    prazo: date | None = None
    meta_entregavel: str | None = Field(None, max_length=500)


class PendenciaResponse(PendenciaBase):
    id_acao: str
    # Origem: exatamente uma preenchida — Reunião (ASSINADA/APROVADA) ou Nota (ADR 0004).
    id_reuniao: str | None = None
    id_nota: str | None = None
    responsavel_id: str | None = None
    responsavel_is_externo: bool | None = None
    co_responsavel_id: str | None = None
    co_responsavel_nome: str | None = None
    status: StatusPendencia = StatusPendencia.PENDENTE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PendenciaUpdate(BaseModel):
    status: StatusPendencia | None = None
    descricao_acao: str | None = Field(None, max_length=500)
    responsavel_id: str | None = None
    responsavel_nome: str | None = Field(None, max_length=500)
    co_responsavel_id: str | None = None
    co_responsavel_nome: str | None = None
    prazo: date | None = None
    cargo: str | None = Field(None, max_length=255)
    meta_entregavel: str | None = Field(None, max_length=500)


class PendenciaNotaCreate(BaseModel):
    """Pendência adicionada à mão dentro de uma Nota (issue #33): descrição,
    responsável escolhido do cadastro (ou nome livre, para externo) e prazo."""

    descricao_acao: str = Field(..., min_length=1, max_length=500)
    responsavel_id: str | None = Field(None, max_length=10)
    responsavel_nome: str | None = Field(None, max_length=500)
    prazo: date | None = None


class PendenciasNotaCreateRequest(BaseModel):
    pendencias: list[PendenciaNotaCreate] = Field(..., min_length=1)


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
    created_at: datetime | None = None
    updated_at: datetime | None = None


# === Notificação ===


class TipoNotificacao(StrEnum):
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
    mensagem: str | None = None
    referencia_id: str | None = None
    lida: bool = False
    created_at: datetime | None = None


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
    section_context: str | None = None
    current_plan: list[CorrectionItem] = Field(default_factory=list)


class ChatCorrecaoResponse(BaseModel):
    reply: str
    correction_plan: list[CorrectionItem]


class QuadroAtribuicaoUpdate(BaseModel):
    """Body do PATCH /reunioes/{id_reuniao}/quadro-atribuicoes/{index}.

    Edita um item do `json_ata.quadro_atribuicoes` antes das pendências serem criadas
    (status AGUARDANDO_VALIDACAO). Substitui a edição livre por chat pra o caso
    específico do responsável da atribuição.

    Quando `responsavel_participante_id` é fornecido, o backend sobrescreve
    `responsavel` e `cargo` com os dados canônicos do participante. Quando não
    vem id, `responsavel` e `cargo` são gravados como texto livre (fallback
    "Digitar livremente" do dropdown).
    """

    responsavel_participante_id: str | None = Field(default=None, min_length=1, max_length=10)
    responsavel: str | None = Field(default=None, max_length=500)
    cargo: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def ao_menos_um_campo(self) -> QuadroAtribuicaoUpdate:
        if not self.responsavel_participante_id and self.responsavel is None and self.cargo is None:
            raise ValueError("Informe responsavel_participante_id ou responsavel/cargo (texto livre)")
        return self


class NovoExternoDados(BaseModel):
    """Dados para cadastrar novo externo durante resolução de não reconhecidos.

    Email é opcional — banco aceita NULL (migration 026) e facilitador pode não
    ter o contato em mãos no momento da transcrição por áudio.
    """

    nome_completo: str = Field(..., max_length=255)
    email: EmailStr | None = Field(default=None, max_length=320)
    cargo: str | None = Field(default=None, max_length=255)


class ResolverNaoReconhecidoItem(BaseModel):
    """Resolução de UM nome identificado pela IA mas não reconhecido pelo matcher.

    Três ações possíveis:
    - `vincular`: apontar um participante já existente (interno ativo ou externo
      cadastrado). Evita duplicata quando o matcher falhou por similaridade.
    - `cadastrar_externo`: criar novo externo (comportamento legado, agora com
      email opcional).
    - `ignorar`: descartar o nome (erro de transcrição, fantasma).
    """

    nome_identificado: str = Field(
        ...,
        description="Nome como consta no JSONB participantes_nao_reconhecidos da reunião",
    )
    acao: Literal["vincular", "cadastrar_externo", "ignorar"]
    participante_id: str | None = Field(
        default=None,
        description="ID do participante existente quando acao='vincular'",
    )
    novo_externo: NovoExternoDados | None = Field(
        default=None,
        description="Dados do novo externo quando acao='cadastrar_externo'",
    )

    @model_validator(mode="after")
    def validar_payload_por_acao(self) -> ResolverNaoReconhecidoItem:
        if self.acao == "vincular" and not self.participante_id:
            raise ValueError("participante_id é obrigatório quando acao='vincular'")
        if self.acao == "cadastrar_externo" and not self.novo_externo:
            raise ValueError("novo_externo é obrigatório quando acao='cadastrar_externo'")
        return self


class ResolverParticipantesRequest(BaseModel):
    resolucoes: list[ResolverNaoReconhecidoItem]


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
    notificacoes: NotificacaoPreferences | None = None
    emails: EmailPreferences | None = None


# === Admin ===


class EmailStatusResponse(BaseModel):
    provedor_primario: str
    email_envio: str
    resend_configurado: bool
    smtp_configurado: bool


class IntegracaoStatus(BaseModel):
    nome: str
    conectado: bool
    ambiente: str | None = None
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
    hora_inicio: str | None = Field(None, max_length=5)
    hora_fim: str | None = Field(None, max_length=5)
    facilitador_id: str | None = None
    assunto: str | None = Field(None, max_length=500)
    objetivo: str | None = Field(None, max_length=500)


class ParticipanteMatchedPreview(BaseModel):
    nome: str = Field(..., max_length=255)
    participante_id: str
    cargo: str | None = None


class ParticipanteExternoPreview(BaseModel):
    nome: str = Field(..., max_length=255)
    cargo: str = Field(..., max_length=255)
    setor: str | None = Field(None, max_length=255)
    email: EmailStr | None = None


class PendenciaImportacao(BaseModel):
    acao: str = Field(..., max_length=1000)
    responsavel_nome: str = Field(..., max_length=255)
    # responsavel_id preenchido se matched; senão referencia externo por índice
    responsavel_id: str | None = None
    responsavel_externo_idx: int | None = None
    cargo: str | None = Field(None, max_length=255)
    prazo: date | None = None
    prazo_original: str | None = Field(None, max_length=100)
    meta_entregavel: str | None = Field(None, max_length=500)
    status: StatusPendencia = StatusPendencia.PENDENTE
    co_responsavel_id: str | None = None


class AtaMigradaPreview(BaseModel):
    """Response de POST /reunioes/importacao/preparar (stateless, nada persiste)."""

    arquivo_hash: str
    documento_id_origem: str | None = None
    nome_arquivo_original: str
    metadados: MetadadosImportacao
    participantes_matched: list[ParticipanteMatchedPreview] = []
    participantes_externos: list[ParticipanteExternoPreview] = []
    pendencias: list[PendenciaImportacao] = []
    registro_narrativo: str | None = None
    resumo_executivo: str | None = None
    paginas: int = 0
    is_mock: bool = False


class ConfirmarImportacaoRequest(BaseModel):
    """Body JSON do POST /reunioes/importacao/confirmar.
    Enviado junto ao arquivo PDF re-uploadado (multipart/form-data).
    """

    arquivo_hash: str
    documento_id_origem: str | None = None
    nome_arquivo_original: str
    metadados: MetadadosImportacao
    participantes_matched: list[ParticipanteMatchedPreview] = []
    participantes_externos: list[ParticipanteExternoPreview] = []
    pendencias: list[PendenciaImportacao] = []
    registro_narrativo: str | None = None
    resumo_executivo: str | None = None


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
    url_pdf: str | None = None


class CheckDuplicataResponse(BaseModel):
    duplicada: bool
    id_reuniao: str | None = None
    titulo: str | None = None
    data: date | None = None
    motivo: str | None = None  # "hash" | "documento_id"


class HistoricoImportacaoItem(BaseModel):
    """Item do histórico de importações (last N ATAs MIGRADA)."""

    id_reuniao: str
    titulo: str | None = None
    data: date | None = None
    documento_id_origem: str | None = None
    nome_arquivo_original: str | None = None
    total_pendencias: int = 0
    importado_por_id: str | None = None
    importado_por_nome: str | None = None
    importado_em: str | None = None  # ISO timestamp (created_at)
