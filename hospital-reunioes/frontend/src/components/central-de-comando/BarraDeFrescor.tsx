"use client";

import { useCallback, useSyncExternalStore } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import type { Frescor } from "@/lib/central-de-comando/api";
import { formatarQuando } from "@/lib/central-de-comando/formato";
import { tempoRelativo } from "@/lib/central-de-comando/tempo-relativo";

const MINUTO_MS = 60_000;

/** O relógio da barra bate uma vez por minuto. */
function assinarMinuto(avisar: () => void) {
  const id = setInterval(avisar, MINUTO_MS);
  return () => clearInterval(id);
}

/**
 * A barra de frescor das telas da Central de Comando (issue #815, ADR 0058).
 *
 * Porte do `FreshnessBar` do repositório antigo: diz há quanto tempo os
 * números foram atualizados, tem o botão Atualizar agora e, quando a última
 * atualização falhou, troca o carimbo por um aviso calmo com a hora do último
 * número bom (e o dia, se não é de hoje) e o motivo que o backend mandou. A
 * tela nunca zera por causa de uma falha: os números de antes continuam
 * embaixo da barra.
 *
 * O "há X minutos" anda sozinho, a cada minuto, sem recarregar a página. O
 * instante é contado em minutos inteiros desde a atualização, e não é o
 * relógio cru: o valor só muda quando o minuto vira, e é isso que a
 * `useSyncExternalStore` precisa para não redesenhar à toa. No servidor não
 * há relógio (`null`), e o carimbo sai sem o tempo. Sem hora registrada, a
 * barra não inventa hora nenhuma.
 *
 * `aviso` é a frase de um Atualizar agora que não chegou a trazer payload (o
 * limite de taxa, a rede fora): os números e o carimbo continuam os de antes.
 */
export function BarraDeFrescor({
  frescor,
  atualizando,
  aviso = null,
  onAtualizar,
}: {
  frescor: Frescor;
  atualizando: boolean;
  aviso?: string | null;
  onAtualizar: () => void;
}) {
  const desde = frescor.atualizado_em === null ? null : Date.parse(frescor.atualizado_em);
  const agoraNoMinuto = useCallback(() => {
    if (desde === null) return null;
    return desde + Math.floor((Date.now() - desde) / MINUTO_MS) * MINUTO_MS;
  }, [desde]);
  const agora = useSyncExternalStore(assinarMinuto, agoraNoMinuto, () => null);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-white px-4 py-3 shadow-premium">
      <div className="min-w-0 space-y-1 text-sm">
        {frescor.atualizacao_falhou ? (
          <p role="status" className="flex items-start gap-2 text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
            <span>
              <span className="font-semibold">Não foi possível atualizar agora.</span>
              {desde !== null && ` Mostrando os números de ${formatarQuando(desde, agora ?? desde)}.`}
              {frescor.motivo && <span className="block">{frescor.motivo}</span>}
            </span>
          </p>
        ) : (
          <p className="flex items-center gap-2 font-medium text-text-secondary">
            <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" aria-hidden="true" />
            {desde === null || agora === null ? "Atualizado" : `Atualizado ${tempoRelativo(desde, agora)}`}
          </p>
        )}
        {aviso && (
          <p role="status" className="text-amber-800">
            {aviso}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onAtualizar}
        disabled={atualizando}
        aria-busy={atualizando}
        className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-white px-3 py-1.5 text-sm font-medium text-text transition-colors hover:bg-primary/5 disabled:cursor-default disabled:text-text-secondary disabled:hover:bg-white"
      >
        <RefreshCw className={`h-4 w-4 ${atualizando ? "animate-spin" : ""}`} aria-hidden="true" />
        {atualizando ? "Atualizando…" : "Atualizar agora"}
      </button>
    </div>
  );
}
