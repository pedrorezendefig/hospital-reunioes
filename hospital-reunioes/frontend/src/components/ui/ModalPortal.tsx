"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

interface ModalPortalProps {
  children: React.ReactNode;
}

/**
 * Renderiza o conteudo direto no document.body via portal.
 *
 * Modais com `position: fixed` afundam quando um ancestral cria contexto de
 * empilhamento (transform/filter — ex.: wrappers .animate-fade-in-up), porque
 * o fixed passa a se ancorar nesse ancestral, e nao na viewport. Portar pro
 * body imuniza contra isso por construcao. Veja ConfirmDialog/AdminModal.
 *
 * O guard de `mounted` evita mismatch de hidratacao: o portal so existe no
 * client, entao no primeiro render (server e hidratacao) nao renderiza nada.
 *
 * ```tsx
 * <ModalPortal>
 *   <div className="modal-backdrop z-[100] flex items-center justify-center">
 *     ...
 *   </div>
 * </ModalPortal>
 * ```
 */
export function ModalPortal({ children }: ModalPortalProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return createPortal(children, document.body);
}

export default ModalPortal;
