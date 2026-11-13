"use client";

import { useEffect, useState } from "react";

/** Quanto tempo o número leva para subir de 0 até o valor (ADR 0092, decisão 7). */
export const DURACAO_DA_CONTAGEM_MS = 900;

/** Rápido no começo e devagar no fim. */
function desacelerar(t: number): number {
  return 1 - (1 - t) ** 3;
}

/**
 * O número que sobe contando de 0 até `alvo` em 0,9 s, quadro a quadro com o
 * `requestAnimationFrame`. Com `parado` (quem pediu menos movimento), o valor
 * final vem já na primeira pintura e nenhum quadro é pedido.
 */
export function useContagem(alvo: number, parado: boolean): number {
  const [valor, setValor] = useState(0);

  useEffect(() => {
    if (parado) return;
    let inicio: number | null = null;
    let quadro = 0;
    const passo = (agora: number) => {
      inicio ??= agora;
      const t = Math.min(1, (agora - inicio) / DURACAO_DA_CONTAGEM_MS);
      setValor(Math.round(alvo * desacelerar(t)));
      if (t < 1) quadro = requestAnimationFrame(passo);
    };
    setValor(0);
    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, [alvo, parado]);

  return parado ? alvo : valor;
}
