import Link from "next/link";

import { PERIODOS, type Periodo, diasDoPeriodo } from "@/lib/central-de-comando/periodo";

interface SeletorDePeriodoProps {
  ativo: Periodo;
  /** O endereço da tela, sem query: cada opção é `caminho?periodo=...`. */
  caminho: string;
  /** Os períodos da tela, na ordem do seletor. O Instagram passa só 7 e 28. */
  periodos?: readonly Periodo[];
}

/**
 * O seletor de período das telas da Central de Comando (ADR 0058).
 *
 * Porte do `PeriodSelector` do repositório antigo: cada opção é um link que
 * troca o `?periodo=` do endereço, sem estado no cliente. O link guardado abre
 * no mesmo período, e recarregar a tela não volta para o padrão.
 */
export function SeletorDePeriodo({ ativo, caminho, periodos = PERIODOS }: SeletorDePeriodoProps) {
  return (
    <nav aria-label="Período" className="inline-flex gap-1 rounded-xl border border-border bg-white p-1">
      {periodos.map((periodo) => {
        const selecionado = periodo === ativo;
        return (
          <Link
            key={periodo}
            href={`${caminho}?periodo=${periodo}`}
            aria-current={selecionado ? "page" : undefined}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              selecionado
                ? "bg-primary text-white"
                : "text-text-secondary hover:bg-primary/5 hover:text-text"
            }`}
          >
            {diasDoPeriodo(periodo)} dias
          </Link>
        );
      })}
    </nav>
  );
}
