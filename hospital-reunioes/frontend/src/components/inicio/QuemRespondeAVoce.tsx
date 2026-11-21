"use client";

import { Fragment, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

/** O que venceu e não foi entregue, só leitura. */
export interface ItemVencido {
  id: string;
  titulo: string;
  origem: string;
  prazo: string;
  dias_de_atraso: number;
}

/** Uma linha do bloco: a pessoa pelo nome e pelo cargo (ADR 0033), nunca pelo `role`. */
export interface PessoaQueResponde {
  id: string;
  nome: string;
  cargo: string | null;
  vencidos: number;
  em_aberto: number;
  ultimo_acesso: string;
  /** As entregas de 90 dias, a mesma conta que a pessoa vê no Início dela (issue #1946). */
  entregas_90_dias: { no_prazo: number; fora_do_prazo: number };
  itens_vencidos: ItemVencido[];
}

export interface QuemResponde {
  pessoas: PessoaQueResponde[];
}

const TITULO = "Quem responde a você";

async function cabecalhoDeAcesso(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

function Vencidos({ pessoa }: { pessoa: PessoaQueResponde }) {
  return (
    <tr>
      <td colSpan={5} className="px-3 pb-4 pt-1 bg-slate-50">
        {pessoa.itens_vencidos.length === 0 ? (
          <p className="text-sm text-text-secondary">Nada vencido e não entregue.</p>
        ) : (
          <ul aria-label={`O que venceu e não foi entregue por ${pessoa.nome}`}>
            {pessoa.itens_vencidos.map((item) => (
              <li key={item.id} className="flex flex-wrap justify-between gap-x-4 gap-y-1 py-2 border-b border-border last:border-b-0">
                <div className="min-w-0">
                  <p className="text-sm text-text break-words">{item.titulo}</p>
                  <p className="text-xs text-text-secondary mt-0.5 break-words">{item.origem}</p>
                </div>
                <span className="text-xs text-red-700 tabular-nums whitespace-nowrap">
                  {item.dias_de_atraso === 1 ? "há 1 dia" : `há ${item.dias_de_atraso} dias`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

/**
 * Quem responde a você (issue #1943, ADR 0104 decisão 9): uma linha por
 * pessoa que quem olha acompanha, com os vencidos agora, os itens em aberto,
 * as entregas de 90 dias no prazo e fora (issue #1946) e o último acesso. Vem num pedido separado do resto do Início, e a falha dele
 * fica neste bloco. Quem não acompanha ninguém recebe `null` e não vê nada.
 * Clicar na linha, ou apertar Enter nela, abre ali mesmo o que venceu e não
 * foi entregue. No celular a tabela rola dentro do bloco.
 */
export function QuemRespondeAVoce() {
  const [dados, setDados] = useState<QuemResponde | null | undefined>(undefined);
  const [falhou, setFalhou] = useState(false);
  const [aberta, setAberta] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await fetch("/api/inicio/quem-responde", { headers: await cabecalhoDeAcesso() });
        if (!res.ok) throw new Error(String(res.status));
        const corpo = (await res.json()) as QuemResponde | null;
        if (vivo) setDados(corpo);
      } catch {
        if (vivo) setFalhou(true);
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  if (!falhou && !dados) return null;

  const alternar = (id: string) => setAberta((atual) => (atual === id ? null : id));

  return (
    <section aria-label={TITULO} className="bg-white rounded-2xl border border-border px-4 sm:px-8 py-6">
      <h2 className="pb-2 border-b border-border text-xs text-text-secondary">{TITULO}</h2>
      {falhou ? (
        <p role="status" className="mt-3 text-sm text-text-secondary">
          Não foi possível carregar quem responde a você agora. Tente de novo em instantes.
        </p>
      ) : dados && dados.pessoas.length === 0 ? (
        <p className="mt-3 text-base text-text">Ninguém com item em aberto agora.</p>
      ) : (
        <div data-testid="rolagem-quem-responde" className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left">
            <thead>
              <tr className="text-[11px] text-text-secondary">
                <th className="px-3 py-2 font-normal">Pessoa</th>
                <th className="px-3 py-2 font-normal text-right">Vencidos agora</th>
                <th className="px-3 py-2 font-normal text-right">Em aberto</th>
                <th className="px-3 py-2 font-normal">Entregas em 90 dias</th>
                <th className="px-3 py-2 font-normal">Último acesso</th>
              </tr>
            </thead>
            <tbody>
              {dados?.pessoas.map((pessoa) => (
                <Fragment key={pessoa.id}>
                  <tr
                    tabIndex={0}
                    aria-expanded={aberta === pessoa.id}
                    onClick={() => alternar(pessoa.id)}
                    onKeyDown={(evento) => {
                      if (evento.key === "Enter") {
                        evento.preventDefault();
                        alternar(pessoa.id);
                      }
                    }}
                    className="cursor-pointer border-t border-border hover:bg-slate-50 focus:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <td className="px-3 py-3">
                      <p className="text-base text-text leading-snug">{pessoa.nome}</p>
                      {pessoa.cargo && <p className="text-xs text-text-secondary mt-0.5">{pessoa.cargo}</p>}
                    </td>
                    <td className={`px-3 py-3 text-right text-xl tabular-nums ${pessoa.vencidos ? "text-red-700" : "text-text"}`}>
                      {pessoa.vencidos}
                    </td>
                    <td className="px-3 py-3 text-right text-xl tabular-nums text-text">{pessoa.em_aberto}</td>
                    <td className="px-3 py-3 text-sm text-text whitespace-nowrap tabular-nums">
                      {`${pessoa.entregas_90_dias.no_prazo} no prazo, ${pessoa.entregas_90_dias.fora_do_prazo} fora`}
                    </td>
                    <td className="px-3 py-3 text-sm text-text-secondary whitespace-nowrap">{pessoa.ultimo_acesso}</td>
                  </tr>
                  {aberta === pessoa.id && <Vencidos pessoa={pessoa} />}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
