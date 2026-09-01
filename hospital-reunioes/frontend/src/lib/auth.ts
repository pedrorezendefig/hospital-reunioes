/**
 * Perfil de acesso é determinado por `access_profile` (enum único).
 * Fallback (fase 1 da migração 035): se access_profile não estiver presente,
 * usa is_super_admin pra compatibilidade.
 */

import type { AccessProfile, PerfilOuvidoria, PerfilPop } from "@/types";

export interface AuthUser {
  id?: string;
  email?: string;
  role?: string | null;
  is_super_admin?: boolean;
  access_profile?: AccessProfile | null;
  perfil_pop?: PerfilPop | null;
  perfil_ouvidoria?: PerfilOuvidoria | null;
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
 * Contexto POPs (ADR 0007): perfil_pop é o eixo de permissão próprio,
 * ortogonal ao access_profile das Reuniões.
 */
export function temPerfilPop(user: AuthUser | null | undefined): boolean {
  return Boolean(user?.perfil_pop);
}

export function isSuperadminPops(user: AuthUser | null | undefined): boolean {
  return user?.perfil_pop === "superadmin";
}

/**
 * Contexto Ouvidoria (ADR 0034): `perfil_ouvidoria` é o terceiro eixo de
 * permissão, ortogonal ao das Reuniões e ao dos POPs. Ter o campo preenchido
 * (`ouvidor` ou `diretoria_executiva`) é ser da Ouvidoria; nulo é estar fora
 * dela, mesmo sendo super admin de Reuniões.
 */
export function temPerfilOuvidoria(user: AuthUser | null | undefined): boolean {
  return Boolean(user?.perfil_ouvidoria);
}

/**
 * True se a pessoa tem papel no contexto Reuniões. access_profile NULL
 * explícito = sem papel (ex.: Coordenador de POPs); campo ausente mantém o
 * comportamento legado (com acesso).
 */
export function temAcessoReunioes(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if ("access_profile" in user) return user.access_profile != null;
  return true;
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
