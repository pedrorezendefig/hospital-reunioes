from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.services.seguranca_do_paciente.reunioes import TipoReuniaoNsp

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
    # Reunião do Núcleo sem quórum (issue #1774, migration 153).
    NAO_INSTALADA = "NAO_INSTALADA"


class StatusPendencia(StrEnum):
    """Os quatro estados gravados (ADR 0098, decisão 4). Atrasada e
    Repactuada são calculadas: veja `situacao` na resposta."""

    PENDENTE = "PENDENTE"
    EM_PROGRESSO = "EM_PROGRESSO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"


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
    """Response, role e cargo podem ser nulos pra secretárias.

    access_profile NULL = sem papel no contexto Reuniões; perfil_pop é o eixo
    do contexto POPs (ADR 0007) — uma pessoa pode ter um, outro, ambos ou nenhum.
    """

    id: str
    nome_completo: str
    cargo: str | None = None
    email: str | None = None  # NULL para stubs externos sem email (migration 026)
    area: str | None = None
    setor: str | None = None
    role: UserRole | None = None
    ativo: bool = True
    is_externo: bool = False
    is_super_admin: bool = False
    access_profile: Literal["regular", "secretaria", "super_admin"] | None = "regular"
    perfil_pop: Literal["superadmin", "gestor_qualidade", "gerente", "coordenador"] | None = None
    # Eixo de permissão do contexto Ouvidoria (ADR 0034): quem lê o Dossiê.
    perfil_ouvidoria: Literal["ouvidor", "diretoria_executiva"] | None = None
    # Eixo de permissão de Contas médicas (ADR 0070): o menu decide por ele.
    perfil_contas_medicas: (
        Literal[
            "faturista",
            "coordenadora",
            "gestao_contas_medicas",
            "diretoria_medica",
            "diretoria_executiva",
            "credenciamento",
            "apoio_faturamento",
        ]
        | None
    ) = None
    # Segurança do Paciente (ADR 0095, decisão 4): o Acesso pleno ao NSP.
    perfil_nsp: Literal["acesso_pleno"] | None = None
    # Canal de Conduta (ADR 0097, decisão 3): quem cadastra membros do Comitê.
    perfil_conduta: Literal["cadastro_de_membros"] | None = None
    # O registro profissional da pessoa (issue #1765).
    conselho_profissional: str | None = None
    registro_profissional: str | None = None
    registro_uf: str | None = None
    # O que a pessoa alcança no módulo Segurança do Paciente. Só o `/me`
    # preenche: é com isto que o menu decide mostrar o item.
    recursos_nsp: list[str] = []
    # O papel na Ouvidoria (ADR 0099). Só o `/me` preenche: o menu mostra o
    # item e a rota abre para quem não é `nenhum`. Nulo quando o cadastro de
    # responsáveis não pôde ser lido.
    papel_ouvidoria: Literal["perfil_ouvidoria", "indice_geral", "responsavel", "nenhum"] | None = None
    # A tela Membros do Comitê de Conduta (issue #1822). Só o `/me` preenche:
    # o menu mostra o item para quem está no Comitê ou tem o perfil de cadastro.
    ve_membros_do_comite: bool = False
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
    # A lista geral também devolve a reunião do Núcleo a quem o módulo libera
    # (issue #1772), com um dos quatro tipos dele.
    tipo: TipoReuniao | TipoReuniaoNsp | None = None
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
    # Obrigatório (issue #1861), mas recusado na rota e não aqui: o 422 do
    # Pydantic vem em lista, e a Recorrência mostra só `detail` em texto.
    setor: str | None = Field(None, max_length=255)
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


# === Transcrição de voz ===


class TranscricaoResponse(BaseModel):
    """Texto transcrito do áudio ditado (issue #35) — cai editável no destino da tela."""

    texto: str


# === Pendência ===


class PendenciaBase(BaseModel):
    descricao_acao: str = Field(..., max_length=500)
    responsavel_nome: str | None = Field(None, max_length=500)
    cargo: str | None = Field(None, max_length=255)
    prazo: date | None = None
    meta_entregavel: str | None = Field(None, max_length=500)


