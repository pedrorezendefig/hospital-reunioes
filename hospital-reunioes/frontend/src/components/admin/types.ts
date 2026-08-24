import { AccessProfile, PerfilOuvidoria, PerfilPop, UserRole } from "@/types";

/** Linha vinda de GET /api/admin/usuarios */
export interface AdminUsuario {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string | null;
  area?: string | null;
  setor?: string | null;
  role?: UserRole | null;
  ativo: boolean;
  is_externo: boolean;
  is_super_admin: boolean;
  access_profile: AccessProfile;
  perfil_pop?: PerfilPop | null;
  perfil_ouvidoria?: PerfilOuvidoria | null;
  auth_user_id?: string | null;
  data_cadastro?: string | null;
}

/** Linha do audit_log retornada por GET /api/admin/usuarios/{id} */
export interface AuditLogRow {
  id: string;
  timestamp: string;
  actor_id?: string | null;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
  ip_address?: string | null;
  reason?: string | null;
}

/** Detalhe combinado de um usuario + ultimos 20 logs. */
export interface AdminUsuarioDetalhe {
  usuario: AdminUsuario;
  audit_logs: AuditLogRow[];
}

/** Payload usado tanto para create quanto update (subset). */
export interface AdminUsuarioPayload {
  nome_completo?: string;
  email?: string;
  cargo?: string | null;
  area?: string | null;
  setor?: string | null;
  role?: UserRole | null;
  access_profile?: AccessProfile;
  is_externo?: boolean;
  ativo?: boolean;
  reason?: string;
}

/**
 * Mudança do eixo POPs reportada pelo modal de edição (#148). A presença do
 * objeto sinaliza que o perfil_pop mudou; `value: null` revoga o acesso.
 */
export interface PerfilPopChange {
  value: PerfilPop | null;
}

/**
 * Mudança do eixo Ouvidoria reportada pelo modal de edição (#320, ADR 0034).
 * Mesma forma do POPs: presença do objeto = mudou; `value: null` revoga.
 */
export interface PerfilOuvidoriaChange {
  value: PerfilOuvidoria | null;
}

export const ROLE_OPTIONS: UserRole[] = [
  "diretor",
  "presidente",
  "gerente",
  "coordenador",
];

export const ACCESS_PROFILE_OPTIONS: AccessProfile[] = [
  "regular",
  "secretaria",
  "super_admin",
];
