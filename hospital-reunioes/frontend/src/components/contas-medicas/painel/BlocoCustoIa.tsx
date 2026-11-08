import { textoEmDolar, type CustoDeIa } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/**
 * O custo de IA da semana, em dólar: a análise das contas concluídas nela e,
 * em partes separadas, as conversas com o Auditor, as provas de regra e o
 * revisor feitos na semana. O médio por conta é só o da análise.
 */
export function BlocoCustoIa({ custo }: { custo: CustoDeIa }) {
  const partes: [string, number][] = [
    ["Análise das contas", custo.analise_usd],
    ["Conversas com o Auditor", custo.conversa_usd],
    ["Provas de regra", custo.provas_usd],
    ["Revisor", custo.revisor_usd],
  ];
  return (
    <Moldura titulo="Custo de IA" subtitulo="A análise das contas e o Auditor, na semana">
      <Numero>{textoEmDolar(custo.total_usd)}</Numero>
      <Apoio>
        {textoEmDolar(custo.medio_por_conta_usd)} por conta, em {custo.contas}{" "}
        {custo.contas === 1 ? "conta" : "contas"}
      </Apoio>
      <ul className="mt-3 space-y-1 text-sm">
        {partes.map(([nome, valor]) => (
          <li key={nome} className="flex justify-between gap-3">
            <span className="text-slate-600">{nome}</span>
            <span className="tabular-nums text-slate-800">{textoEmDolar(valor)}</span>
          </li>
        ))}
      </ul>
    </Moldura>
  );
}
