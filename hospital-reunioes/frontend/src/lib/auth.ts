/**
 * Super admin é identificado pela flag boolean is_super_admin no participante.
 * Diretores e presidentes SEM a flag ficam com a mesma visibilidade de
 * gerente/coordenador (só veem reuniões/pendências em que participaram).
 */

export interface AuthUser {
  id?: string;
  email?: string;
  role?: string;
  is_super_admin?: boolean;
}

/**
 * Recebe o participante (ou objeto de usuário com a flag) e retorna true se
 * for super admin. Aceita undefined/null por conveniência em componentes que
 * ainda estão carregando o usuário.
 */
export function isSuperAdmin(user: AuthUser | null | undefined): boolean {
  return user?.is_super_admin === true;
}

/**
 * @deprecated Use isSuperAdmin(user) — o modelo agora usa flag dedicada
 * em vez de role. Retorna sempre false para forçar migração das chamadas
 * restantes (o comportamento antigo "diretor=super" não é mais válido).
 */
export function isSuperUser(_role: string): boolean {
  if (typeof console !== "undefined" && console.warn) {
    console.warn(
      "[auth] isSuperUser(role) está deprecado. Use isSuperAdmin(user) lendo user.is_super_admin."
    );
  }
  return false;
}
