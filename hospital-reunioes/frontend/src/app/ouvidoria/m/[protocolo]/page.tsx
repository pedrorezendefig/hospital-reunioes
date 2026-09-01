"use client";

/**
 * A página do caso, endereçada pelo protocolo (issue #476, PRD #468, RN-53).
 *
 * O Dossiê era um modal sobre a fila: não tinha URL, então o botão do email de
 * cobrança não tinha para onde apontar, ninguém favoritava um caso e o voltar
 * do navegador não servia para nada. Agora cada manifestação tem endereço.
 *
 * O protocolo pode viver na URL porque ele já é público: vai no email do
 * manifestante e no do setor. Quem protege o caso é o perfil, não o segredo do
 * endereço, e é o backend quem decide (403 para quem está fora da Ouvidoria,
 * 404 para protocolo que não existe, log de acesso em toda leitura).
 *
 * Deslogado não cai aqui: o layout da área encaminha para o login levando este
 * endereço junto, e o login devolve a pessoa ao caso que ela tentou abrir
 * (issue #477).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { Dossie } from "@/components/ouvidoria/Dossie";

export default function PaginaDoCaso() {
  const params = useParams<{ protocolo: string }>();
  const bruto = params?.protocolo;
  const protocolo = decodeURIComponent(Array.isArray(bruto) ? bruto[0] : (bruto ?? ""));

  const [token, setToken] = useState<string | null>(null);
  // A sessão só chega depois de uma ida ao Supabase. Sem esta espera, o Dossiê
  // montaria sem token, veria "sem sessão" e a página piscaria um erro que não
  // é verdade.
  const [sessaoResolvida, setSessaoResolvida] = useState(false);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      setToken(session?.access_token ?? null);
      setSessaoResolvida(true);
    }
    init();
  }, []);

  return (
    <div className="p-4 md:p-8 max-w-4xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Painel da Ouvidoria
      </Link>

      {sessaoResolvida && <Dossie protocolo={protocolo} token={token} />}
    </div>
  );
}
