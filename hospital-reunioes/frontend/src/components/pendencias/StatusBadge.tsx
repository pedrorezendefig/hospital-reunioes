"use client";

import { PENDENCIA_STATUS_CONFIG } from "@/constants/pendencias";
import { StatusPendencia } from "@/types";

interface StatusBadgeProps {
  status: StatusPendencia;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const cfg = PENDENCIA_STATUS_CONFIG[status];
  if (!cfg) return null;

  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.color} ${className ?? ""}`}
    >
      <Icon className="w-3 h-3" strokeWidth={2.5} />
      {cfg.label}
    </span>
  );
}