class PendenciaResponse(PendenciaBase):
    id_acao: str
    # Origem: Reunião em estado terminal — ASSINADA ou APROVADA (ADR 0003/0011).
    id_reuniao: str | None = None
    responsavel_id: str | None = None
    responsavel_is_externo: bool | None = None
    co_responsavel_id: str | None = None
    co_responsavel_nome: str | None = None
    status: StatusPendencia = StatusPendencia.PENDENTE
    # Calculados (ADR 0098, decisão 4): aberta com prazo vencido, e há
    # Repactuação no histórico. `situacao` é o que a tela mostra.
    atrasada: bool = False
    repactuada: bool = False
    situacao: Literal["PENDENTE", "EM_PROGRESSO", "CONCLUIDO", "CANCELADO", "ATRASADO", "REPACTUADA"] = "PENDENTE"
    concluida_em: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AcaoPendenciaRequest(BaseModel):
    """Uma ação na Pendência (ADR 0098, decisão 5). A anotação é obrigatória;
    o prazo só vale em repactuar, reabrir e ajustar. Contestar, ajustar e
    recusar são a Contestação do item da Ata (issue #1870); só ajustar troca
    o responsável (`responsavel_id`, uma pessoa ativa do cadastro)."""

    comando: Literal[
        "iniciar", "anotar", "concluir", "repactuar", "cancelar", "reabrir", "contestar", "ajustar", "recusar"
    ]
    anotacao: str = Field(..., max_length=5000)
    prazo: date | None = None
    responsavel_id: str | None = Field(None, max_length=10)

    @field_validator("anotacao")
    @classmethod
    def _anotacao_com_texto(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("Escreva a anotação: toda ação na pendência pede uma.")
        return valor


class AnexoDoEvento(BaseModel):
    """Foto ou PDF anexado na conclusão (issue #1865). Abre pelo link assinado."""

    id: int
    nome: str
    tipo: str
    tamanho_bytes: int


class EventoHistoricoPendencia(BaseModel):
    id: int
    comando: str
    anotacao: str
    autor_id: str | None = None
    autor_nome: str
    status_antes: str | None = None
    status_depois: str | None = None
    prazo_antes: date | None = None
    prazo_depois: date | None = None
    # Nome de quem era e de quem passou a ser o responsável, só no ajuste que
    # trocou o responsável (issue #1870).
    responsavel_antes: str | None = None
    responsavel_depois: str | None = None
    conta_atraso: bool = False
    criado_em: datetime
    anexo: AnexoDoEvento | None = None


class HistoricoPendenciaResponse(BaseModel):
    eventos: list[EventoHistoricoPendencia]
    # Os comandos que quem pede pode dar agora (a tela mostra só esses botões).
    acoes_permitidas: list[str]
    # Se quem olha abre os anexos: responsável, Facilitador ou Super admin (#1865).
    pode_abrir_anexos: bool = False


class LinkDoAnexoResponse(BaseModel):
    url: str


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
    # Os dois que o banco aceita desde a 060 e a 116: fora daqui, a lista do
    # sino dava 500 e o painel abria vazio com o contador marcando (#1430).
    ACEITE_INTERNO = "ACEITE_INTERNO"
    CONTAS_MEDICAS = "CONTAS_MEDICAS"
    # A Conversa da Demanda (129, issue #1537): a referencia e a Demanda.
    TECNOLOGIA = "TECNOLOGIA"
    # A mudança no Comitê de Conduta (184, issue #1822): sem referência.
    CONDUTA = "CONDUTA"


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
    # Sem `max_length`: o teto do tamanho mora em `teto_dos_chats` (issue #893),
    # para a recusa chegar à tela como frase, e não como `detail` em lista.
    role: Literal["user", "assistant"]
    content: str


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
    `responsavel` e `cargo` com os dados canônicos do participante e grava o
    vínculo (`responsavel_id`) no item (ADR 0008). Quando não vem id,
    `responsavel` e `cargo` são gravados como texto livre (fallback "Digitar
    livremente" do dropdown) e o vínculo anterior é limpo.

    `tipo` e `frequencia` (issue #1872) classificam a linha como Ação, Rotina
    ou Processo sem mexer no responsável. A frequência só vale na Rotina.
    """

    responsavel_participante_id: str | None = Field(default=None, min_length=1, max_length=10)
    responsavel: str | None = Field(default=None, max_length=500)
    cargo: str | None = Field(default=None, max_length=255)
    tipo: Literal["ACAO", "ROTINA", "PROCESSO"] | None = None
    frequencia: Literal["SEMANAL", "QUINZENAL", "MENSAL"] | None = None

    def mexe_no_responsavel(self) -> bool:
        return bool(self.responsavel_participante_id) or self.responsavel is not None or self.cargo is not None

    @model_validator(mode="after")
    def ao_menos_um_campo(self) -> QuadroAtribuicaoUpdate:
        if not self.mexe_no_responsavel() and not ({"tipo", "frequencia"} & self.model_fields_set):
            raise ValueError("Informe responsavel_participante_id, responsavel/cargo (texto livre), tipo ou frequencia")
        return self


class ExcluirParticipanteAtaRequest(BaseModel):
    """Body do POST /reunioes/{id}/ata-participantes/excluir (ADR 0023).

    Exclui, pelo nome canônico exibido na Ata, um participante de
    `json_ata.participantes` e o vínculo espelhado em `reuniao_participantes`.
    """

    nome: str = Field(..., min_length=1, max_length=255)


class AdicionarParticipanteAtaRequest(BaseModel):
    """Body do POST /reunioes/{id}/ata-participantes (ADR 0023).

    Adiciona à lista da Ata um participante do cadastro (mesmo contrato de
    `vincular` da resolução): grava em `json_ata.participantes` e faz upsert
    idempotente no roster.
    """

    participante_id: str = Field(..., min_length=1, max_length=10)


# === Ata Guiada (ADR 0005) ===


class AtaGuiadaConcluirRequest(BaseModel):
    """Body do POST /reunioes/{id}/ata-guiada/concluir.

    O `rascunho` é o `json_ata` enxuto montado na conversa com o agente:
    `resumo_executivo` (texto) + `quadro_atribuicoes` (lista de ações). Só esses
    dois campos são persistidos — o shape completo da Ata por Transcrição
    (participantes/discussao/objetivo/PDF) não se aplica à Ata Guiada.
    """

    rascunho: dict = Field(default_factory=dict)


class AtaGuiadaChatRequest(BaseModel):
    """Body do POST /reunioes/{id}/ata-guiada/chat (stateless).

    Carrega o rascunho enxuto atual (`json_ata` parcial) + o histórico da conversa;
    o backend devolve a resposta do agente e o rascunho atualizado. O estado vive no
    frontend entre os turnos — só persiste no `concluir`.

    `documento_apoio` (ADR 0006) é o texto opcional de um Documento de apoio anexado,
    reenviado a cada turno como contexto sob demanda (o frontend o guarda em memória).
    """

    rascunho: dict = Field(default_factory=dict)
    messages: list[ChatMessageSchema]
    # Seção apontada pelo Facilitador (⌖ — ADR 0006, #58): o Resumo ou uma ação
    # específica. Espelha o `section_context` do ChatCorrecaoRequest.
    section_context: str | None = None
    documento_apoio: str | None = None


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
