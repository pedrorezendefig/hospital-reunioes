import { textoDaNota, type Painel } from "@/lib/contas-medicas/painel";

import { Apoio, Moldura, Numero } from "./Moldura";

/** A nota média de entrada das contas concluídas na semana, com a da anterior ao lado. */
export function CartaoNotaMedia({ nota }: { nota: NonNullable<Painel["nota_media"]> }) {
  return (
    <Moldura titulo="Nota média de entrada">
      <Numero>{textoDaNota(nota.semana)}</Numero>
      <Apoio>Semana anterior: {textoDaNota(nota.anterior)}</Apoio>
    </Moldura>
  );
}
