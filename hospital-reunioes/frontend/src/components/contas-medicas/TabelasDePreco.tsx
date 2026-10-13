import {
  CATEGORIAS_DE_ENVIO,
  type TabelaDaCategoria,
  rotuloDaCategoria,
  vigencia,
} from "@/lib/contas-medicas/operadoras";

/**
 * As tabelas de preço de uma operadora, uma linha por versão (issues #1120 e
 * #1140): a categoria, a tabela, a versão, a vigência e a situação. "Em uso" é
 * a versão que a busca de preço escolhe hoje; as outras ficam guardadas.
 *
 * Com `aoPedirNovaVersao`, a primeira linha de cada categoria que recebe
 * tabela pela tela ganha o botão "Nova versão" (a biblioteca de tabelas).
 */
export function TabelasDePreco({
  rotulo,
  tabelas,
  aoPedirNovaVersao,
}: {
  rotulo: string;
  tabelas: TabelaDaCategoria[];
  aoPedirNovaVersao?: (categoria: string) => void;
}) {
  function novaVersao(categoria: string) {
    if (!aoPedirNovaVersao) return null;
    return (
      <td className="py-1">
        {CATEGORIAS_DE_ENVIO.includes(categoria) && (
          <button
            type="button"
            onClick={() => aoPedirNovaVersao(categoria)}
            className="text-xs font-medium text-primary hover:underline whitespace-nowrap"
          >
            Nova versão
          </button>
        )}
      </td>
    );
  }

  return (
    <table aria-label={rotulo} className="w-full text-xs mt-2">
      <thead>
        <tr className="text-left text-slate-500 uppercase">
          <th className="py-1 pr-3 font-medium">Categoria</th>
          <th className="py-1 pr-3 font-medium">Tabela</th>
          <th className="py-1 pr-3 font-medium">Versão</th>
          <th className="py-1 pr-3 font-medium">Vigência</th>
          <th className="py-1 pr-3 font-medium">Situação</th>
          {aoPedirNovaVersao && <th className="py-1 font-medium" aria-label="Ação" />}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {tabelas.flatMap((t) =>
          t.versoes.length === 0
            ? [
                <tr key={t.categoria}>
                  <td className="py-1 pr-3 text-slate-800">{rotuloDaCategoria(t.categoria)}</td>
                  <td className="py-1 pr-3 text-slate-500">{t.tipo ?? ""}</td>
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3 text-slate-500">Não carregada</td>
                  {novaVersao(t.categoria)}
                </tr>,
              ]
            : t.versoes.map((v, i) => (
                <tr key={`${t.categoria}-${i}`}>
                  <td className="py-1 pr-3 text-slate-800">{i === 0 ? rotuloDaCategoria(t.categoria) : ""}</td>
                  <td className="py-1 pr-3 text-slate-600 break-all">{v.tabela}</td>
                  <td className="py-1 pr-3 text-slate-600">{v.versao ?? ""}</td>
                  <td className="py-1 pr-3 text-slate-600">{vigencia(v)}</td>
                  <td className={`py-1 pr-3 ${v.em_uso ? "text-emerald-700 font-medium" : "text-slate-500"}`}>
                    {v.em_uso ? "Em uso" : "Guardada"}
                  </td>
                  {i === 0 ? novaVersao(t.categoria) : aoPedirNovaVersao && <td className="py-1" />}
                </tr>
              )),
        )}
      </tbody>
    </table>
  );
}
