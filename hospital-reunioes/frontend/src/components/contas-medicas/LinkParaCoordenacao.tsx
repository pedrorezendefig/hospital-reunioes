"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ClipboardCheck } from "lucide-react";

import { ROTA_COORDENACAO } from "@/lib/contas-medicas/coordenacao";
import { createClient } from "@/lib/supabase/client";

/**
 * O caminho até a tela Coordenação (issue #1143), na tela de contas, com o
 * número de lembretes abertos.
 *
 * Só aparece para quem tem a Conferência da coordenação, que a rota
 * `/api/contas-medicas/me` já resolve pela matriz; só então os lembretes são
 * pedidos. Sem resposta, some: a decisão de verdade é da API da tela, que
 * recusa com 403.
 */
export function LinkParaCoordenacao() {
  const [pode, setPode] = useState(false);
  const [abertos, setAbertos] = useState<number | null>(null);

  useEffect(() => {
    let vivo = true;
    async function perguntar() {
      try {
        const {
          data: { session },
        } = await createClient().auth.getSession();
        if (!session?.access_token) return;
        const cabecalho = { headers: { Authorization: `Bearer ${session.access_token}` } };
        const res = await fetch("/api/contas-medicas/me", cabecalho);
        if (!res.ok) return;
        const { permissoes } = await res.json();
        const tem = Array.isArray(permissoes) && permissoes.includes("conferencia_coordenacao");
        if (!vivo || !tem) return;
        setPode(true);
        const conferencia = await fetch(ROTA_COORDENACAO, cabecalho);
        if (!conferencia.ok) return;
        const { numeros } = await conferencia.json();
        if (vivo && typeof numeros?.lembretes_abertos === "number") setAbertos(numeros.lembretes_abertos);
      } catch {
        // sem resposta, sem link (ou sem a contagem)
      }
    }
    perguntar();
    return () => {
      vivo = false;
    };
  }, []);

  if (!pode) return null;
  return (
    <Link
      href="/contas-medicas/coordenacao"
      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300"
    >
      <ClipboardCheck className="w-4 h-4" aria-hidden="true" /> Coordenação
      {abertos !== null && (
        <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-white tabular-nums">
          {abertos}
        </span>
      )}
    </Link>
  );
}
