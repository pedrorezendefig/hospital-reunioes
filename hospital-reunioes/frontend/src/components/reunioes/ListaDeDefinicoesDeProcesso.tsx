"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";

/**
 * A tela das Definições de processo do setor (issue #1875, ADR 0098, decisão 9).
 *
 * As linhas do tipo Processo das atas enviadas, agrupadas pelo setor da
 * reunião, com o trecho da ata copiado. Sem responsável nem lembrete: é só
 * consulta. Tirar da lista pede anotação; quem pode tirar vem do servidor.
 */

export interface DefinicaoDeProcesso {
  id: string;
  id_reuniao: string;
  reuniao_titulo: string | null;
  reuniao_data: string | null;
  setor_id: string | null;
  setor_nome: string | null;
  trecho: string;
  objetivo: string | null;
  created_at: string | null;
  pode_retirar: boolean;
}

const SEM_SETOR = "Reunião sem setor";

/** "2026-11-10" vira "10/11/2026", sem passar por fuso. */
function dataBr(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

async function cabecalho(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

function agrupar(itens: DefinicaoDeProcesso[]): [string, DefinicaoDeProcesso[]][] {
  const grupos = new Map<string, DefinicaoDeProcesso[]>();
  for (const item of itens) {
    const setor = item.setor_nome || SEM_SETOR;
    grupos.set(setor, [...(grupos.get(setor) ?? []), item]);
  }
  return [...grupos.entries()];
}

function FormularioDeAnotacao({
  aoConfirmar,
  aoCancelar,
}: {
  aoConfirmar: (anotacao: string) => Promise<void>;
  aoCancelar: () => void;
}) {
  const [anotacao, setAnotacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const pronto = anotacao.trim().length > 0;

  async function confirmar() {
    if (!pronto) return;
    setEnviando(true);
    await aoConfirmar(anotacao.trim());
    setEnviando(false);
  }

  return (
    <div className="mt-2 p-3 rounded-xl border border-primary/30 bg-primary/5 space-y-2">
      <label className="block">
        <span className="text-xs font-semibold text-slate-600">Anotação (obrigatória)</span>
        <textarea
          value={anotacao}
          onChange={(e) => setAnotacao(e.target.value)}
          placeholder="Diga por que o item sai da lista: repetido ou deixou de valer."
          className="mt-1 w-full min-h-[70px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={confirmar}
          disabled={!pronto || enviando}
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {enviando ? "Registrando..." : "Confirmar"}
        </button>
        <button
          type="button"
          onClick={aoCancelar}
          className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50"
        >
          Voltar
        </button>
      </div>
    </div>
  );
}

export function ListaDeDefinicoesDeProcesso() {
  const [itens, setItens] = useState<DefinicaoDeProcesso[] | null>(null);
  const [tirando, setTirando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const res = await fetch("/api/definicoes-processo", { headers: await cabecalho() });
    setItens(res.ok ? ((await res.json()) as DefinicaoDeProcesso[]) : []);
  }, []);

  useEffect(() => {
    carregar().catch(() => setItens([]));
  }, [carregar]);

  async function retirar(id: string, anotacao: string) {
    setErro(null);
    try {
      const res = await fetch(`/api/definicoes-processo/${id}/retirar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(await cabecalho()) },
        body: JSON.stringify({ anotacao }),
      });
      if (!res.ok) {
        const dados = await res.json().catch(() => ({}));
        setErro(typeof dados.detail === "string" ? dados.detail : "Não deu para tirar da lista agora. Tente de novo.");
        return;
      }
      setTirando(null);
      await carregar();
    } catch {
      setErro("Sem conexão. Tente de novo.");
    }
  }

  if (itens === null) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando as definições de processo...
      </div>
    );
  }

  if (itens.length === 0) {
    return (
      <p className="text-sm text-text-secondary">
        Nenhuma definição de processo nos setores das reuniões que você conduz. Elas chegam aqui quando a ata é
        enviada com uma linha do tipo Processo.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {erro && (
        <p role="alert" className="text-sm text-red-600">
          {erro}
        </p>
      )}
      {agrupar(itens).map(([setor, doSetor]) => (
        <section key={setor} className="rounded-xl border border-border bg-white p-4 space-y-2">
          <h2 className="text-base text-text">{setor}</h2>
          <ul aria-label={`Definições de processo de ${setor}`} className="divide-y divide-border">
            {doSetor.map((item) => (
              <li key={item.id} className="py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm text-text break-words">{item.trecho}</p>
                    {item.objetivo && <p className="text-xs text-text-secondary mt-1">Para quê: {item.objetivo}</p>}
                    <p className="text-xs text-text-secondary mt-1">
                      Da ata de {item.reuniao_titulo || "reunião sem título"}
                      {item.reuniao_data ? `, ${dataBr(item.reuniao_data)}` : ""}.
                    </p>
                  </div>
                  {item.pode_retirar && (
                    <button
                      type="button"
                      onClick={() => setTirando(item.id)}
                      className="px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50"
                    >
                      Tirar da lista
                    </button>
                  )}
                </div>
                {tirando === item.id && (
                  <FormularioDeAnotacao
                    aoConfirmar={(anotacao) => retirar(item.id, anotacao)}
                    aoCancelar={() => setTirando(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
