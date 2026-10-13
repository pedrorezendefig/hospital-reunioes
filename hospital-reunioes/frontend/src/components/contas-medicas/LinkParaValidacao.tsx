"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ListChecks } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

/**
 * O caminho até a fila de Validação (issue #1142), na tela de contas.
 *
 * Só aparece para quem tem a permissão de decidir na validação, que a rota
 * `/api/contas-medicas/me` já resolve pela matriz. Sem resposta, some: a
 * decisão de verdade é da API da fila, que recusa com 403.
 */
export function LinkParaValidacao() {
  const [pode, setPode] = useState(false);

  useEffect(() => {
    let vivo = true;
    async function perguntar() {
      try {
        const {
          data: { session },
        } = await createClient().auth.getSession();
        if (!session?.access_token) return;
        const res = await fetch("/api/contas-medicas/me", {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) return;
        const { permissoes } = await res.json();
        if (vivo) setPode(Array.isArray(permissoes) && permissoes.includes("decidir_validacao"));
      } catch {
        // sem resposta, sem link
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
      href="/contas-medicas/validacao"
      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300"
    >
      <ListChecks className="w-4 h-4" aria-hidden="true" /> Validação
    </Link>
  );
}
