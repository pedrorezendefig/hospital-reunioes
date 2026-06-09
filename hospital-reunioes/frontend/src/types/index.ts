// === Enums ===

export type UserRole = "diretor" | "presidente" | "gerente" | "coordenador";

export type AccessProfile = "regular" | "secretaria" | "super_admin";

export const ACCESS_PROFILE_LABELS: Record<AccessProfile, string> = {
  regular: "Regular",
  secretaria: "Secretária",
  super_admin: "Super Admin",
};

export type StatusAta =
  | "PROGRAMADA"
  | "PROCESSANDO"
  | "AGUARDANDO_RESOLUCAO"
  | "ERRO"
  | "ERRO_UPLOAD_TRANSCRICAO"
  | "ERRO_GERACAO_PDF"
  | "ERRO_ENVIO_EMAIL"
  | "AGUARDANDO_VALIDACAO"
  | "AGUARDANDO_ASSINATURA"
  | "ASSINADA"
  | "APROVADA"
  | "CANCELADA"
  | "MIGRADA";

export type StatusPendencia =
  | "PENDENTE"
  | "EM_PROGRESSO"
  | "CONCLUIDO"
  | "ATRASADO"
  | "CANCELADO"
  | "REPACTUADA";

export type TipoReuniao =
  | "Diretoria"
  | "Gerencial"
  | "Coordenação"
  | "Mensal"
  | "Extraordinária";

// === Participante ===

export interface ParticipanteNaoReconhecido {
  nome: string
  cargo: string
  setor?: string
}

export interface Participante {
  id: string;
  nome_completo: string;
  cargo?: string | null;
  email: string;
  area?: string;
  setor?: string;
  role?: UserRole | null;
  ativo: boolean;
  is_externo?: boolean;
  is_super_admin?: boolean;
  access_profile?: AccessProfile;
  data_cadastro?: string;
}

export interface FacilitadorOption {
  id: string;
  nome_completo: string;
  setor?: string | null;
  is_externo?: boolean;
  ativo?: boolean;
}

// === Reunião ===

export interface Reuniao {
  id_reuniao: string;
  data: string;
  hora_inicio?: string;
  hora_fim?: string;
  tipo?: TipoReuniao;
  facilitador_id?: string;
  setor?: string;
  objetivo?: string;
  status_ata: StatusAta;
  total_acoes: number;
  acoes_concluidas: number;
  fonte: "FIREFLIES" | "MOCK" | "IMPORTACAO_LEGADA";
  url_pdf_preliminar?: string;
  url_pdf_assinado?: string;
  json_ata?: Record<string, unknown>;
  documento_id_origem?: string;
  arquivo_hash?: string;
  created_at?: string;
  updated_at?: string;
}

// === Nota ===

export interface Nota {
  id: string;
  corpo: string;
  autor_id: string;
  created_at?: string;
  updated_at?: string;
}

// === Pendência ===

export interface Pendencia {
  id_acao: string;
  // Origem: exatamente uma preenchida — Reunião (ASSINADA/APROVADA) ou Nota (ADR 0004).
  id_reuniao?: string | null;
  id_nota?: string | null;
  descricao_acao: string;
  responsavel_id?: string;
  responsavel_nome?: string;
  responsavel_is_externo?: boolean | null;
  co_responsavel_id?: string;
  co_responsavel_nome?: string;
  cargo?: string;
  prazo?: string;
  meta_entregavel?: string;
  status: StatusPendencia;
  total_comentarios?: number;
  created_at?: string;
  updated_at?: string;
}

export interface PendenciaStats {
  pendente: number;
  em_progresso: number;
  concluido: number;
  atrasado: number;
  cancelado: number;
  repactuada: number;
  total: number;
}

export interface PendenciaUpdate {
  status?: StatusPendencia;
  descricao_acao?: string;
  responsavel_id?: string;
  responsavel_nome?: string;
  co_responsavel_id?: string;
  co_responsavel_nome?: string;
  prazo?: string;
  cargo?: string;
  meta_entregavel?: string;
}

