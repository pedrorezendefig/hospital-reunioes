import type { FluxogramaEstrutura } from "@/lib/pops/fluxograma/tipos";

export type { FluxogramaEstrutura } from "@/lib/pops/fluxograma/tipos";

// === Enums ===

export type UserRole = "diretor" | "presidente" | "gerente" | "coordenador";

export type AccessProfile = "regular" | "secretaria" | "super_admin";

export const ACCESS_PROFILE_LABELS: Record<AccessProfile, string> = {
  regular: "Regular",
  secretaria: "Secretária",
  super_admin: "Super Admin",
};

// Eixo de permissão do contexto POPs (ADR 0007) — ortogonal ao AccessProfile.
export type PerfilPop =
  | "superadmin"
  | "gestor_qualidade"
  | "gerente"
  | "coordenador";

export const PERFIL_POP_LABELS: Record<PerfilPop, string> = {
  superadmin: "Superadmin",
  gestor_qualidade: "Gestor de Qualidade",
  gerente: "Gerente",
  coordenador: "Coordenador",
};

// Contexto POPs — POP, Versão e formulário institucional (issue #82)

export type EstadoVersaoPop =
  | "A_ELABORAR"
  | "EM_ELABORACAO"
  | "EM_REVISAO"
  | "EM_VALIDACAO"
  | "EM_ASSINATURA"
  | "PUBLICADO";

export const ESTADO_VERSAO_POP_LABELS: Record<EstadoVersaoPop, string> = {
  A_ELABORAR: "A Elaborar",
  EM_ELABORACAO: "Em Elaboração",
  EM_REVISAO: "Em Revisão",
  EM_VALIDACAO: "Em Validação",
  EM_ASSINATURA: "Em Assinatura",
  PUBLICADO: "Publicado",
};

export type CriticidadePop = "CRITICA" | "ALTA" | "MEDIA";

export const CRITICIDADE_POP_LABELS: Record<CriticidadePop, string> = {
  CRITICA: "CRÍTICA",
  ALTA: "ALTA",
  MEDIA: "MÉDIA",
};

export type PeriodicidadeRevisaoPop = "3_meses" | "6_meses" | "1_ano" | "2_anos";

export const PERIODICIDADE_REVISAO_POP_LABELS: Record<PeriodicidadeRevisaoPop, string> = {
  "3_meses": "3 meses",
  "6_meses": "6 meses",
  "1_ano": "1 ano",
  "2_anos": "2 anos",
};

export interface PopVersao {
  id: string;
  numero_versao: string;
  estado: EstadoVersaoPop;
}

export interface Pop {
  id: string;
  codigo: string;
  nome: string;
  setor_id: string;
  setor_nome: string | null;
  setor_sigla: string | null;
  criticidade: CriticidadePop;
  base_normativa: string | null;
  periodicidade_revisao: PeriodicidadeRevisaoPop;
  prazo_elaboracao_dias: number;
  prazo_revisao_dias: number;
  elaborador_id: string;
  revisor_id: string;
  validador_id: string;
  criado_por: string | null;
  created_at: string | null;
  versao: PopVersao | null;
}

export interface PopDesignavel {
  id: string;
  nome_completo: string | null;
  perfil_pop: PerfilPop;
}

// Elaboração — POP vivo com chat do agente (issue #83; estrutura dinâmica ADR 0016)

/** Tipo de uma seção do POP: texto comum ou o fluxo do procedimento. */
export type TipoSecaoPop = "texto" | "fluxograma";

/** Uma seção do POP na estrutura DINÂMICA (ADR 0016): o agente cria, renomeia,
 * reordena e remove seções livremente. O `id` é estável e atribuído pelo
 * sistema (não deriva do título, que pode mudar) — mantém o apontar-seção (⌖)
 * e a atualização ao vivo precisos. A Identificação (seção 1) deriva do
 * cadastro do POP e não vive nesta lista. Espelha pops_secoes.py do backend. */
export interface SecaoPop {
  id: string;
  titulo: string;
  /** Texto (string) em toda seção; na seção `tipo=fluxograma`, o objeto JSON da
   * gramática restrita (ADR 0024) quando válido, ou uma string sem desenho
   * possível (objeto inválido serializado, ou Mermaid legado que a migração
   * one-shot da #224 não converteu). */
  conteudo: string | FluxogramaEstrutura;
  tipo: TipoSecaoPop;
  /** Fluxograma: o `svg` é o desenho renderizado no cliente (renderer próprio do
   * ADR 0024, ou o Mermaid legado antes da migração), capturado e persistido com
   * a Versão para o PDF embutir o mesmo do preview (pipeline do ADR 0017). Só na
   * seção `tipo=fluxograma`; cai quando o conteúdo muda (re-captura). */
  svg?: string;
}

/** O rascunho persistido na Versão: a lista ordenada de seções de conteúdo. */
export interface RascunhoPop {
  secoes: SecaoPop[];
}

/** Dados do POP que alimentam a seção 1 (Identificação) da tela de elaboração. */
export interface PopElaboracaoPopInfo {
  id: string;
  codigo: string;
  nome: string;
  setor_nome: string | null;
  setor_sigla: string | null;
  criticidade: CriticidadePop;
  base_normativa: string | null;
  periodicidade_revisao: PeriodicidadeRevisaoPop;
  prazo_elaboracao_dias: number;
  prazo_revisao_dias: number;
  elaborador_id: string;
  revisor_id: string;
  validador_id: string;
  elaborador_nome: string | null;
  revisor_nome: string | null;
  validador_nome: string | null;
  created_at: string | null;
}

// Revisão e Validação — aprovar/devolver com retorno direto (issue #85)

/** Devolução registrada com nome e timestamp — visível na elaboração e na
 * leitura da Versão; a etapa de retorno decide para onde o reenvio volta. */
export interface PopDevolucao {
  id: string;
  autor_id: string;
  autor_nome: string | null;
  etapa_retorno: "EM_REVISAO" | "EM_VALIDACAO";
  comentarios: string;
  created_at: string | null;
}

export const ETAPA_DEVOLUCAO_LABELS: Record<PopDevolucao["etapa_retorno"], string> = {
  EM_REVISAO: "Revisão",
  EM_VALIDACAO: "Validação",
};

/** Material de referência da elaboração (issue #84) — o agente o lê ativamente. */
export interface PopMaterialReferencia {
  id: string;
  filename: string;
  extensao: string;
  tamanho_bytes: number;
  created_at: string | null;
}

/** GET /pops/{id}/elaboracao e GET /pops/{id}/versao — a Versão completa
 * (rascunho persistido + Devoluções, da mais recente à mais antiga + Materiais
 * de referência). */
export interface PopElaboracao {
  pop: PopElaboracaoPopInfo;
  versao: PopVersao;
  rascunho: RascunhoPop | null;
  periodicidade_sugerida: PeriodicidadeRevisaoPop | null;
  devolucoes: PopDevolucao[];
  materiais: PopMaterialReferencia[];
}

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

// === Pendência ===

export interface Pendencia {
  id_acao: string;
  // Origem: Reunião em estado terminal — ASSINADA ou APROVADA (ADR 0003/0011).
  id_reuniao?: string | null;
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
