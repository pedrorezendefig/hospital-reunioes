"use client";

import { useState } from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";

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

  return (
    <div className="modal-backdrop z-[200] flex items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-premium-strong w-full max-w-md overflow-hidden"
      >
        <header className="flex items-start justify-between px-6 py-4 border-b border-border">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-red-50">
              <AlertTriangle className="w-5 h-5 text-red-500" />
            </div>
            <div>
              <h2 className="text-base font-bold text-text">{title}</h2>
              <p className="text-xs text-slate-500 mt-0.5">{description}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="px-6 py-5">
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
        </div>

        <footer className="flex items-center justify-end gap-3 px-6 py-4 bg-slate-50 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${confirmStyles[confirmVariant]}`}
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {confirmLabel}
          </button>
        </footer>
      </form>
    </div>
  );
}
