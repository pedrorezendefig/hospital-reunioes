"use client";

/**
 * A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).
 *
 * Três números no topo (aguardando decisão, contas afetadas, R$ em jogo) e um
 * cartão por tema: regra pendente, código bloqueado, observação do time ou
 * termo do dicionário, na ordem do servidor (maior R$ em jogo primeiro). Cada
 * decisão grava no servidor e a fila é relida. A leitura da IA de cada
 * observação é pedida uma vez; o servidor guarda.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";

import { CartaoDeTema } from "@/components/contas-medicas/CartaoDeTema";
import { reais } from "@/lib/contas-medicas/guia";
import { detalheDoErro } from "@/lib/contas-medicas/operadoras";
import {
  type Decisao,
  type FilaDeValidacao,
  ROTA_DA_FILA,
  type Tema,
  decidir,
  enviarAoCadastro,
  lerObservacao,
} from "@/lib/contas-medicas/validacao";
import { createClient } from "@/lib/supabase/client";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-5";

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className={CARTAO}>
      <p className="text-xs font-semibold uppercase tracking-[0.04em] text-slate-500">{rotulo}</p>
      <p className="text-2xl font-bold text-primary mt-1">{valor}</p>
    </div>
  );
}

export default function ValidacaoPage() {
  const [token, setToken] = useState<string | null>(null);
  const [fila, setFila] = useState<FilaDeValidacao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [falhasDaLeitura, setFalhasDaLeitura] = useState<Record<string, string>>({});
  const lidas = useRef(new Set<string>());

  const carregar = useCallback(async (tk: string) => {
    try {
      const res = await fetch(ROTA_DA_FILA, { headers: { Authorization: `Bearer ${tk}` } });
      if (res.status === 403) {
        setErro("Esta fila é de quem tem a permissão de decidir na validação.");
        setFila(null);
        return;
      }
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível carregar a fila de Validação."));
        return;
      }
      setErro(null);
      setFila(await res.json());
    } catch {
      setErro("Não foi possível carregar a fila de Validação.");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data: { session } }) => {
        const tk = session?.access_token ?? null;
        setToken(tk);
        if (tk) carregar(tk);
        else {
          setErro("Sessão expirada. Entre de novo.");
          setCarregando(false);
        }
      });
  }, [carregar]);

  // A leitura da IA de cada observação sem leitura: um pedido por tema.
  useEffect(() => {
    if (!token || !fila) return;
    for (const tema of fila.temas) {
      if (tema.tipo !== "OBSERVACAO" || tema.leitura_ia || lidas.current.has(tema.id)) continue;
      lidas.current.add(tema.id);
      lerObservacao(token, tema)
        .catch(() => ({ leitura: undefined, erro: "Não foi possível ler a observação." }))
        .then(({ leitura, erro: falha }) => {
          if (!leitura) {
            setFalhasDaLeitura((atual) => ({ ...atual, [tema.id]: falha ?? "Não foi possível ler a observação." }));
            return;
          }
          setFila((atual) =>
            atual
              ? { ...atual, temas: atual.temas.map((t) => (t.id === tema.id ? { ...t, leitura_ia: leitura } : t)) }
              : atual,
          );
        });
    }
  }, [token, fila]);

  async function aoDecidir(tema: Tema, decisao: Decisao, corpo?: { texto?: string }) {
    if (!token) return;
    setOcupado(tema.id);
    const falha = await decidir(token, tema, decisao, corpo);
    setOcupado(null);
    if (falha) {
      setErro(falha);
      return;
    }
    await carregar(token);
  }

  async function aoEnviarAoCadastro(tema: Tema) {
    if (!token) return;
    setOcupado(tema.id);
    const falha = await enviarAoCadastro(token, tema);
    setOcupado(null);
    if (falha) {
      setErro(falha);
      return;
    }
    await carregar(token);
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/contas-medicas"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Contas médicas
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Validação</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          Regras pendentes, códigos bloqueados e observações do time, por tema, com quantas contas e quanto dinheiro
          esperam a sua decisão.
        </p>
      </div>

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      {carregando && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando a fila de Validação
        </div>
      )}

      {fila && (
        <>
          <section aria-label="Números da Validação" className="grid gap-4 sm:grid-cols-3">
            <Numero rotulo="Aguardando decisão" valor={String(fila.numeros.aguardando_decisao)} />
            <Numero rotulo="Contas afetadas" valor={String(fila.numeros.contas_afetadas)} />
            <Numero rotulo="R$ em jogo" valor={`R$ ${reais(fila.numeros.valor_em_jogo)}`} />
          </section>

          {fila.temas.length === 0 ? (
            <p className="text-sm text-slate-500">Nada aguardando decisão.</p>
          ) : (
            <div className="space-y-4">
              {fila.temas.map((tema) => (
                <CartaoDeTema
                  key={tema.id}
                  tema={tema}
                  ocupado={ocupado === tema.id}
                  falhaDaLeitura={falhasDaLeitura[tema.id]}
                  onDecidir={(decisao, corpo) => aoDecidir(tema, decisao, corpo)}
                  onEnviarAoCadastro={() => aoEnviarAoCadastro(tema)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
