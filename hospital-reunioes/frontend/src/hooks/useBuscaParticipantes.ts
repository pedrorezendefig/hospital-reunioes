"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export interface ParticipanteBusca {
  id: string;
  nome_completo: string;
  email?: string | null;
  cargo?: string | null;
  setor?: string | null;
  area?: string | null;
  role?: string | null;
  ativo?: boolean;
  is_externo?: boolean;
}

interface UseBuscaParticipantesResult {
  resultados: ParticipanteBusca[];
  loading: boolean;
  error: string | null;
}

/**
 * Busca debounced em `/api/participantes` por nome. Retorna internos ativos e
 * externos cadastrados (endpoint já devolve ambos desde que ativo=true).
 *
 * Termos com menos de 2 caracteres não disparam fetch — evita flood.
 */
export function useBuscaParticipantes(
  termo: string,
  debounceMs = 250,
  limit = 10
): UseBuscaParticipantesResult {
  const [resultados, setResultados] = useState<ParticipanteBusca[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const termoLimpo = termo.trim();
    if (termoLimpo.length < 2) {
      setResultados([]);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const timer = setTimeout(async () => {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        const token = session?.access_token;
        if (!token) {
          if (!cancelled) setLoading(false);
          return;
        }

        const params = new URLSearchParams({
          nome: termoLimpo,
          ativo: "true",
          limit: String(limit),
        });
        const res = await fetch(`/api/participantes?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          throw new Error(`Falha na busca (${res.status})`);
        }

        const data = (await res.json()) as ParticipanteBusca[];
        if (!cancelled) {
          setResultados(Array.isArray(data) ? data : []);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Erro ao buscar");
          setResultados([]);
          setLoading(false);
        }
      }
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [termo, debounceMs, limit]);

  return { resultados, loading, error };
}
