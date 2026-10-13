import { textoEmDolar, type Painel } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/** O custo de IA das contas concluídas na semana e o médio por conta, em dólar. */
export function BlocoCustoIa({ custo }: { custo: NonNullable<Painel["custo_ia"]> }) {
  return (
    <Moldura titulo="Custo de IA" subtitulo="Todas as chamadas de cada conta, inclusive as de uma nova análise">
      <Numero>{textoEmDolar(custo.total_usd)}</Numero>
      <Apoio>
        {textoEmDolar(custo.medio_por_conta_usd)} por conta, em {custo.contas}{" "}
        {custo.contas === 1 ? "conta" : "contas"}
      </Apoio>
    </Moldura>
  );
}
