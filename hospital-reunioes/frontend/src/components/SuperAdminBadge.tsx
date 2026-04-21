"use client";

import { Shield } from "lucide-react";

interface SuperAdminBadgeProps {
  /** Se false, renderiza null. */
  visible?: boolean;
  /** Tamanho do icone (px). Default 14. */
  size?: number;
  className?: string;
}

/**
 * Badge discreto exibido ao lado do nome do usuario logado
 * quando ele e super admin. Deve ser usado no header/navbar do
 * app SOMENTE para o proprio usuario logado — nao usar em listas
 * de outros usuarios (use um Badge diferente pra isso).
 */
export function SuperAdminBadge({
  visible = true,
  size = 14,
  className = "",
}: SuperAdminBadgeProps) {
  if (!visible) return null;

  return (
    <span
      title="Super Admin"
      aria-label="Super Admin"
      className={`inline-flex items-center justify-center text-primary ${className}`}
    >
      <Shield width={size} height={size} strokeWidth={2.25} />
    </span>
  );
}

export default SuperAdminBadge;
