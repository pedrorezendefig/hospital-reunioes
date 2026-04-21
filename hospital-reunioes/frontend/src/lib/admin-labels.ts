/**
 * Mapas de labels amigaveis para o painel /admin.
 *
 * Diretores usam esse painel — valores raw como `DELETE_REUNIAO`,
 * `super_admin`, `AGUARDANDO_ASSINATURA` precisam virar textos em PT-BR
 * legiveis. Usado por /admin/logs, /admin/usuarios e /admin/bulk.
 */

export const ACTION_LABELS: Record<string, string> = {
  DELETE_REUNIAO: "Excluiu reunião",
  DELETE_ATA: "Excluiu ata",
  DELETE_PENDENCIA: "Excluiu pendência",
  FORCE_STATUS: "Forçou status",
  EDIT_REUNIAO_FORCE: "Editou reunião (forçado)",
  EDIT_PENDENCIA_FORCE: "Editou pendência (forçado)",
  CREATE_USUARIO: "Criou usuário",
  EDIT_USUARIO: "Editou usuário",
  DELETE_USUARIO: "Excluiu usuário",
  RESET_PASSWORD: "Resetou senha",
  PROMOTE_SUPER_ADMIN: "Promoveu a super admin",
  DEMOTE_SUPER_ADMIN: "Rebaixou super admin",
  EXPORT_LOGS: "Exportou logs",
};

export const TARGET_TYPE_LABELS: Record<string, string> = {
  reuniao: "Reunião",
  ata: "Ata",
  pendencia: "Pendência",
  participante: "Participante",
  super_admin: "Super admin",
  bulk: "Ação em massa",
  audit_log: "Log de auditoria",
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  pending: "Agendado",
  running: "Executando",
  completed: "Concluído",
  failed: "Falhou",
};

export const STATUS_ATA_LABELS: Record<string, string> = {
  PROGRAMADA: "Programada",
  PROCESSANDO: "Processando",
  AGUARDANDO_RESOLUCAO: "Aguardando resolução",
  AGUARDANDO_VALIDACAO: "Aguardando validação",
  AGUARDANDO_ASSINATURA: "Aguardando assinatura",
  ASSINADA: "Assinada",
  CANCELADA: "Cancelada",
  ERRO: "Erro",
  ERRO_TRANSCRICAO: "Erro de transcrição",
  ERRO_IA: "Erro de IA",
  ERRO_CLICKSIGN: "Erro ClickSign",
  MIGRADA: "Migrada",
};

/**
 * Fallback amigavel para enum desconhecido: "DELETE_REUNIAO" -> "Delete reuniao".
 */
export function humanize(value: string): string {
  if (!value) return "—";
  const spaced = value.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function actionLabel(value: string): string {
  return ACTION_LABELS[value] ?? humanize(value);
}

export function targetTypeLabel(value: string): string {
  return TARGET_TYPE_LABELS[value] ?? humanize(value);
}

export function jobStatusLabel(value: string): string {
  return JOB_STATUS_LABELS[value] ?? humanize(value);
}

export function statusAtaLabel(value: string): string {
  return STATUS_ATA_LABELS[value] ?? humanize(value);
}
