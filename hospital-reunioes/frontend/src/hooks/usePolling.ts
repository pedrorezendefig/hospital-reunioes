"use client";

import { useEffect, useRef } from "react";

/**
 * Hook that runs a callback on a fixed interval while `enabled` is true.
 *
 * Consolidates the repeated pattern found in:
 *   - reunioes/[id]/page.tsx  (polls while PROCESSANDO / AGUARDANDO_RESOLUCAO)
 *   - reunioes/page.tsx       (polls for processing meetings, 15s)
 *   - NotificacoesDropdown.tsx (polls notification count, 30s)
 *
 * Uses a ref to always call the latest version of `callback`,
 * avoiding stale closure issues without requiring `callback` in deps.
 *
 * Usage:
 *   usePolling(
 *     () => fetchData(),
 *     15000,
 *     reuniao?.status_ata === "PROCESSANDO"
 *   );
 */
export function usePolling(
  callback: () => Promise<void> | void,
  intervalMs: number,
  enabled: boolean
): void {
  const savedCallback = useRef(callback);

  // Keep ref current so the interval always fires the latest callback
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;

    const tick = () => {
      savedCallback.current();
    };

    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}
