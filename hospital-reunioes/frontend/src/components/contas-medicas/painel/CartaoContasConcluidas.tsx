import type { Painel } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/** Quantas contas foram concluídas na semana. */
export function CartaoContasConcluidas({ contas }: { contas: NonNullable<Painel["contas_concluidas"]> }) {
  return (
    <Moldura titulo="Contas concluídas">
      <Numero>{contas.total}</Numero>
      <Apoio>{contas.total === 1 ? "conta na semana" : "contas na semana"}</Apoio>
    </Moldura>
  );
}
