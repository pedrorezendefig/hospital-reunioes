"use client";

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

/** Uma entrega dos últimos 7 dias. */
export interface Entrega {
  id: string;
  titulo: string;
  concluida_em: string;
  no_prazo: boolean;
}

export interface NumerosDe90Dias {
  no_prazo: number;
  fora_do_prazo: number;
}

export interface MeusNumerosDaPessoa {
  numeros_90_dias: NumerosDe90Dias;
  entregues_7_dias: Entrega[];
}

const TITULO = "Seus últimos 90 dias";
const TITULO_DA_LISTA = "Entregue nos últimos 7 dias";

async function cabecalhoDeAcesso(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

/** "2026-11-17" vira "17/11", sem passar por fuso. */
function diaEMes(iso: string): string {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
}

function Numero({ valor, rotulo, testId }: { valor: number; rotulo: string; testId: string }) {
  return (
    <p data-testid={testId} className="flex items-baseline gap-2">
      <b className="font-normal text-3xl tabular-nums text-text">{valor}</b>
      <span className="text-xs text-text-secondary">{rotulo}</span>
    </p>
  );
}

/**
 * Os próprios números dos últimos 90 dias (issue #1946, ADR 0104 decisões 7
 * e 9): as entregas no prazo e fora, com a régua do ranking, só de quem está
 * olhando. Quem está em dia (`emDia`, que vem do Início) vê também o que
 * entregou nos últimos 7 dias. Vem num pedido separado do resto do Início, e
 * a falha fica neste bloco. Quem não tem número recebe `null` e não vê nada.
 */
export function MeusNumeros({ emDia }: { emDia: boolean | null }) {
  const [dados, setDados] = useState<MeusNumerosDaPessoa | null | undefined>(undefined);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await fetch("/api/inicio/meus-numeros", { headers: await cabecalhoDeAcesso() });
        if (!res.ok) throw new Error(String(res.status));
        const corpo = (await res.json()) as MeusNumerosDaPessoa | null;
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

  return (
    <section aria-label={TITULO} className="bg-white rounded-2xl border border-border px-4 sm:px-8 py-6">
      <h2 className="pb-2 border-b border-border text-xs text-text-secondary">{TITULO}</h2>
      {falhou || !dados ? (
        <p role="status" className="mt-3 text-sm text-text-secondary">
          Não foi possível carregar os seus números agora. Tente de novo em instantes.
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-x-10 gap-y-3">
            <Numero valor={dados.numeros_90_dias.no_prazo} rotulo="entregas no prazo" testId="no-prazo" />
            <Numero valor={dados.numeros_90_dias.fora_do_prazo} rotulo="entregas fora do prazo" testId="fora-do-prazo" />
          </div>
          {emDia && (
            <div className="mt-6">
              <h3 className="pb-2 border-b border-border text-xs text-text-secondary">{TITULO_DA_LISTA}</h3>
              {dados.entregues_7_dias.length === 0 ? (
                <p className="mt-3 text-sm text-text-secondary">Nada entregue nos últimos 7 dias.</p>
              ) : (
                <ul aria-label={TITULO_DA_LISTA}>
                  {dados.entregues_7_dias.map((entrega, indice) => (
                    <li key={`${entrega.id}:${indice}`} className="py-2.5 border-b border-border last:border-b-0">
                      <p className="text-base text-text leading-snug break-words">{entrega.titulo}</p>
                      <p className="text-xs text-text-secondary mt-0.5">
                        {`Entregue em ${diaEMes(entrega.concluida_em)}, ${entrega.no_prazo ? "no prazo" : "fora do prazo"}`}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
