import { AlertCircle, Check, Loader2, Plus, X } from "lucide-react";
import { Select } from "@/components/ui/Select";
import {
  type MapeamentoDeColunas,
  type PropostaDeMapeamento,
  plural,
} from "@/lib/contas-medicas/operadoras";

/**
 * O mapeamento das colunas de uma tabela em PDF ou planilha (issue #1146): a
 * pessoa vê a coluna que a IA apontou para cada campo, ajusta, pede a amostra
 * de novo e confirma. A amostra são os 20 primeiros itens convertidos, com o
 * total do arquivo. Nada é gravado antes de "Confirmar e gravar", e o botão só
 * vale quando a amostra na tela é a do mapeamento escolhido.
 */

const ORIGEM: Record<PropostaDeMapeamento["origem"], string> = {
  IA: "A IA propôs as colunas. Confira a amostra antes de confirmar.",
  CONFIRMADO: "Mesmo cabeçalho de uma tabela já confirmada: o mapeamento foi reaproveitado, sem IA.",
  PESSOA: "Amostra com o seu ajuste.",
};

const NENHUMA = "";

const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_SECUNDARIO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm font-medium disabled:opacity-50";

function preco(valor: number | string | null): string {
  if (typeof valor === "number") return valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
  return valor ?? "";
}

export function MapeamentoDaTabela({
  proposta,
  mapeamento,
  alterado,
  ocupado,
  aoMudar,
  aoVerAmostra,
  aoConfirmar,
}: {
  proposta: PropostaDeMapeamento;
  /** O mapeamento na tela, que pode já ser o ajuste da pessoa. */
  mapeamento: MapeamentoDeColunas;
  /** O mapeamento mudou depois da última amostra. */
  alterado: boolean;
  ocupado: boolean;
  aoMudar: (mapeamento: MapeamentoDeColunas) => void;
  aoVerAmostra: () => void;
  aoConfirmar: () => void;
}) {
  const colunas = proposta.cabecalho.map((c) => ({ value: c, label: c }));
  const opcionais = [{ value: NENHUMA, label: "Nenhuma" }, ...colunas];

  function campo(nome: "codigo_alternativo" | "descricao" | "unidade", rotulo: string) {
    return (
      <Select
        label={rotulo}
        value={mapeamento[nome] ?? NENHUMA}
        onChange={(v) => aoMudar({ ...mapeamento, [nome]: v || null })}
        options={opcionais}
      />
    );
  }

  function mudarPreco(indice: number, mudanca: Partial<{ chave: string; coluna: string }>) {
    aoMudar({
      ...mapeamento,
      precos: mapeamento.precos.map((p, i) => (i === indice ? { ...p, ...mudanca } : p)),
    });
  }

  const chaves = mapeamento.precos.map((p) => p.chave);

  return (
    <section aria-label="Mapeamento das colunas" className="mt-6 border-t border-slate-100 pt-4">
      <h3 className="text-sm font-semibold text-slate-900">Mapeamento das colunas</h3>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">{ORIGEM[proposta.origem]}</p>

      <div className="grid gap-3 sm:grid-cols-4">
        <Select
          label="Código"
          value={mapeamento.codigo}
          onChange={(v) => aoMudar({ ...mapeamento, codigo: v })}
          options={colunas}
        />
        {campo("codigo_alternativo", "Código alternativo")}
        {campo("descricao", "Descrição")}
        {campo("unidade", "Unidade")}
      </div>

      <div className="mt-3 space-y-2">
        {mapeamento.precos.map((p, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] items-end">
            <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
              Nome do preço {i + 1}
              <input
                value={p.chave}
                onChange={(e) => mudarPreco(i, { chave: e.target.value.trim().toLowerCase() })}
                className={`${CAMPO} normal-case font-normal`}
              />
            </label>
            <Select
              label={`Coluna do preço ${i + 1}`}
              value={p.coluna}
              onChange={(v) => mudarPreco(i, { coluna: v })}
              options={colunas}
            />
            <button
              type="button"
              aria-label={`Tirar o preço ${i + 1}`}
              disabled={mapeamento.precos.length === 1}
              onClick={() => aoMudar({ ...mapeamento, precos: mapeamento.precos.filter((_, j) => j !== i) })}
              className="p-2 text-slate-500 hover:text-slate-700 disabled:opacity-30"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            aoMudar({ ...mapeamento, precos: [...mapeamento.precos, { chave: "", coluna: proposta.cabecalho[0] }] })
          }
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          <Plus className="w-3.5 h-3.5" aria-hidden="true" /> Outro preço (por plano ou acomodação)
        </button>
        <p className="text-xs text-slate-500">
          Um preço só se chama valor. Com um preço por plano, o nome é o do plano em minúsculas (comum, carioca).
        </p>
      </div>

      {proposta.erro ? (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700 mt-4 break-words">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {proposta.erro}
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-700 mt-4">
            {plural(proposta.total, "item no arquivo", "itens no arquivo")}. A amostra mostra os{" "}
            {proposta.amostra.length} primeiros.
          </p>
          <div className="overflow-x-auto mt-2">
            <table aria-label="Amostra da tabela" className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 uppercase">
                  <th className="py-1 pr-3 font-medium">Código</th>
                  <th className="py-1 pr-3 font-medium">Código alternativo</th>
                  <th className="py-1 pr-3 font-medium">Descrição</th>
                  <th className="py-1 pr-3 font-medium">Unidade</th>
                  {chaves.map((c) => (
                    <th key={c} className="py-1 pr-3 font-medium text-right">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {proposta.amostra.map((item, i) => (
                  <tr key={i}>
                    <td className="py-1 pr-3 font-mono text-slate-800">{item.codigo}</td>
                    <td className="py-1 pr-3 font-mono text-slate-600">{item.codigo_alternativo ?? ""}</td>
                    <td className="py-1 pr-3 text-slate-700">{item.descricao ?? ""}</td>
                    <td className="py-1 pr-3 text-slate-600">{item.unidade ?? ""}</td>
                    {chaves.map((c) => (
                      <td key={c} className="py-1 pr-3 text-right tabular-nums text-slate-800">
                        {preco(item.precos[c] ?? null)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="flex flex-wrap gap-3 mt-4">
        <button type="button" onClick={aoVerAmostra} disabled={ocupado || !alterado} className={BOTAO_SECUNDARIO}>
          Ver amostra com o ajuste
        </button>
        <button
          type="button"
          onClick={aoConfirmar}
          disabled={ocupado || alterado || Boolean(proposta.erro)}
          className={BOTAO}
        >
          {ocupado ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Check className="w-4 h-4" aria-hidden="true" />
          )}
          Confirmar e gravar
        </button>
      </div>
    </section>
  );
}
