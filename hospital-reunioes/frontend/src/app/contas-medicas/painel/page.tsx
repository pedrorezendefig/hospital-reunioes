"use client";

/**
 * O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).
 *
 * A nota média de entrada da semana, onde o R$ apontado nasce, os dez itens
 * que mais faltam, a produção de cada faturista, o R$ incluído por nível de
 * evidência e o custo de IA, com os filtros de semana, operadora e tipo de
 * conta. Quem soma é o servidor; quem decide o que cada pessoa vê também: a
 * faturista recebe só a própria linha de produção.
 *
 * Quem tem o painel completo vê o botão do segundo agente (ADR 0082, issue
 * #1523): ele mostra antes quantas contas e o custo estimado, pede
 * confirmação e o servidor relê em segundo plano. Nenhuma rotina automática
 * chama o agente.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2, ScanSearch } from "lucide-react";

import { FiltrosDoPainel } from "@/components/contas-medicas/painel/FiltrosDoPainel";
import { TelaDoPainel } from "@/components/contas-medicas/painel/TelaDoPainel";
import { detalheDoErro } from "@/lib/contas-medicas/operadoras";
import {
  hojeIso,
  type PedidoAoSegundoAgente,
  PERGUNTA_A_CADA_MS,
  ROTA_DO_SEGUNDO_AGENTE,
  rotaDoPainel,
  rotuloDaSemana,
  textoEmDolar,
  type FiltrosDoPainel as Filtros,
  type Painel,
} from "@/lib/contas-medicas/painel";
import { createClient } from "@/lib/supabase/client";

function SegundoAgente({ token, aoTerminar }: { token: string; aoTerminar: () => void }) {
  const [pedido, setPedido] = useState<PedidoAoSegundoAgente | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Sem o painel completo, o servidor responde 403 e o botão não aparece.
  const ler = useCallback(async (): Promise<PedidoAoSegundoAgente | null> => {
    const res = await fetch(ROTA_DO_SEGUNDO_AGENTE, { headers: { Authorization: `Bearer ${token}` } }).catch(
      () => null,
    );
    return res?.ok ? res.json() : null;
  }, [token]);

  useEffect(() => {
    ler().then(setPedido);
  }, [ler]);

  // Enquanto o agente relê, a tela pergunta de tempos em tempos e relê o
  // Painel quando ele termina.
  const emAndamento = pedido?.em_andamento ?? false;
  useEffect(() => {
    if (!emAndamento) return;
    const relogio = setInterval(async () => {
      const atual = await ler();
      if (!atual || atual.em_andamento) return;
      setPedido(atual);
      aoTerminar();
    }, PERGUNTA_A_CADA_MS);
    return () => clearInterval(relogio);
  }, [emAndamento, ler, aoTerminar]);

  if (!pedido || (!pedido.em_andamento && pedido.contas === 0)) return null;

  async function aoPedir() {
    if (!pedido) return;
    const pergunta =
      `Pedir ao segundo agente a releitura de ${pedido.contas} ${pedido.contas === 1 ? "conta" : "contas"}? ` +
      `Custo estimado: cerca de ${textoEmDolar(pedido.custo_estimado_usd)}.`;
    if (!window.confirm(pergunta)) return;
    setOcupado(true);
    const res = await fetch(ROTA_DO_SEGUNDO_AGENTE, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => null);
    setOcupado(false);
    if (!res?.ok) {
      setErro(res ? await detalheDoErro(res, "Não foi possível chamar o segundo agente.") : "Não foi possível chamar o segundo agente.");
      return;
    }
    setErro(null);
    setPedido(await res.json());
  }

  return (
    <section
      aria-label="Segundo agente"
      className="bg-white rounded-2xl border border-border shadow-premium p-5 flex flex-wrap items-center justify-between gap-3"
    >
      {pedido.em_andamento ? (
        <p className="flex items-center gap-2 text-sm text-slate-600">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          O segundo agente está relendo as contas. O Painel atualiza sozinho quando ele terminar.
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-600 max-w-xl">
            O segundo agente relê {pedido.contas} {pedido.contas === 1 ? "conta concluída" : "contas concluídas"} que
            ele ainda não revisou, atrás do que foi dado ao paciente e não foi cobrado. Custo estimado: cerca de{" "}
            {textoEmDolar(pedido.custo_estimado_usd)}.
          </p>
          <button
            type="button"
            disabled={ocupado}
            onClick={aoPedir}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50"
          >
            {ocupado ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <ScanSearch className="w-4 h-4" aria-hidden="true" />
            )}
            Reler contas concluídas
          </button>
        </>
      )}
      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700 w-full">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}
    </section>
  );
}

export default function PainelPage() {
  const [token, setToken] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<Filtros>({ semana: hojeIso(), operadora: "", tipo: "" });
  const [painel, setPainel] = useState<Painel | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  // Sobe quando o segundo agente termina: o Painel é pedido de novo.
  const [recarga, setRecarga] = useState(0);
  const recarregar = useCallback(() => setRecarga((n) => n + 1), []);

  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data: { session } }) => {
        if (session?.access_token) setToken(session.access_token);
        else setCarregando(false);
      });
  }, []);

  useEffect(() => {
    if (!token || !filtros.semana) return;
    let vivo = true;
    setCarregando(true);
    setErro(null);
    fetch(rotaDoPainel(filtros), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!vivo) return;
        if (!res.ok) {
          setErro("Não foi possível carregar o Painel.");
          return;
        }
        setPainel(await res.json());
      })
      .catch(() => vivo && setErro("Não foi possível carregar o Painel."))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [token, filtros, recarga]);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/contas-medicas"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Contas médicas
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Painel</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          A nota da semana e onde a perda da conta nasce, pelas contas concluídas de segunda a domingo.
        </p>
      </div>

      {token && <SegundoAgente token={token} aoTerminar={recarregar} />}

      <FiltrosDoPainel filtros={filtros} operadoras={painel?.filtros.operadoras ?? []} aoMudar={setFiltros} />

      {painel && (
        <p className="flex items-center gap-2 text-sm text-slate-600">
          Semana de {rotuloDaSemana(painel.semana)}
          {carregando && <Loader2 className="w-4 h-4 animate-spin text-slate-400" aria-label="Carregando" />}
        </p>
      )}

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      {!painel && carregando && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando o Painel
        </div>
      )}

      {painel && <TelaDoPainel painel={painel} />}
    </div>
  );
}
