"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Select } from "@/components/ui/Select";
import { createClient } from "@/lib/supabase/client";

/**
 * A tela das Rotinas (issue #1874, ADR 0098, decisão 9).
 *
 * Cada Rotina mostra os ciclos em aberto (o de agora e os que fecharam sem
 * marcação). Realizada é um clique; Não realizada pede anotação. O
 * Facilitador marca pelo responsável que não entra no app e encerra a Rotina,
 * também com anotação. Quem pode o quê vem do servidor.
 *
 * A Rotina que veio do fluxo contínuo antigo nasce sem frequência (issue
 * #1877): não tem ciclo até o Facilitador escolher, aqui mesmo.
 */

interface CicloEmAberto {
  inicio: string;
  fim: string;
  atrasado: boolean;
}

interface Verificacao {
  ciclo_inicio: string;
  ciclo_fim: string;
  resultado: "REALIZADA" | "NAO_REALIZADA";
  anotacao: string | null;
  atrasada: boolean;
  marcada_por_nome: string;
}

export interface Rotina {
  id: string;
  id_reuniao: string;
  reuniao_titulo: string | null;
  descricao: string;
  responsavel_nome: string;
  frequencia: "SEMANAL" | "QUINZENAL" | "MENSAL" | null;
  status: "ATIVA" | "ENCERRADA";
  encerrada_em: string | null;
  anotacao_encerramento: string | null;
  ciclos_em_aberto: CicloEmAberto[];
  verificacoes: Verificacao[];
  pode_marcar: boolean;
  pode_encerrar: boolean;
  pode_escolher_frequencia?: boolean;
}

const FREQUENCIA: Record<string, string> = { SEMANAL: "semanal", QUINZENAL: "quinzenal", MENSAL: "mensal" };
const OPCOES_DE_FREQUENCIA = [
  { value: "SEMANAL", label: "Semanal" },
  { value: "QUINZENAL", label: "Quinzenal" },
  { value: "MENSAL", label: "Mensal" },
];

function EscolhaDaFrequencia({
  descricao,
  aoSalvar,
}: {
  descricao: string;
  aoSalvar: (frequencia: string) => Promise<void>;
}) {
  const [frequencia, setFrequencia] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    if (!frequencia) return;
    setSalvando(true);
    await aoSalvar(frequencia);
    setSalvando(false);
  }

  return (
    <div
      role="group"
      aria-label={`Frequência de ${descricao}`}
      className="p-3 rounded-xl border border-primary/30 bg-primary/5 space-y-2"
    >
      <p className="text-xs text-slate-600">
        Era fluxo contínuo. Escolha a frequência: o primeiro ciclo cobrado é o seguinte ao de hoje.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={frequencia}
          onChange={setFrequencia}
          placeholder="Escolha a frequência"
          options={OPCOES_DE_FREQUENCIA}
          className="w-56"
        />
        <button
          type="button"
          onClick={salvar}
          disabled={!frequencia || salvando}
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {salvando ? "Salvando..." : "Salvar a frequência"}
        </button>
      </div>
    </div>
  );
}

/** "2026-11-30" vira "30/11", sem passar por fuso. */
function diaEMes(iso: string): string {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
}

