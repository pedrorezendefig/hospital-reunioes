"use client";

import { useSyncExternalStore } from "react";

/** A tela larga do Quadro da Tecnologia (ADR 0090): o `xl` do Tailwind, 1280px. */
export const CONSULTA_DA_TELA_LARGA = "(min-width: 1280px)";

function consulta(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(CONSULTA_DA_TELA_LARGA)
    : null;
}

function assinar(avisar: () => void): () => void {
  const lista = consulta();
  lista?.addEventListener("change", avisar);
  return () => lista?.removeEventListener("change", avisar);
}

/**
 * Se a tela tem 1280px ou mais (issue #1642). Escolhe entre o Quadro e a
 * lista, que não cabem os dois na página: esconder um deles só pelo CSS
 * deixaria os mesmos cards duas vezes na árvore.
 *
 * O servidor e o navegador sem `matchMedia` ficam com a tela estreita, a
 * lista de sempre; a tela larga troca para o Quadro logo depois de montar.
 */
export function useTelaLarga(): boolean {
  return useSyncExternalStore(
    assinar,
    () => consulta()?.matches ?? false,
    () => false,
  );
}
