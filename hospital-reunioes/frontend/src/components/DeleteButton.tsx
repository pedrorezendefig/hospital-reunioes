"use client";

import { useState } from "react";
import { Crown } from "lucide-react";
import { ConfirmDialog } from "./ConfirmDialog";
import { useToast } from "./ui/Toast";

/**
 * Props do DeleteButton.
 *
 * Wrapper reutilizavel pra acoes destrutivas dentro da camada Super Admin.
 * Renderiza um botao roxo com icone de coroa (autoridade superadmin) que,
 * ao ser clicado, abre um ConfirmDialog (simples ou com motivo obrigatorio,
 * controlado pela prop `requireReason`). A seriedade da acao destrutiva
 * continua sinalizada pelo botao de confirmacao interno do modal, que usa
 * `confirmVariant="danger"` (vermelho).
 *
 * Exemplo:
 * ```tsx
 * <DeleteButton
 *   visible={isSuperAdmin(user)}
 *   requireReason
 *   confirmTitle="Excluir ATA?"
 *   confirmDescription="Esta acao nao pode ser desfeita."
 *   onDelete={async (reason) => {
 *     await api.delete(`/reunioes/${id}/force`, { reason });
 *   }}
 * />
 * ```
 *
 * Tratamento de erros: se `onDelete` rejeitar, o DeleteButton exibe um toast
 * "Erro ao excluir: {msg}" via `useToast` e mantem o modal aberto pro usuario
 * tentar de novo. Em sucesso, o modal fecha. Requer `<ToastProvider>` acima
 * na arvore (ja presente em `app/layout.tsx`).
 */
export interface DeleteButtonProps {
  /** Se false, nao renderiza nada. Default: true. */
  visible?: boolean;
  /** Texto do botao. Default: "Excluir". */
  label?: string;
  /**
   * Se true, o ConfirmDialog exige motivo (textarea max 1000 chars) e
   * `onDelete` recebe a string digitada. Default: false.
   */
  requireReason?: boolean;
  /** Titulo do modal de confirmacao. Ex: "Excluir ATA assinada?". */
  confirmTitle: string;
  /** Descricao opcional exibida no modal. */
  confirmDescription?: string;
  /** Texto do botao Confirmar no modal. Default: "Excluir". */
  confirmLabel?: string;
  /**
   * Callback que executa a delecao. Se `requireReason` for true, recebe
   * o motivo digitado. Deve lancar/rejeitar em caso de falha — o DeleteButton
   * cuida de exibir o toast de erro e manter o modal aberto.
   */
  onDelete: (reason?: string) => Promise<void>;
  /** Desabilita o botao gatilho (e consequentemente a abertura do modal). */
  disabled?: boolean;
  /** Classes extras aplicadas ao botao gatilho. */
  className?: string;
  /** Se true, esconde o icone de coroa (mostra so o label). Default: false. */
  hideIcon?: boolean;
  /**
   * Variante visual do botao gatilho.
   * - `solid` (default): fundo roxo solido.
   * - `outline`: borda roxa, texto roxo, fundo transparente.
   * - `ghost`: sem borda nem fundo, so texto roxo (pra usar em menus).
   */
  buttonVariant?: "solid" | "outline" | "ghost";
}

export function DeleteButton({
  visible = true,
  label = "Excluir",
  requireReason = false,
  confirmTitle,
  confirmDescription,
  confirmLabel = "Excluir",
  onDelete,
  disabled = false,
  className = "",
  hideIcon = false,
  buttonVariant = "solid",
}: DeleteButtonProps) {
  const [open, setOpen] = useState(false);
  const { toast } = useToast();

  if (!visible) return null;

  const handleConfirm = async (reason?: string) => {
    try {
      await onDelete(reason);
      // Sucesso: deixa o ConfirmDialog fechar sozinho via onClose.
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast(`Erro ao excluir: ${msg}`, "error");
      // Relanca pro ConfirmDialog detectar falha e manter modal aberto.
      throw err;
    }
  };

  const variantClass =
    buttonVariant === "solid"
      ? "bg-purple-600 text-white hover:bg-purple-700 border border-purple-600"
      : buttonVariant === "outline"
        ? "bg-transparent text-purple-700 hover:bg-purple-50 border border-purple-200"
        : "bg-transparent text-purple-700 hover:bg-purple-50 border border-transparent";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled}
        className={`inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${variantClass} ${className}`}
      >
        {!hideIcon && <Crown className="w-4 h-4" />}
        {label}
      </button>

      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={handleConfirm}
        title={confirmTitle}
        description={confirmDescription}
        confirmLabel={confirmLabel}
        confirmVariant="danger"
        requireReason={requireReason}
      />
    </>
  );
}

export default DeleteButton;
