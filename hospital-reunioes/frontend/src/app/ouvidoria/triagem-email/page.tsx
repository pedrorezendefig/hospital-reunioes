"use client";

/**
 * Triagem de e-mail da Ouvidoria (issue #648, PRD #646, ADR 0051).
 *
 * A porta fica ao lado da fila, na área da Ouvidoria, e só para o Perfil da
 * Ouvidoria (o layout desta rota barra os demais no servidor). A tela em si
 * mora em `components/ouvidoria/TriagemDeEmail`, com teste próprio.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";

import { TriagemDeEmail } from "@/components/ouvidoria/TriagemDeEmail";
import { createClient } from "@/lib/supabase/client";

export default function TriagemDeEmailPage() {
  const [token, setToken] = useState<string | null>(null);
  const [semSessao, setSemSessao] = useState(false);

  useEffect(() => {
    let cancelado = false;
    createClient()
      .auth.getSession()
      .then(({ data: { session } }) => {
        if (cancelado) return;
        if (session?.access_token) setToken(session.access_token);
        else setSemSessao(true);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Voltar à fila
      </Link>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Triagem de e-mail</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          O que chegou em ouvidoria@, antes de virar caso. Nada daqui vira manifestação sem a sua decisão.
        </p>
      </div>
      {token ? (
        <TriagemDeEmail token={token} />
      ) : semSessao ? (
        <p className="text-sm text-slate-500">Sua sessão expirou. Entre de novo para ver a triagem.</p>
      ) : (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Carregando
        </div>
      )}
    </div>
  );
}
