/**
 * Perfil de acesso é determinado por `access_profile` (enum único).
 * Fallback (fase 1 da migração 035): se access_profile não estiver presente,
 * usa is_super_admin pra compatibilidade.
 */

import type { AccessProfile } from "@/types";

export interface AuthUser {
  id?: string;
  email?: string;
  role?: string | null;
  is_super_admin?: boolean;
  access_profile?: AccessProfile;
}

export function isSuperAdmin(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (user.access_profile) return user.access_profile === "super_admin";
  return user.is_super_admin === true;
}

export function isSecretaria(user: AuthUser | null | undefined): boolean {
  return user?.access_profile === "secretaria";
}

export function isRegular(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (user.access_profile) return user.access_profile === "regular";
  return user.is_super_admin !== true;
}

/**
 * @deprecated Use isSuperAdmin(user). O modelo agora usa access_profile.
 */
export function isSuperUser(_role: string): boolean {
  if (typeof console !== "undefined" && console.warn) {
    console.warn(
      "[auth] isSuperUser(role) está deprecado. Use isSuperAdmin(user) lendo user.access_profile."
    );
  }
  return false;
}
