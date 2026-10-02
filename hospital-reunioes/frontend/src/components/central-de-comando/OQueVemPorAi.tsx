import { Sparkles } from "lucide-react";

import { ROTEIRO } from "@/lib/central-de-comando/roteiro";

/**
 * O bloco "O que vem por aí" no pé da Visão Geral (issue #821, ADR 0058, decisão
 * 5): o que ainda vai nascer na Central, em linguagem de leigo, SEM data e SEM
 * item de menu. É o único lugar onde funcionalidade futura aparece.
 */
export function OQueVemPorAi() {
  return (
    <section aria-labelledby="central-o-que-vem" className="space-y-4 rounded-2xl border border-dashed border-border bg-bg p-6">
      <div className="space-y-1">
        <h2 id="central-o-que-vem" className="flex items-center gap-2 text-lg font-bold text-text">
          <Sparkles aria-hidden className="h-5 w-5 text-primary" />O que vem por aí
        </h2>
        <p className="text-sm text-text-secondary">O que ainda vai nascer na Central. Aparece aqui antes de virar tela.</p>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2">
        {ROTEIRO.map((item) => {
          const Icone = item.icone;
          return (
            <li key={item.id} className="flex items-start gap-3 rounded-xl border border-border bg-white p-4">
              <span
                aria-hidden
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
              >
                <Icone className="h-4 w-4" />
              </span>
              <div className="space-y-1">
                <h3 className="font-semibold text-text">{item.titulo}</h3>
                <p className="text-xs text-text-secondary">{item.descricao}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
