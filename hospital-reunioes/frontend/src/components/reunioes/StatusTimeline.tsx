"use client";

import {
  Bot,
  Users,
  ClipboardCheck,
  PenLine,
  BadgeCheck,
  XCircle,
} from "lucide-react";
import type { StatusAta } from "@/types";

const TIMELINE_STEPS: { status: StatusAta; label: string; icon: typeof Bot }[] = [
  { status: "PROCESSANDO", label: "Processando IA", icon: Bot },
  { status: "AGUARDANDO_RESOLUCAO", label: "Resolver Participantes", icon: Users },
  { status: "AGUARDANDO_VALIDACAO", label: "Aguard. Validação", icon: ClipboardCheck },
  { status: "AGUARDANDO_ASSINATURA", label: "Aguard. Assinatura", icon: PenLine },
  { status: "ASSINADA", label: "Assinada", icon: BadgeCheck },
];

const STATUS_ORDER: Record<StatusAta, number> = {
  PROGRAMADA: -1,
  PROCESSANDO: 0,
  ERRO: 0,
  ERRO_UPLOAD_TRANSCRICAO: 0,
  ERRO_GERACAO_PDF: 0,
  ERRO_ENVIO_EMAIL: 0,
  AGUARDANDO_RESOLUCAO: 1,
  AGUARDANDO_VALIDACAO: 2,
  AGUARDANDO_ASSINATURA: 3,
  ASSINADA: 4,
  CANCELADA: -1,
  MIGRADA: 4,
};

export default function StatusTimeline({ current }: { current: StatusAta }) {
  const currentOrder = STATUS_ORDER[current] ?? 0;
  const isError = current === "ERRO";

  return (
    <div className="flex items-center gap-2">
      {TIMELINE_STEPS.map((step, i) => {
        const done = currentOrder > i;
        const active = currentOrder === i && !isError;
        const Icon = step.icon;
        return (
          <div key={step.status} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                done
                  ? "bg-gradient-to-r from-primary to-primary-dark text-white"
                  : active
                  ? "bg-primary/10 text-primary ring-2 ring-primary/30"
                  : "bg-slate-100 text-slate-400"
              }`}
            >
              <Icon className="w-3.5 h-3.5" strokeWidth={done || active ? 2 : 1.5} />
              {step.label}
            </div>
            {i < TIMELINE_STEPS.length - 1 && (
              <div className={`h-px w-6 ${done ? "bg-primary" : "bg-slate-200"}`} />
            )}
          </div>
        );
      })}
      {isError && (
        <div className="ml-2 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
          <XCircle className="w-3.5 h-3.5" />
          Erro
        </div>
      )}
    </div>
  );
}
