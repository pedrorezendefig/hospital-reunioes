"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

export interface CurrentParticipante {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string;
  area?: string | null;
  setor?: string | null;
  role?: string;
  ativo?: boolean;
  is_externo?: boolean;
  is_super_admin?: boolean;
}

interface State {
  participante: CurrentParticipante | null;
  loading: boolean;
  error: string | null;
}

// Cache por sessao do browser — evita re-fetch em cada navegacao SPA.
// A promise e deduplicada para que multiplos consumidores renderizados no
// mesmo tick compartilhem uma unica requisicao.
let cachedPromise: Promise<CurrentParticipante | null> | null = null;
let cachedValue: CurrentParticipante | null = null;

async function fetchMe(): Promise<CurrentParticipante | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) return null;

  const res = await fetch("/api/participantes/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    // 401/404 -> tratamos como "nao ha participante" e deixamos a UI decidir.
    return null;
  }
  const data = (await res.json()) as CurrentParticipante;
  cachedValue = data;
  return data;
}

/**
 * Hook que retorna o participante logado (GET /api/participantes/me).
 *
 * Fonte unica de verdade para is_super_admin, role, setor do usuario atual.
 * Evita dependencia de user_metadata do JWT (que pode ficar stale apos
 * promote/demote via painel /admin).
 *
 * A primeira chamada faz fetch; chamadas subsequentes na mesma sessao
 * reaproveitam o valor cacheado. Chame `invalidateCurrentParticipante()`
 * se precisar forcar refresh (ex: apos self-service que muda flags).
 */
export function useCurrentParticipante(): State {
  const [state, setState] = useState<State>({
    participante: cachedValue,
    loading: cachedValue === null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    if (cachedValue) {
      setState({ participante: cachedValue, loading: false, error: null });
      return;
    }

    if (!cachedPromise) {
      cachedPromise = fetchMe().catch((err) => {
        cachedPromise = null; // permite retry em chamada futura
        throw err;
      });
    }

    cachedPromise
      .then((p) => {
        if (cancelled) return;
        setState({ participante: p, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          participante: null,
          loading: false,
          error: err instanceof Error ? err.message : "Erro ao buscar participante",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

/**
 * Limpa o cache do participante logado. Use apos acoes que mudam o
 * proprio participante (ex: auto-promote via /admin/super-admins).
 */
export function invalidateCurrentParticipante(): void {
  cachedPromise = null;
  cachedValue = null;
}
