import { textoEmReais, type Painel } from "@/lib/contas-medicas/painel";

import { Moldura } from "./Moldura";

/** Os códigos com mais contas com linha Incluir: a fila de parametrização para a consultoria do MV. */
export function BlocoItensQueFaltam({ itens }: { itens: NonNullable<Painel["itens_que_faltam"]> }) {
  return (
    <Moldura titulo="Os dez itens que mais faltam" subtitulo="Fila de parametrização para a consultoria do MV">
      {itens.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">Nenhum item faltando nesta semana.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="py-1.5 font-medium">Código</th>
              <th className="py-1.5 font-medium">Item</th>
              <th className="py-1.5 font-medium text-right">Contas</th>
              <th className="py-1.5 font-medium text-right">R$</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((item) => (
              <tr key={item.codigo} className="border-t border-slate-100">
                <td className="py-1.5 font-mono text-xs text-slate-600">{item.codigo}</td>
                <td className="py-1.5 text-slate-800">{item.descricao}</td>
                <td className="py-1.5 text-right font-semibold tabular-nums text-primary">{item.contas}</td>
                <td className="py-1.5 text-right tabular-nums text-slate-700">{textoEmReais(item.valor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Moldura>
  );
}