async function cabecalho(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

/** O que pede anotação: Não realizada de um ciclo, ou o encerramento. */
type Pedido = { tipo: "nao_realizada"; rotina: string; inicio: string } | { tipo: "encerrar"; rotina: string };

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
          placeholder="Conte o que aconteceu."
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

export function ListaDeRotinas() {
  const [rotinas, setRotinas] = useState<Rotina[] | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const res = await fetch("/api/rotinas", { headers: await cabecalho() });
    setRotinas(res.ok ? ((await res.json()) as Rotina[]) : []);
  }, []);

  useEffect(() => {
    carregar().catch(() => setRotinas([]));
  }, [carregar]);

  // O Início (issue #1944) chega com #rotina-<id>: a lista vem depois do
  // primeiro desenho, então a rolagem até a Rotina espera ela chegar.
  const carregou = rotinas !== null;
  useEffect(() => {
    if (!carregou || !window.location.hash.startsWith("#rotina-")) return;
    document.getElementById(decodeURIComponent(window.location.hash.slice(1)))?.scrollIntoView();
  }, [carregou]);

  async function enviar(url: string, corpo?: Record<string, string>) {
    setErro(null);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { ...(corpo ? { "Content-Type": "application/json" } : {}), ...(await cabecalho()) },
        ...(corpo ? { body: JSON.stringify(corpo) } : {}),
      });
      if (!res.ok) {
        const dados = await res.json().catch(() => ({}));
        setErro(typeof dados.detail === "string" ? dados.detail : "Não deu para registrar agora. Tente de novo.");
        return;
      }
      setPedido(null);
      await carregar();
    } catch {
      setErro("Sem conexão. Tente de novo.");
    }
  }

  if (rotinas === null) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando as Rotinas...
      </div>
    );
  }

  if (rotinas.length === 0) {
    return <p className="text-sm text-text-secondary">Nenhuma Rotina no seu nome ou nas reuniões que você conduz.</p>;
  }

  return (
    <div className="space-y-4">
      {erro && (
        <p role="alert" className="text-sm text-red-600">
          {erro}
        </p>
      )}
      {rotinas.map((rotina) => {
        const frequencia = rotina.frequencia ? FREQUENCIA[rotina.frequencia] : "sem frequência";
        return (
          <section
            key={rotina.id}
            id={`rotina-${rotina.id}`}
            className="scroll-mt-4 rounded-xl border border-border bg-white p-4 space-y-3">
            <header className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-base text-text break-words">{rotina.descricao}</h2>
                <p className="text-xs text-text-secondary mt-1">
                  Rotina {frequencia}
                  {rotina.reuniao_titulo ? ` da ${rotina.reuniao_titulo}` : ""}. Responsável: {rotina.responsavel_nome || "sem nome"}.
                </p>
                {rotina.status === "ENCERRADA" && (
                  <p className="text-xs text-text-secondary mt-1">
                    Encerrada em {rotina.encerrada_em ? diaEMes(rotina.encerrada_em) : ""}: {rotina.anotacao_encerramento}
                  </p>
                )}
              </div>
              {rotina.pode_encerrar && (
                <button
                  type="button"
                  onClick={() => setPedido({ tipo: "encerrar", rotina: rotina.id })}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50"
                >
                  Encerrar a Rotina
                </button>
              )}
            </header>
            {!rotina.frequencia &&
              rotina.status === "ATIVA" &&
              (rotina.pode_escolher_frequencia ? (
                <EscolhaDaFrequencia
                  descricao={rotina.descricao}
                  aoSalvar={(escolhida) => enviar(`/api/rotinas/${rotina.id}/frequencia`, { frequencia: escolhida })}
                />
              ) : (
                <p className="text-xs text-text-secondary">
                  Sem ciclo por enquanto: o facilitador da reunião escolhe a frequência.
                </p>
              ))}
            {pedido?.tipo === "encerrar" && pedido.rotina === rotina.id && (
              <FormularioDeAnotacao
                aoConfirmar={(anotacao) => enviar(`/api/rotinas/${rotina.id}/encerrar`, { anotacao })}
                aoCancelar={() => setPedido(null)}
              />
            )}

            {rotina.ciclos_em_aberto.length > 0 && (
              <ul aria-label={`Ciclos em aberto de ${rotina.descricao}`} className="divide-y divide-border">
                {rotina.ciclos_em_aberto.map((ciclo) => (
                  <li key={ciclo.inicio} className="py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm text-text">
                        {diaEMes(ciclo.inicio)} a {diaEMes(ciclo.fim)}
                        {ciclo.atrasado && <span className="ml-2 text-xs text-red-700">Atrasado</span>}
                      </span>
                      {rotina.pode_marcar && (
                        <span className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => enviar(`/api/rotinas/${rotina.id}/ciclos/${ciclo.inicio}/realizada`)}
                            className="px-3 py-1.5 rounded-lg bg-primary text-white text-sm font-semibold"
                          >
                            Realizada
                          </button>
                          <button
                            type="button"
                            onClick={() => setPedido({ tipo: "nao_realizada", rotina: rotina.id, inicio: ciclo.inicio })}
                            className="px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50"
                          >
                            Não realizada
                          </button>
                        </span>
                      )}
                    </div>
                    {pedido?.tipo === "nao_realizada" &&
                      pedido.rotina === rotina.id &&
                      pedido.inicio === ciclo.inicio && (
                        <FormularioDeAnotacao
                          aoConfirmar={(anotacao) =>
                            enviar(`/api/rotinas/${rotina.id}/ciclos/${ciclo.inicio}/nao-realizada`, { anotacao })
                          }
                          aoCancelar={() => setPedido(null)}
                        />
                      )}
                  </li>
                ))}
              </ul>
            )}

            {rotina.verificacoes.length > 0 && (
              <ul aria-label={`Verificações de ${rotina.descricao}`} className="space-y-1">
                {rotina.verificacoes.map((v) => (
                  <li key={v.ciclo_inicio} className="text-xs text-text-secondary">
                    {diaEMes(v.ciclo_inicio)} a {diaEMes(v.ciclo_fim)}:{" "}
                    {v.resultado === "REALIZADA" ? "Realizada" : "Não realizada"}
                    {v.atrasada ? ", marcada com atraso" : ""}, por {v.marcada_por_nome}.
                    {v.anotacao ? ` ${v.anotacao}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
