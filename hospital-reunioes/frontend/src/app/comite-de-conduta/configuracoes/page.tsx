"use client";

import { ConfiguracoesDoCanal } from "@/components/conduta/ConfiguracoesDoCanal";

/** Configurações do Canal de Conduta, só da coordenação (issue #1826). */
export default function ConfiguracoesDoCanalPage() {
  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto w-full">
      <h1 className="text-2xl font-bold text-slate-900">Configurações</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-5">Contatos e textos usados nas telas públicas.</p>
      <ConfiguracoesDoCanal />
    </div>
  );
}
