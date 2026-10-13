"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BarChart3 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

/** Quem tem o Painel completo e quem envia e corrige contas (a faturista vê a própria produção). */
const QUEM_VE_O_PAINEL = ["painel_completo", "enviar_corrigir_contas"];

/**
 * O caminho até o Painel (issue #1137), na tela de contas.
 *
 * Aparece pela permissão que a rota `/api/contas-medicas/me` já resolve pela
 * matriz. Sem resposta, some: quem decide o que cada um vê no Painel é a API
 * dele, que manda à faturista só a própria linha de produção.
 */
export function LinkParaPainel() {
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
        if (vivo) setPode(Array.isArray(permissoes) && QUEM_VE_O_PAINEL.some((p) => permissoes.includes(p)));
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
      href="/contas-medicas/painel"
      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300"
    >
      <BarChart3 className="w-4 h-4" aria-hidden="true" /> Painel
    </Link>
  );
}
