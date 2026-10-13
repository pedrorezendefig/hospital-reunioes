import { textoDaTaxa, type Painel } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/** A taxa de Não procede: linhas Não procede sobre as apontadas, sem Validar. */
export function CartaoNaoProcede({ naoProcede }: { naoProcede: NonNullable<Painel["nao_procede"]> }) {
  return (
    <Moldura titulo="Não procede">
      <Numero>{textoDaTaxa(naoProcede.taxa)}</Numero>
      <Apoio>
        {naoProcede.linhas} de {naoProcede.de} {naoProcede.de === 1 ? "linha" : "linhas"}
      </Apoio>
    </Moldura>
  );
}
