"use client";

/**
 * As perguntas de esclarecimento do agente do Núcleo (issue #1991).
 *
 * Aparecem na confirmação do envio, depois do registro, e na página de
 * acompanhamento. Quem notificou responde em poucas palavras, ou deixa para
 * depois. A chave é a mesma do acompanhamento: o protocolo e o código, ou o
 * e-mail ou telefone que a pessoa deixou.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, Send } from "lucide-react";

export interface ChaveDoAcompanhamento {
  protocolo: string;
  codigo?: string;
  contato?: string;
}

// Até o agente ler a notificação: uma consulta a cada 5 segundos, por um minuto.
const INTERVALO_MS = 5000;
const CONSULTAS = 12;
const LIMITE_DA_RESPOSTA = 500;

const CAMPO =
  "w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";

async function postar(url: string, corpo: object): Promise<Response> {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
}

function listaDePerguntas(corpo: unknown): string[] {
  const lista = (corpo as { perguntas?: unknown } | null)?.perguntas;
  return Array.isArray(lista) ? lista.filter((p): p is string => typeof p === "string") : [];
}

/** As perguntas ainda sem resposta. Com `esperar`, consulta de novo enquanto
 * o servidor diz que o agente ainda não leu a notificação. Falha fica calada:
 * as perguntas nunca seguram nada. */
export function usePerguntasDeEsclarecimento(chave: ChaveDoAcompanhamento | null, esperar = false): string[] {
  const [perguntas, setPerguntas] = useState<string[]>([]);
  const protocolo = chave?.protocolo;
  const codigo = chave?.codigo;
  const contato = chave?.contato;

  useEffect(() => {
    if (!protocolo || (!codigo && !contato)) return;
    let vivo = true;
    let espera: ReturnType<typeof setTimeout> | undefined;
    const corpo = codigo ? { protocolo, codigo } : { protocolo, contato };

    async function consultar(restantes: number) {
      try {
        const res = await postar("/api/nsp/publico/perguntas", corpo);
        if (!vivo || !res.ok) return;
        const dados = await res.json();
        if (!vivo) return;
        const lista = listaDePerguntas(dados);
        setPerguntas(lista);
        if (esperar && lista.length === 0 && dados?.aguardando === true && restantes > 1) {
          espera = setTimeout(() => consultar(restantes - 1), INTERVALO_MS);
        }
      } catch {
        // Sem conexão: a pessoa ainda pode responder no acompanhamento.
      }
    }

    consultar(CONSULTAS);
    return () => {
      vivo = false;
      if (espera) clearTimeout(espera);
    };
  }, [protocolo, codigo, contato, esperar]);

  return perguntas;
}

interface Props {
  chave: ChaveDoAcompanhamento;
  perguntas: string[];
  /** Na confirmação: o link para responder na página de acompanhamento. */
  responderDepois?: boolean;
  /** No acompanhamento: o bloco vem num cartão, como o estado. */
  emCartao?: boolean;
}

const BLOCO = "space-y-3 rounded-xl border border-border bg-slate-50 px-4 py-4 text-left";
const CARTAO = "space-y-3 bg-white rounded-2xl border border-border shadow-premium px-5 py-6";

/** Sem pergunta em aberto, não mostra nada. */
export function PerguntasDeEsclarecimento({ chave, perguntas, responderDepois = false, emCartao = false }: Props) {
  const [abertas, setAbertas] = useState<string[]>(perguntas);
  const [textos, setTextos] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [respondeu, setRespondeu] = useState(false);

  useEffect(() => setAbertas(perguntas), [perguntas]);

  const preenchidas = abertas
    .map((pergunta) => ({ pergunta, resposta: (textos[pergunta] ?? "").trim() }))
    .filter(({ resposta }) => resposta !== "");

  if (abertas.length === 0 && !respondeu) return null;

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (preenchidas.length === 0 || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const corpo = chave.codigo
        ? { protocolo: chave.protocolo, codigo: chave.codigo }
        : { protocolo: chave.protocolo, contato: chave.contato };
      const res = await postar("/api/nsp/publico/respostas", { ...corpo, respostas: preenchidas });
      if (res.status === 429) {
        setErro("Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.");
        return;
      }
      if (!res.ok) {
        const dados = await res.json().catch(() => null);
        setErro(typeof dados?.detail === "string" ? dados.detail : "Não foi possível enviar agora. Tente de novo.");
        return;
      }
      setAbertas(listaDePerguntas(await res.json()));
      setTextos({});
      setRespondeu(true);
    } catch {
      setErro("Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby="nsp-perguntas-titulo" className={emCartao ? CARTAO : BLOCO}>
      <h3 id="nsp-perguntas-titulo" className="text-base font-bold text-slate-900">
        Perguntas do Núcleo
      </h3>
      {respondeu && (
        <p role="status" className="flex items-center gap-1.5 text-sm font-semibold text-emerald-700">
          <CheckCircle2 className="w-4 h-4" aria-hidden />
          Obrigado. A resposta chegou ao Núcleo.
        </p>
      )}
      {abertas.length > 0 && (
        <form onSubmit={enviar} noValidate className="space-y-3">
          <p className="text-sm text-slate-500">
            A sua notificação já está registrada. Se puder, responda em poucas palavras.
          </p>
          {abertas.map((pergunta, indice) => (
            <div key={pergunta} className="space-y-1.5">
              <label htmlFor={`nsp-pergunta-${indice}`} className="block text-sm font-semibold text-slate-700">
                {pergunta}
              </label>
              <input
                id={`nsp-pergunta-${indice}`}
                maxLength={LIMITE_DA_RESPOSTA}
                value={textos[pergunta] ?? ""}
                onChange={(e) => setTextos((atuais) => ({ ...atuais, [pergunta]: e.target.value }))}
                className={CAMPO}
              />
            </div>
          ))}
          {erro && (
            <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-lg px-3 py-2">
              {erro}
            </p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="submit"
              disabled={preenchidas.length === 0 || enviando}
              className="flex flex-1 min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Enviar respostas
            </button>
            {responderDepois && (
              <Link
                href="/notificar/acompanhar"
                className="flex flex-1 min-h-[44px] items-center justify-center rounded-xl border border-border bg-white px-4 py-3 text-base font-semibold text-slate-600 hover:border-primary/40"
              >
                Responder depois
              </Link>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
