/**
 * A Prova da regra na tela (issue #1488, PRD #1484, ADR 0081).
 *
 * O que o Guia teria dito de diferente nas últimas contas concluídas da
 * operadora, conta a conta. Serve à proposta do "Ensinar uma regra nova" e a
 * cada regra do lote do Auditor (issue #1490).
 */

import { AlertCircle } from "lucide-react";

import { dataBr } from "@/lib/contas-medicas/operadoras";

export interface LinhaDaProva {
  acao: string;
  data: string | null;
  codigo: string | null;
  descricao: string;
  quantidade_devida: number | null;
  regra_codigo: string | null;
}

export interface ContaDaProva {
  conta_id: string;
  numero_atendimento: string | null;
  numero_conta: string | null;
  mudaria: boolean;
  entrariam: LinhaDaProva[];
  sairiam: (LinhaDaProva & { feito: boolean })[];
  mudariam: { antes: LinhaDaProva; depois: LinhaDaProva }[];
}

export interface ProvaDaRegra {
  contas: number;
  mudaria: boolean;
  feitas_que_sumiriam: number;
  aviso: string | null;
  por_conta: ContaDaProva[];
}

function descricaoDaLinha(linha: LinhaDaProva): string {
  return [linha.descricao, linha.data ? dataBr(linha.data) : null].filter(Boolean).join(", ");
}

/** O que o Guia teria dito de diferente em cada conta. A conta que não muda fica de fora. */
export function ProvaDaRegraNaTela({ prova }: { prova: ProvaDaRegra }) {
  const mudaram = prova.por_conta.filter((c) => c.mudaria);
  const feitas = prova.feitas_que_sumiriam;
  return (
    <section aria-label="Prova da regra" className="rounded-lg bg-white border border-slate-200 p-3 text-sm space-y-2">
      <h3 className="text-xs font-semibold text-slate-500 uppercase">Prova da regra</h3>
      <p className="text-slate-700">
        Refeita nas {prova.contas} últimas contas concluídas da operadora. Nenhuma conta foi alterada.
      </p>
      {prova.aviso && <p className="text-amber-700 font-medium">{prova.aviso}</p>}
      {feitas > 0 && (
        <p role="alert" className="flex items-start gap-2 text-red-700 font-medium">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          {feitas === 1
            ? "1 linha já feita pela faturista sumiria."
            : `${feitas} linhas já feitas pela faturista sumiriam.`}
        </p>
      )}
      {mudaram.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {mudaram.map((c) => {
            const rotulo = `Atendimento ${c.numero_atendimento ?? ""}, conta ${c.numero_conta ?? ""}`;
            return (
              <li key={c.conta_id} aria-label={rotulo} className="py-2 space-y-1">
                <p className="font-semibold text-slate-900">{rotulo}</p>
                {c.entrariam.map((l, i) => (
                  <p key={`e-${i}`} className="text-emerald-700">
                    Entraria: {descricaoDaLinha(l)}
                  </p>
                ))}
                {c.sairiam.map((l, i) => (
                  <p key={`s-${i}`} className="text-slate-700">
                    Sairia: {descricaoDaLinha(l)}
                    {l.feito && <span className="ml-2 text-xs font-semibold text-red-700">Já feita</span>}
                  </p>
                ))}
                {c.mudariam.map((m, i) => (
                  <p key={`m-${i}`} className="text-slate-700">
                    Mudaria: {m.depois.descricao}, quantidade {m.antes.quantidade_devida ?? ""} para{" "}
                    {m.depois.quantidade_devida ?? ""}
                  </p>
                ))}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
