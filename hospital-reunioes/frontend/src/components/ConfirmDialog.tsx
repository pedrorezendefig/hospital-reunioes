"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";

/**
 * Variantes do botao Confirmar.
 * - `default`: azul/padrao.
 * - `danger`: vermelho, pra acoes destrutivas.
 */
export type ConfirmVariant = "default" | "danger";

/**
 * Props comuns do ConfirmDialog.
 *
 * Quando `requireReason` e true, o modal exibe um textarea "Motivo (obrigatorio)"
 * e `onConfirm` recebe o texto digitado. Quando false (default), `onConfirm`
 * e chamado sem argumento.
 */
export interface ConfirmDialogProps {
  /** Controla a visibilidade do modal. */
  open: boolean;
  /** Chamada quando o usuario cancela ou clica fora. */
  onClose: () => void;
  /**
   * Chamada quando o usuario confirma. Pode ser async — enquanto a Promise
   * estiver pendente, o botao Confirmar mostra loading e o modal fica bloqueado.
   * Se `requireReason` for true, recebe a string digitada; caso contrario, nao recebe argumento.
   */
  onConfirm: (reason?: string) => void | Promise<void>;
  /** Titulo exibido no topo do modal. */
  title: string;
  /** Descricao opcional exibida abaixo do titulo. */
  description?: string;
  /** Texto do botao de confirmacao. Default: "Confirmar". */
  confirmLabel?: string;
  /** Texto do botao cancelar. Default: "Cancelar". */
  cancelLabel?: string;
  /** Estilo do botao confirmar. Default: "default". */
  confirmVariant?: ConfirmVariant;
  /**
   * Se true, renderiza o textarea de motivo obrigatorio (max 1000 chars)
   * e desabilita Confirmar enquanto estiver vazio (apos trim). Default: false.
   */
  requireReason?: boolean;
  /** Placeholder do textarea quando `requireReason` e true. */
  reasonPlaceholder?: string;
}

const MAX_REASON_LENGTH = 1000;

/**
 * Modal generico de confirmacao usado pela camada Super Admin.
 *
 * Duas variantes:
 *
 * 1. Simples (default):
 *    ```tsx
 *    <ConfirmDialog
 *      open={open}
 *      onClose={() => setOpen(false)}
 *      onConfirm={async () => { await doThing(); }}
 *      title="Aplicar alteracao?"
 *    />
 *    ```
 *
 * 2. Com motivo obrigatorio:
 *    ```tsx
 *    <ConfirmDialog
 *      open={open}
 *      onClose={() => setOpen(false)}
 *      onConfirm={async (reason) => { await del(id, reason); }}
 *      title="Excluir ATA assinada?"
 *      requireReason
 *      confirmVariant="danger"
 *      confirmLabel="Excluir"
 *    />
 *    ```
 *
 * Se `onConfirm` lancar erro, o modal permanece aberto — cabe ao chamador
 * exibir o erro (ex: via toast). Se resolver com sucesso, o ConfirmDialog
 * chama `onClose` automaticamente.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  confirmVariant = "default",
  requireReason = false,
  reasonPlaceholder = "Explique brevemente o motivo desta acao...",
}: ConfirmDialogProps) {
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  // Reset interno sempre que o modal abre
  useEffect(() => {
    if (open) {
      setReason("");
      setLoading(false);
    }
  }, [open]);

  if (!open) return null;

  const reasonTrimmed = reason.trim();
  const confirmDisabled =
    loading || (requireReason && reasonTrimmed.length === 0);

  const handleConfirm = async () => {
    if (confirmDisabled) return;
    try {
      setLoading(true);
      if (requireReason) {
        await onConfirm(reasonTrimmed);
      } else {
        await onConfirm();
      }
      // Sucesso: fechar modal. O reset acontece ao reabrir.
      onClose();
    } catch (err) {
      // Mantem modal aberto; chamador decide como exibir erro.
       
      console.error("ConfirmDialog.onConfirm lancou erro:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleBackdropClick = () => {
    if (loading) return;
    onClose();
  };

  const isDanger = confirmVariant === "danger";

  const confirmButtonClass = isDanger
    ? "bg-red-600 text-white hover:bg-red-700"
    : "bg-primary text-white hover:bg-primary/90";

  const iconWrapperClass = isDanger
    ? "bg-red-100 text-red-600"
    : "bg-primary/10 text-primary";

  return (
    <div
      className="modal-backdrop z-[200] flex items-center justify-center px-4"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          disabled={loading}
          aria-label="Fechar"
          className="absolute top-3 right-3 p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <X className="w-4 h-4" />
        </button>

        <div
          className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4 ${iconWrapperClass}`}
        >
          <AlertTriangle className="w-6 h-6" />
        </div>

        <h3
          id="confirm-dialog-title"
          className="text-lg font-bold text-slate-900 text-center mb-1"
        >
          {title}
        </h3>

        {description && (
          <p className="text-sm text-slate-500 text-center mb-4 whitespace-pre-line">
            {description}
          </p>
        )}

        {requireReason && (
          <div className="mb-4 mt-2">
            <label
              htmlFor="confirm-dialog-reason"
              className="block text-xs font-medium text-slate-700 mb-1.5"
            >
              Motivo (obrigatorio)
            </label>
            <textarea
              id="confirm-dialog-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={MAX_REASON_LENGTH}
              rows={4}
              disabled={loading}
              placeholder={reasonPlaceholder}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 disabled:bg-slate-50 disabled:text-slate-400 resize-none"
            />
            <div className="flex justify-end mt-1">
              <span
                className={`text-[10px] ${
                  reason.length >= MAX_REASON_LENGTH
                    ? "text-red-500"
                    : "text-slate-400"
                }`}
              >
                {reason.length}/{MAX_REASON_LENGTH}
              </span>
            </div>
          </div>
        )}

        <div className="flex gap-3 mt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={confirmDisabled}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${confirmButtonClass}`}
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {loading ? "Processando..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
