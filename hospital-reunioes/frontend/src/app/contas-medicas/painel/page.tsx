"use client";

/**
 * O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).
 *
 * A nota média de entrada da semana, onde o R$ apontado nasce, os dez itens
 * que mais faltam, a produção de cada faturista, o R$ incluído por nível de
 * evidência e o custo de IA, com os filtros de semana, operadora e tipo de
 * conta. Quem soma é o servidor; quem decide o que cada pessoa vê também: a
 * faturista recebe só a própria linha de produção.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";

import { FiltrosDoPainel } from "@/components/contas-medicas/painel/FiltrosDoPainel";
import { TelaDoPainel } from "@/components/contas-medicas/painel/TelaDoPainel";
import {
  hojeIso,
  rotaDoPainel,
  rotuloDaSemana,
  type FiltrosDoPainel as Filtros,
  type Painel,
} from "@/lib/contas-medicas/painel";
import { createClient } from "@/lib/supabase/client";

export default function PainelPage() {
  const [token, setToken] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<Filtros>({ semana: hojeIso(), operadora: "", tipo: "" });
  const [painel, setPainel] = useState<Painel | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data: { session } }) => {
        if (session?.access_token) setToken(session.access_token);
        else setCarregando(false);
      });
  }, []);

  useEffect(() => {
    if (!token || !filtros.semana) return;
    let vivo = true;
    setCarregando(true);
    setErro(null);
    fetch(rotaDoPainel(filtros), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!vivo) return;
        if (!res.ok) {
          setErro("Não foi possível carregar o Painel.");
          return;
        }
        setPainel(await res.json());
      })
      .catch(() => vivo && setErro("Não foi possível carregar o Painel."))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [token, filtros]);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/contas-medicas"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Contas médicas
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Painel</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          A nota da semana e onde a perda da conta nasce, pelas contas concluídas de segunda a domingo.
        </p>
      </div>

      <FiltrosDoPainel filtros={filtros} operadoras={painel?.filtros.operadoras ?? []} aoMudar={setFiltros} />

      {painel && (
        <p className="flex items-center gap-2 text-sm text-slate-600">
          Semana de {rotuloDaSemana(painel.semana)}
          {carregando && <Loader2 className="w-4 h-4 animate-spin text-slate-400" aria-label="Carregando" />}
        </p>
      )}

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      {!painel && carregando && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando o Painel
        </div>
      )}

      {painel && <TelaDoPainel painel={painel} />}
    </div>
  );
}
