/**
 * Como funciona a Ouvidoria (issue #1629, PRD #1527, regra T9): o primeiro
 * acesso em uma tela, pelo menu de atalhos.
 *
 * Cinco passos, cada um com o título da seção 4.14 e uma frase de onde ele
 * acontece no app. Nada mais: a tela precisa caber no celular com rolagem
 * curta, e quem quiser o detalhe tem o "?" de cada campo na tela do trabalho.
 */

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { FRASE_DO_TOPO, PASSOS_DA_OUVIDORIA } from "@/lib/ouvidoria/orientacao";

export default function ComoFuncionaPage() {
  return (
    <div className="p-4 md:p-8 max-w-2xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Como funciona a Ouvidoria</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-5">{FRASE_DO_TOPO.como_funciona}</p>

      <ol aria-label="Os cinco passos de um caso" className="space-y-2.5">
        {PASSOS_DA_OUVIDORIA.map((passo, indice) => (
          <li
            key={passo.titulo}
            className="flex gap-3 bg-white rounded-2xl border border-border shadow-premium px-4 py-3"
          >
            <span
              aria-hidden="true"
              className="flex items-center justify-center shrink-0 w-7 h-7 rounded-full bg-[#EAEAF0] text-[#282760] text-sm font-bold"
            >
              {indice + 1}
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-900 normal-case tracking-normal">{passo.titulo}</h2>
              <p className="text-sm text-slate-600 mt-0.5">{passo.detalhe}</p>
            </div>
          </li>
        ))}
      </ol>

      <Link
        href="/ouvidoria"
        className="mt-5 inline-flex items-center justify-center min-h-[44px] px-4 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 transition-colors"
      >
        Ir para a fila
      </Link>
    </div>
  );
}
