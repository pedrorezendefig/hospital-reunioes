"use client";

import { useState } from "react";
import { BookOpen } from "lucide-react";

import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";
import { paginasVisiveis, type PaginaDoManual } from "@/lib/manual/paginas";
import { MarkdownDoManual } from "./MarkdownDoManual";
import { RetratoDaAna } from "./RetratoDaAna";

type Aba = "aplicativo" | "ana";

/**
 * O manual, na largura toda, com as abas Aplicativo do Hospital e Ana (issue
 * #1718, ADR 0094, decisões 1, 2 e 4).
 *
 * A aba Aplicativo do Hospital lista só as páginas dos módulos que a pessoa
 * tem no menu. A aba Ana é só do Super admin e mostra o Retrato da Ana
 * (issue #1720, ADR 0094, decisão 3).
 *
 * No celular, a lista de páginas fica em cima e a página embaixo, numa coluna;
 * a partir do `md`, lado a lado.
 */
export function Manual({ paginas }: { paginas: readonly PaginaDoManual[] }) {
  const { participante } = useCurrentParticipante();
  const superAdmin = isSuperAdmin(participante);
  const visiveis = paginasVisiveis(paginas, participante);
  const [aba, setAba] = useState<Aba>("aplicativo");
  const [escolhida, setEscolhida] = useState<string | null>(null);
  const pagina = visiveis.find((p) => p.pasta === escolhida) ?? visiveis[0];

  const abas: { id: Aba; rotulo: string }[] = [
    { id: "aplicativo", rotulo: "Aplicativo do Hospital" },
    ...(superAdmin ? [{ id: "ana" as const, rotulo: "Ana" }] : []),
  ];
  const abaAberta = superAdmin ? aba : "aplicativo";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <BookOpen className="h-5 w-5" strokeWidth={1.75} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Manual</h1>
          <p className="text-sm text-text-secondary">
            Como usar o aplicativo, tarefa por tarefa.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist" aria-label="Manual">
        {abas.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={abaAberta === a.id}
            onClick={() => setAba(a.id)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer ${
              abaAberta === a.id
                ? "border-primary text-primary"
                : "border-transparent text-text-secondary hover:text-text"
            }`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {abaAberta === "ana" ? (
        <div role="tabpanel" aria-label="Ana">
          <RetratoDaAna />
        </div>
      ) : (
        <div role="tabpanel" aria-label="Aplicativo do Hospital">
          {pagina ? (
            <div data-colunas-do-manual className="flex flex-col md:flex-row gap-6">
              <nav aria-label="Páginas do manual" className="md:w-56 md:shrink-0">
                <ul className="flex flex-wrap gap-1 md:flex-col">
                  {visiveis.map((p) => {
                    const ativa = p.pasta === pagina.pasta;
                    return (
                      <li key={p.pasta}>
                        <button
                          type="button"
                          onClick={() => setEscolhida(p.pasta)}
                          aria-current={ativa ? "page" : undefined}
                          className={`w-full text-left px-3 py-2 rounded-xl text-sm font-medium transition-colors cursor-pointer ${
                            ativa
                              ? "bg-primary/10 text-primary"
                              : "text-text-secondary hover:bg-primary/5 hover:text-text"
                          }`}
                        >
                          {p.titulo}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </nav>

              <article className="min-w-0 flex-1 max-w-3xl rounded-2xl border border-border bg-surface p-5 md:p-8 shadow-premium">
                <h2 className="text-xl font-bold text-text mb-4">{pagina.titulo}</h2>
                <MarkdownDoManual pasta={pagina.pasta}>{pagina.corpo}</MarkdownDoManual>
              </article>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">
              O manual ainda não tem página para as partes do aplicativo que você usa.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
