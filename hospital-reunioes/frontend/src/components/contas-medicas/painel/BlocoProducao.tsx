import { textoDaTaxa, textoEmReais, type Painel } from "@/lib/contas-medicas/painel";

import { Moldura } from "./Moldura";

/**
 * A produção de cada faturista na semana: contas e valor lado a lado, com o
 * R$ retirado (glosa evitada) em segundo plano. A faturista recebe só a dela.
 */
export function BlocoProducao({ linhas }: { linhas: Painel["producao"] }) {
  return (
    <Moldura titulo="Produção por faturista">
      {linhas.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">Nenhuma conta concluída nesta semana.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="py-1.5 font-medium">Faturista</th>
                <th className="py-1.5 font-medium text-right">Contas</th>
                <th className="py-1.5 font-medium text-right">Com pendência</th>
                <th className="py-1.5 font-medium text-right">R$ incluído</th>
                <th className="py-1.5 font-medium text-right">Não procede</th>
                <th className="py-1.5 font-medium text-right text-slate-400">R$ retirado</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((linha) => (
                <tr key={linha.faturista_id ?? "sem-faturista"} className="border-t border-slate-100">
                  <td className="py-1.5 text-slate-800">{linha.nome ?? "Sem faturista"}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums text-primary">{linha.contas}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-700">{linha.com_pendencia}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums text-primary">
                    {textoEmReais(linha.valor_incluido)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-slate-700">{textoDaTaxa(linha.taxa_nao_procede)}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-400">{textoEmReais(linha.valor_retirado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Moldura>
  );
}
