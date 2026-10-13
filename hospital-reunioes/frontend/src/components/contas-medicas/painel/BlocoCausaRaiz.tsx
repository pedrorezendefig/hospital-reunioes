import {
  QUEM_CORRIGE,
  ROTULO_CAUSA,
  textoDoPercentual,
  textoEmReais,
  type Painel,
} from "@/lib/contas-medicas/painel";

import { COR_DO_TRILHO, COR_PRIMARIA } from "./cores";
import { Moldura } from "./Moldura";

/** O R$ apontado por causa-raiz, com o percentual de cada uma e quem corrige. */
export function BlocoCausaRaiz({ causas }: { causas: NonNullable<Painel["causa_raiz"]> }) {
  return (
    <Moldura titulo="R$ apontado por causa-raiz" subtitulo="Onde o problema nasce e quem corrige">
      <ul className="space-y-3">
        {causas.map((c) => (
          <li key={c.causa} className="space-y-1.5">
            <div className="flex items-baseline gap-3 text-sm">
              <span className="font-medium text-slate-800">{ROTULO_CAUSA[c.causa]}</span>
              <span className="hidden sm:inline text-xs text-slate-500">{QUEM_CORRIGE[c.causa]}</span>
              <span className="ml-auto font-semibold tabular-nums text-primary">{textoDoPercentual(c.percentual)}</span>
              <span className="w-28 text-right text-xs tabular-nums text-slate-500">{textoEmReais(c.valor)}</span>
            </div>
            <div aria-hidden="true" className="h-2 overflow-hidden rounded-full" style={{ backgroundColor: COR_DO_TRILHO }}>
              <div className="h-full rounded-full" style={{ width: `${c.percentual}%`, backgroundColor: COR_PRIMARIA }} />
            </div>
          </li>
        ))}
      </ul>
    </Moldura>
  );
}
