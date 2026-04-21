"use client";

import { useId, useState } from "react";
import { Loader2, AlertTriangle } from "lucide-react";
import { AdminModal } from "./AdminModal";

interface Props {
  title: string;
  description: string;
  confirmLabel: string;
  confirmVariant?: "danger" | "warning" | "primary";
  onClose: () => void;
  onConfirm: (reason: string) => Promise<boolean | void>;
}

/**
 * Modal de confirmacao que exige motivo em texto.
 *
 * Botao de submit fica desabilitado enquanto o motivo nao for informado —
 * corresponde ao requisito de "confirmacao dupla" (item 7 de §5 do plano).
 */
export function ReasonModal({
  title,
  description,
  confirmLabel,
  confirmVariant = "danger",
  onClose,
  onConfirm,
}: Props) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const formId = useId();

  const canSubmit = reason.trim().length > 0 && !submitting;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onConfirm(reason.trim());
    } finally {
      setSubmitting(false);
    }
  }

  const confirmStyles: Record<string, string> = {
    danger:
      "bg-red-600 hover:bg-red-700 text-white disabled:bg-red-300 disabled:cursor-not-allowed",
    warning:
      "bg-amber-600 hover:bg-amber-700 text-white disabled:bg-amber-300 disabled:cursor-not-allowed",
    primary:
      "bg-gradient-to-r from-primary to-primary-light text-white hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed",
  };

  const iconStyles: Record<string, { bg: string; fg: string }> = {
    danger: { bg: "bg-red-50", fg: "text-red-500" },
    warning: { bg: "bg-amber-50", fg: "text-amber-600" },
    primary: { bg: "bg-primary/10", fg: "text-primary" },
  };

  const iconStyle = iconStyles[confirmVariant];

  return (
    <AdminModal
      open
      onClose={onClose}
      title={title}
      description={description}
      icon={
        <div className={`p-2 rounded-xl ${iconStyle.bg}`}>
          <AlertTriangle className={`w-5 h-5 ${iconStyle.fg}`} />
        </div>
      }
      size="md"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form={formId}
            disabled={!canSubmit}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${confirmStyles[confirmVariant]}`}
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-slate-500 uppercase">
            Motivo <span className="text-red-500">*</span>
          </span>
          <textarea
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            required
            minLength={1}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary resize-none"
            placeholder="Ex: usuário desligado, erro de cadastro…"
          />
        </label>
      </form>
    </AdminModal>
  );
}
