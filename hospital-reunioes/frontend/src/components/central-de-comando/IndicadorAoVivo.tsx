"use client";

/**
 * O indicador Ao vivo da Visão Geral (issue #816, ADR 0058).
 *
 * "N no site agora", o único número em tempo real da Central. Some enquanto
 * não há número e quando a consulta falha sem um valor anterior; com um número
 * guardado, mantém-no. A degradação é silenciosa, sem aviso na tela: o Ao vivo
 * nunca derruba a Visão Geral nem mostra zero por causa de uma falha. O ponto
 * que pulsa diz que o número é de agora, e não do período.
 *
 * Acessibilidade (issue #843): a região viva é só o número, para o leitor de
 * tela não reanunciar o bloco inteiro a cada consulta de 30 segundos; e o ponto
 * para de pulsar quando a pessoa pede menos movimento no sistema.
 */

import { formatarInteiro } from "@/lib/central-de-comando/formato";

import { useAoVivo } from "./useAoVivo";

export function IndicadorAoVivo() {
  const pessoas = useAoVivo();
  if (pessoas === null) return null;

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-white px-3 py-1.5 text-sm text-text-secondary shadow-premium">
      <span aria-hidden className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75 motion-reduce:animate-none" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
      </span>
      <span>
        <strong aria-live="polite" className="font-semibold tabular-nums text-text">{formatarInteiro(pessoas)}</strong> no site agora
      </span>
    </div>
  );
}
