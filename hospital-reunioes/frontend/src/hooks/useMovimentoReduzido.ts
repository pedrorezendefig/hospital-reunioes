"use client";

import { useSyncExternalStore } from "react";

/** Quem pediu ao sistema menos movimento na tela. */
export const CONSULTA_DO_MOVIMENTO_REDUZIDO = "(prefers-reduced-motion: reduce)";

function consulta(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(CONSULTA_DO_MOVIMENTO_REDUZIDO)
    : null;
}

function assinar(avisar: () => void): () => void {
  const lista = consulta();
  lista?.addEventListener("change", avisar);
  return () => lista?.removeEventListener("change", avisar);
}

/**
 * Se a pessoa pediu menos movimento (ADR 0092, decisão 7): com o sim, número
 * e barra aparecem prontos, sem contar nem crescer. O CSS já desliga as
 * animações dele pelo `@media`; este gancho é para o movimento feito em
 * JavaScript, que o CSS não alcança.
 */
export function useMovimentoReduzido(): boolean {
  return useSyncExternalStore(
    assinar,
    () => consulta()?.matches ?? false,
    () => false,
  );
}
