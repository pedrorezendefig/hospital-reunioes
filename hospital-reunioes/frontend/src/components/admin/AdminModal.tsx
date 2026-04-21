"use client";

import {
  ReactNode,
  RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

type ModalSize = "sm" | "md" | "lg" | "xl";

interface AdminModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  icon?: ReactNode;
  size?: ModalSize;
  scrollable?: boolean;
  footer?: ReactNode;
  children: ReactNode;
  closeOnBackdrop?: boolean;
  closeOnEsc?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
}

const SIZE_CLASS: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
  xl: "max-w-5xl",
};

// Contador global para body scroll-lock com multiplos modais abertos em
// cascata (ex: ReasonModal de reset -> NewPasswordModal).
let openModalCount = 0;
let prevBodyOverflow: string | null = null;

function lockBodyScroll() {
  if (openModalCount === 0) {
    prevBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  openModalCount += 1;
}

function unlockBodyScroll() {
  openModalCount = Math.max(0, openModalCount - 1);
  if (openModalCount === 0) {
    document.body.style.overflow = prevBodyOverflow ?? "";
    prevBodyOverflow = null;
  }
}

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/**
 * Modal padronizado do painel admin.
 *
 * Caracteristicas:
 * - Renderizado via `createPortal(document.body)`, imune a `transform`/`filter`
 *   em ancestors (causa classica de `position: fixed` afundar no container).
 * - Backdrop escurecido (`bg-black/40`) com blur leve; animacao `fade-in`.
 * - Conteudo com animacao `scale-in` (0.22s cubic-bezier).
 * - Acessibilidade: `role="dialog"`, `aria-modal`, `aria-labelledby`,
 *   `aria-describedby`, focus inicial no primeiro campo interativo.
 * - ESC e click no backdrop fecham (opcionais via prop).
 * - Body scroll-lock com contador para suportar modais em cascata.
 *
 * Contrato de submit para forms: envolva `children` em
 * `<form id="xxx" onSubmit={...}>` e no `footer` use
 * `<button type="submit" form="xxx">`. Funciona em todos os browsers modernos.
 */
export function AdminModal({
  open,
  onClose,
  title,
  description,
  icon,
  size = "md",
  scrollable = false,
  footer,
  children,
  closeOnBackdrop = true,
  closeOnEsc = true,
  initialFocusRef,
}: AdminModalProps) {
  const [mounted, setMounted] = useState(false);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Body scroll-lock (com contador em modulo para cascata).
  useEffect(() => {
    if (!open) return;
    lockBodyScroll();
    return () => unlockBodyScroll();
  }, [open]);

  // ESC fecha.
  useEffect(() => {
    if (!open || !closeOnEsc) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, closeOnEsc, onClose]);

  // Focus inicial.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus();
        return;
      }
      const root = contentRef.current;
      if (!root) return;
      const focusable = root.querySelector<HTMLElement>(
        "input:not([type='hidden']):not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled]):not([aria-label='Fechar'])",
      );
      focusable?.focus();
    }, 50);
    return () => clearTimeout(t);
  }, [open, initialFocusRef]);

  if (!open || !mounted) return null;

  const sizeClass = SIZE_CLASS[size];

  return createPortal(
    <>
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-[2px] z-[200] animate-fade-in"
        onClick={closeOnBackdrop ? onClose : undefined}
        aria-hidden="true"
      />
      <div
        className="fixed inset-0 z-[210] flex items-center justify-center p-4 pointer-events-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
      >
        <div
          ref={contentRef}
          onClick={(e) => e.stopPropagation()}
          className={cx(
            "bg-white rounded-2xl shadow-premium-strong pointer-events-auto animate-scale-in flex flex-col w-full",
            sizeClass,
            scrollable && "max-h-[90vh] overflow-hidden",
          )}
        >
          <header className="flex items-start justify-between gap-3 px-6 py-4 border-b border-border flex-shrink-0">
            <div className="flex items-start gap-3 min-w-0">
              {icon && <div className="flex-shrink-0">{icon}</div>}
              <div className="min-w-0">
                <h2
                  id={titleId}
                  className="text-lg font-bold text-text truncate"
                >
                  {title}
                </h2>
                {description && (
                  <p id={descId} className="text-xs text-slate-500 mt-0.5">
                    {description}
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 flex-shrink-0 transition-colors"
              aria-label="Fechar"
            >
              <X className="w-5 h-5" />
            </button>
          </header>

          <div
            className={cx(
              "px-6 py-5",
              scrollable ? "flex-1 overflow-auto" : "",
            )}
          >
            {children}
          </div>

          {footer && (
            <footer className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border bg-slate-50/50 flex-shrink-0">
              {footer}
            </footer>
          )}
        </div>
      </div>
    </>,
    document.body,
  );
}
