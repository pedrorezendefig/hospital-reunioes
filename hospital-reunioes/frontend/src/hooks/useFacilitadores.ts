"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import type { FacilitadorOption } from "@/types";

interface State {
  facilitadores: FacilitadorOption[];
  loading: boolean;
  error: string | null;
}

let cachedPromise: Promise<FacilitadorOption[]> | null = null;
let cachedValue: FacilitadorOption[] | null = null;

async function fetchFacilitadores(): Promise<FacilitadorOption[]> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) return [];

  const res = await fetch("/api/participantes/facilitadores", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = (await res.json()) as FacilitadorOption[];
  cachedValue = data;
  return data;
}

/**
 * Lista de pessoas que ja foram facilitadoras de alguma reuniao viva.
 * Compartilhada via cache de modulo entre /pendencias, /pendencias/kanban
 * e /reunioes/calendario para evitar 3 fetches em troca de viewport.
 */
export function useFacilitadores(): State {
  const [state, setState] = useState<State>({
    facilitadores: cachedValue ?? [],
    loading: cachedValue === null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    if (cachedValue) {
      setState({ facilitadores: cachedValue, loading: false, error: null });
      return;
    }

    if (!cachedPromise) {
      cachedPromise = fetchFacilitadores().catch((err) => {
        cachedPromise = null;
        throw err;
      });
    }

    cachedPromise
      .then((list) => {
        if (cancelled) return;
        setState({ facilitadores: list, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          facilitadores: [],
          loading: false,
          error: err instanceof Error ? err.message : "Erro ao buscar facilitadores",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export function invalidateFacilitadores(): void {
  cachedPromise = null;
  cachedValue = null;
}
