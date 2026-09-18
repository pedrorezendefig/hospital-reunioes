import { formatarData, formatarInteiro, formatarPercentual } from "@/lib/central-de-comando/formato";
import type { Periodo } from "@/lib/central-de-comando/periodo";

type Intervalo = { inicio: string; fim: string };

/** O bloco `periodo` do payload: o período e as datas dele e do anterior. */
export type PeriodoDoPayload = {
  chave: Periodo;
  dias: number;
  atual: Intervalo;
  anterior: Intervalo;
};

/** O bloco `visitantes` do payload, com a variação já calculada no backend. */
export type VisitantesDoPayload = {
  atual: number;
  anterior: number;
  variacao: number | null;
};

/**
 * A seta da variação contra o período anterior: para cima em verde, para
 * baixo em âmbar, e nada quando não há base de comparação. O sentido fica na
 * seta, e a porcentagem vai sem sinal (molde da Central antiga).
 */
function Variacao({ variacao }: { variacao: number | null }) {
  if (variacao === null) return null;
  const subiu = variacao >= 0;
  return (
    <span className={`font-semibold ${subiu ? "text-emerald-700" : "text-amber-700"}`}>
      {subiu ? "↑" : "↓"} {formatarPercentual(Math.abs(variacao))}
    </span>
  );
}

/**
 * O número-manchete da Visão Geral: quantos Visitantes o Site teve no período.
 *
 * As datas ficam à vista, pequenas, para quem conferir com o Google comparar o
 * mesmo intervalo: o período termina ontem, e a conta é do backend.
 */
export function BlocoVisitantes({
  periodo,
  visitantes,
}: {
  periodo: PeriodoDoPayload;
  visitantes: VisitantesDoPayload;
}) {
  return (
    <section
      aria-labelledby="central-visitantes"
      className="space-y-3 rounded-2xl border border-border bg-white p-6 shadow-premium"
    >
      <h2 id="central-visitantes" className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
        Visitantes · últimos {periodo.dias} dias
      </h2>
      <p className="text-5xl font-bold tabular-nums text-text">{formatarInteiro(visitantes.atual)}</p>
      <p className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
        <Variacao variacao={visitantes.variacao} />
        <span>
          {visitantes.variacao === null
            ? "sem base de comparação com o período anterior"
            : "em relação ao período anterior"}
        </span>
      </p>
      <p className="text-xs text-text-secondary">
        De {formatarData(periodo.atual.inicio)} a {formatarData(periodo.atual.fim)}. Período anterior:{" "}
        {formatarData(periodo.anterior.inicio)} a {formatarData(periodo.anterior.fim)}.
      </p>
    </section>
  );
}