// === Comentário ===

export interface Comentario {
  id: string;
  id_acao: string;
  autor_id: string;
  autor_nome: string;
  conteudo: string;
  mencoes: string[];
  created_at?: string;
  updated_at?: string;
}

// === Notificação ===

export type TipoNotificacao = "MENCAO" | "STATUS_ALTERADO" | "COMENTARIO" | "PRAZO_PROXIMO" | "RESPONSAVEL_ATRIBUIDO";

export interface Notificacao {
  id: string;
  destinatario_id: string;
  tipo: TipoNotificacao;
  titulo: string;
  mensagem?: string;
  referencia_id?: string;
  lida: boolean;
  created_at?: string;
}

// === Ata JSON ===

export type StatusAtribuicao = "ABERTO" | "EM_ANDAMENTO" | "CONCLUIDO";

export interface Atribuicao {
  acao: string;
  responsavel: string;
  cargo: string;
  prazo: string | null;       // "YYYY-MM-DD" | "Fluxo contínuo" | null
  entregavel: string;
  objetivo_meta?: string;
  status?: StatusAtribuicao;
}

export interface ContribuicaoDiscussao {
  /** Nome civil de quem falou (vem do diretório ativo quando identificável).
   *  Pode ser null/ausente em ATAs legadas ou quando a IA não identificou a pessoa. */
  nome?: string | null;
  /** Cargo/função no formato "Cargo — Setor" (ex: "Diretora — Infraestrutura"). */
  funcao?: string;
  conteudo: string;
}

export interface TopicoDiscussao {
  titulo: string;
  descricao?: string;
  contribuicoes?: ContribuicaoDiscussao[];
  divergencias?: string[];
  decisao?: string;
  responsavel?: string | null;
}

export interface JsonAta {
  // === Modelo HSM oficial — 6 seções obrigatórias ===
  // (1) Cabeçalho: hora_inicio + hora_fim + (instituição/tipo via reunião)
  hora_inicio?: string;
  hora_fim?: string;
  // (2) Participantes
  participantes?: Array<{ nome: string; cargo: string; setor?: string; presente?: boolean }>;
  // (3) Objetivo
  objetivo?: string;
  // (4) Discussão dos Pontos (4.1, 4.2…)
  discussao?: TopicoDiscussao[];
  // (5) Quadro de Pendências, Decisões e Responsáveis
  quadro_atribuicoes?: Atribuicao[];
  // (6) Assinaturas — renderizadas pelo PDF a partir dos participantes presentes

  // === Campos legados (ATAs anteriores à migração HSM) ===
  // Presentes em JSONs antigos no Supabase; o novo pipeline não produz mais esses campos.
  /** @deprecated — substituído por discussao[] estruturado. Pré-migração HSM. */
  registro_narrativo?: string;
  /** @deprecated — removido do modelo oficial HSM. Pré-migração. */
  resumo_executivo?: string;
  /** @deprecated — removido do modelo oficial HSM. Pré-migração. */
  proxima_reuniao?: string | null;
  /** @deprecated — removido do modelo oficial HSM. Pré-migração. */
  lacunas_identificadas?: string[];

  error?: string;
  _mock?: boolean;
}

// === Preferências do Usuário ===

export interface NotificacaoPreferences {
  mencao: boolean;
  prazo_proximo: boolean;
  comentario: boolean;
  responsavel_atribuido: boolean;
}

export type EmailPreferences = Record<string, boolean>;

export interface UserPreferences {
  notificacoes: NotificacaoPreferences;
  emails: EmailPreferences;
}

export interface PerfilStats {
  reunioes: number;
  pendencias_ativas: number;
  concluidas: number;
  no_prazo_percentual: number;
}

export interface IntegracaoStatus {
  nome: string;
  conectado: boolean;
  ambiente: string | null;
  descricao: string;
}

// === Health ===

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
}
