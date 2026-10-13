import { textoEmReais, type Painel } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/** O R$ apontado nas contas da semana, com quanto disso já entrou no MV (as linhas Feito). */
export function CartaoValorApontado({ valor }: { valor: NonNullable<Painel["valor_apontado"]> }) {
  return (
    <Moldura titulo="R$ apontado">
      <Numero>{textoEmReais(valor.total)}</Numero>
      <Apoio>Já incluídos: {textoEmReais(valor.ja_incluido)}</Apoio>
    </Moldura>
  );
}
