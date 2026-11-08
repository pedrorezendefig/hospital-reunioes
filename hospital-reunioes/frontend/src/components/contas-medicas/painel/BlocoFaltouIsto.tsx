import { dataCurta } from "@/lib/contas-medicas/guia";
import {
  CLASSIFICACOES_DO_FALTOU,
  ORIGENS_DO_FALTOU,
  ROTULO_CLASSIFICACAO_DO_FALTOU,
  ROTULO_ORIGEM_DO_FALTOU,
  type FaltouIstoNaSemana,
} from "@/lib/contas-medicas/painel";

import { Moldura } from "./Moldura";

/**
 * Os Faltou isto apontados em cada semana (issue #1492): quantos o Auditor
 * classificou como Regra, Leitura ou Defeito, quantos esperam a classificação
 * e quem achou, a pessoa ou o agente. A semana escolhida fica no alto.
 */
export function BlocoFaltouIsto({ semanas }: { semanas: FaltouIstoNaSemana[] }) {
  const daMaisNova = [...semanas].reverse();
  return (
    <Moldura titulo="Faltou isto por semana" subtitulo="O que o módulo deixou passar, por classificação e por quem achou">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="py-1.5 font-medium">Semana</th>
              <th className="py-1.5 font-medium text-right">Total</th>
              {CLASSIFICACOES_DO_FALTOU.map((c) => (
                <th key={c} className="py-1.5 font-medium text-right">
                  {ROTULO_CLASSIFICACAO_DO_FALTOU[c]}
                </th>
              ))}
              {ORIGENS_DO_FALTOU.map((o) => (
                <th key={o} className="py-1.5 font-medium text-right text-slate-400">
                  {ROTULO_ORIGEM_DO_FALTOU[o]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {daMaisNova.map((s) => (
              <tr key={s.semana} className="border-t border-slate-100">
                <td className="py-1.5 text-slate-800">{dataCurta(s.semana)}</td>
                <td className="py-1.5 text-right font-semibold tabular-nums text-primary">{s.total}</td>
                {CLASSIFICACOES_DO_FALTOU.map((c) => (
                  <td key={c} className="py-1.5 text-right tabular-nums text-slate-700">
                    {s.classificacao[c]}
                  </td>
                ))}
                {ORIGENS_DO_FALTOU.map((o) => (
                  <td key={o} className="py-1.5 text-right tabular-nums text-slate-400">
                    {s.origem[o]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Moldura>
  );
}
