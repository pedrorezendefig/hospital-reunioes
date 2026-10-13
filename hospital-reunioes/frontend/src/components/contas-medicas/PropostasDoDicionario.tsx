"use client";

/**
 * As propostas da IA para o dicionário de itens (issue #1135, PRD #1128).
 *
 * O termo de medicamento da prescrição que não casa com nenhum item da conta
 * vai uma vez à IA, que propõe o código. A proposta já vale na análise das
 * contas seguintes; aqui a gestão confirma ou rejeita. Rejeitar tira o código
 * e deixa o termo decidido, sem par. Quem recusa é o servidor.
 */

import { useEffect, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { detalheDoErro } from "@/lib/contas-medicas/operadoras";

interface Proposta {
  id: string;
  termo: string;
  codigo_conta: string;
  descricao_conta: string | null;
}

type Decisao = "confirmar" | "rejeitar";

const ROTA = "/api/contas-medicas/dicionario/propostas";
const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-6";
const BOTAO = "px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50";

export function PropostasDoDicionario({ token }: { token: string | null }) {
  const [propostas, setPropostas] = useState<Proposta[] | null>(null);
  const [falhaAoCarregar, setFalhaAoCarregar] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupada, setOcupada] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let viva = true;
    fetch(ROTA, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!viva) return;
        if (!res.ok) {
          setFalhaAoCarregar(true);
          return;
        }
        setPropostas((await res.json()).propostas);
      })
      .catch(() => viva && setFalhaAoCarregar(true));
    return () => {
      viva = false;
    };
  }, [token]);

  async function decidir(proposta: Proposta, decisao: Decisao) {
    if (!token) return;
    setOcupada(proposta.id);
    setErro(null);
    try {
      const res = await fetch(`${ROTA}/${proposta.id}/${decisao}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `Não foi possível ${decisao} a proposta (HTTP ${res.status}).`));
        return;
      }
      setPropostas((atuais) => (atuais ?? []).filter((p) => p.id !== proposta.id));
    } catch {
      setErro(`Não foi possível ${decisao} a proposta.`);
    } finally {
      setOcupada(null);
    }
  }

  return (
    <section aria-label="Propostas da IA para o dicionário" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Propostas da IA para o dicionário</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        Nomes da prescrição que o dicionário não ligava a nenhum item da conta. A IA propôs o código uma vez, e a
        proposta já vale nas análises seguintes. Confirmar mantém o código; rejeitar deixa o termo sem código.
      </p>
      {falhaAoCarregar ? (
        <p className="text-sm text-slate-500">Não foi possível carregar as propostas.</p>
      ) : propostas === null ? (
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando propostas
        </p>
      ) : propostas.length === 0 ? (
        <p className="text-sm text-slate-500">Nenhuma proposta à espera.</p>
      ) : (
        <ul className="divide-y divide-border">
          {propostas.map((proposta) => (
            <li
              key={proposta.id}
              data-testid={`proposta-${proposta.id}`}
              className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-900 break-words">{proposta.termo}</p>
                <p className="text-xs text-slate-500 break-words">
                  Código proposto <span className="font-mono">{proposta.codigo_conta}</span>
                  {proposta.descricao_conta ? `, ${proposta.descricao_conta}` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => decidir(proposta, "confirmar")}
                disabled={ocupada !== null}
                className={`${BOTAO} bg-primary text-white`}
              >
                Confirmar
              </button>
              <button
                type="button"
                onClick={() => decidir(proposta, "rejeitar")}
                disabled={ocupada !== null}
                className={`${BOTAO} border border-border text-slate-700`}
              >
                Rejeitar
              </button>
            </li>
          ))}
        </ul>
      )}
      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700 mt-4">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
        </p>
      )}
    </section>
  );
}
