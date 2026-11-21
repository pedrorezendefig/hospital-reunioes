"use client";

/**
 * A página de acompanhamento da notificação de incidente (issue #1987).
 *
 * Pública, sem login, como o formulário. Quem notificou sem se identificar
 * entra com o protocolo e o código que viu na confirmação; quem se identificou,
 * com o protocolo e o e-mail ou telefone que deixou. O servidor devolve só o
 * estado em palavras simples, e a mesma recusa para todo dado que não confere.
 */

import { useState } from "react";
import { AlertCircle, Loader2, Search, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  PerguntasDeEsclarecimento,
  usePerguntasDeEsclarecimento,
  type ChaveDoAcompanhamento,
} from "@/components/seguranca-do-paciente/PerguntasDeEsclarecimento";
import { SEM_PUNICAO } from "@/lib/seguranca-do-paciente/notificacao";

interface Situacao {
  protocolo: string;
  estado: string;
}

/** As perguntas do agente que esperam resposta (issue #1991), com a chave
 * que acabou de conferir. */
function PerguntasEmAberto({ chave }: { chave: ChaveDoAcompanhamento }) {
  const perguntas = usePerguntasDeEsclarecimento(chave);
  return <PerguntasDeEsclarecimento chave={chave} perguntas={perguntas} emCartao />;
}

type Caminho = "anonimo" | "identificado";

// A legenda dos estados: cor e significado, lidos juntos.
const ESTADOS: { nome: string; cor: string; significado: string }[] = [
  { nome: "Recebida", cor: "bg-slate-400", significado: "O Núcleo recebeu e vai ler o seu relato." },
  { nome: "Em análise", cor: "bg-amber-400", significado: "O Núcleo está analisando o que aconteceu." },
  { nome: "Concluída", cor: "bg-emerald-500", significado: "O Núcleo terminou de tratar a notificação." },
];

const CAMPO =
  "w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";
const ROTULO = "block text-sm font-semibold text-slate-700";

function opcao(escolhida: boolean): string {
  return `min-h-[44px] rounded-xl border px-3 py-3 text-base font-semibold transition-colors ${
    escolhida
      ? "border-primary bg-primary/10 text-primary"
      : "border-border bg-white text-slate-600 hover:border-primary/40"
  }`;
}

function corDoEstado(estado: string): string {
  return ESTADOS.find((e) => e.nome === estado)?.cor ?? "bg-slate-400";
}

export default function AcompanharNotificacaoPage() {
  const [caminho, setCaminho] = useState<Caminho | null>(null);
  const [protocolo, setProtocolo] = useState("");
  const [chave, setChave] = useState("");
  const [consultando, setConsultando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [situacao, setSituacao] = useState<Situacao | null>(null);
  const [chaveConferida, setChaveConferida] = useState<ChaveDoAcompanhamento | null>(null);

  const podeConsultar = caminho !== null && protocolo.trim() !== "" && chave.trim() !== "";

  function escolher(novo: Caminho) {
    setCaminho(novo);
    setChave("");
    setErro(null);
  }

  async function consultar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!podeConsultar || consultando) return;
    setConsultando(true);
    setErro(null);
    setSituacao(null);
    setChaveConferida(null);
    const corpo =
      caminho === "anonimo"
        ? { protocolo: protocolo.trim(), codigo: chave.trim() }
        : { protocolo: protocolo.trim(), contato: chave.trim() };
    try {
      const res = await fetch("/api/nsp/publico/acompanhamento", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (res.status === 429) {
        setErro("Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.");
        return;
      }
      if (res.status === 404) {
        const { detail } = (await res.json()) as { detail?: string };
        setErro(detail ?? "Não encontramos uma notificação com esses dados.");
        return;
      }
      if (!res.ok) {
        setErro("Não foi possível consultar agora. Tente novamente em instantes.");
        return;
      }
      setSituacao((await res.json()) as Situacao);
      setChaveConferida(corpo);
    } catch {
      setErro("Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo.");
    } finally {
      setConsultando(false);
    }
  }

  return (
    <main className="min-h-screen bg-bg">
      <div className="max-w-lg mx-auto px-4 py-8 space-y-5">
        <div className="flex items-center justify-center">
          <Logo variant="default" size="sm" />
        </div>
        <div className="text-center space-y-1">
          <h1 className="text-xl font-bold text-slate-900">Acompanhar notificação</h1>
          <p className="text-sm text-slate-500">
            Informe o protocolo e o código, ou o e-mail ou telefone que você deixou.
          </p>
        </div>

        <form
          onSubmit={consultar}
          noValidate
          className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-5"
        >
          <div className="space-y-1.5">
            <p id="rotulo-caminho" className={`etiqueta ${ROTULO}`}>
              Como você notificou?
            </p>
            <div role="group" aria-labelledby="rotulo-caminho" className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                aria-pressed={caminho === "anonimo"}
                onClick={() => escolher("anonimo")}
                className={opcao(caminho === "anonimo")}
              >
                Notifiquei sem me identificar
              </button>
              <button
                type="button"
                aria-pressed={caminho === "identificado"}
                onClick={() => escolher("identificado")}
                className={opcao(caminho === "identificado")}
              >
                Notifiquei com o meu nome
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="protocolo" className={`etiqueta ${ROTULO}`}>
              Protocolo
            </label>
            <input
              id="protocolo"
              type="text"
              value={protocolo}
              onChange={(e) => setProtocolo(e.target.value)}
              maxLength={20}
              autoComplete="off"
              autoCapitalize="characters"
              placeholder="NSP-2026-0042"
              className={CAMPO}
            />
          </div>

          {caminho && (
            <div className="space-y-1.5">
              <label htmlFor="chave" className={`etiqueta ${ROTULO}`}>
                {caminho === "anonimo" ? "Código de acompanhamento" : "E-mail ou telefone"}
              </label>
              <input
                id="chave"
                type="text"
                value={chave}
                onChange={(e) => setChave(e.target.value)}
                maxLength={caminho === "anonimo" ? 40 : 200}
                autoComplete="off"
                className={caminho === "anonimo" ? `${CAMPO} font-mono` : CAMPO}
              />
            </div>
          )}

          {erro && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
              <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" aria-hidden />
              <p className="text-sm text-amber-800">{erro}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={!podeConsultar || consultando}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {consultando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Consultar
          </button>
        </form>

        {situacao && (
          <section className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-1">
            <p className="text-sm text-slate-500">Protocolo {situacao.protocolo}</p>
            <p className="flex items-center gap-2 text-lg font-bold text-slate-900">
              <span aria-hidden="true" className={`h-3 w-3 rounded-full ${corDoEstado(situacao.estado)}`} />
              <span role="status">{situacao.estado}</span>
            </p>
          </section>
        )}

        {chaveConferida && <PerguntasEmAberto chave={chaveConferida} />}

        <section aria-labelledby="legenda" className="space-y-2">
          <h2 id="legenda" className="text-sm font-semibold text-slate-700">
            O que cada estado quer dizer
          </h2>
          <ul className="space-y-1.5">
            {ESTADOS.map(({ nome, cor, significado }) => (
              <li key={nome} className="flex items-start gap-2 text-sm text-slate-600">
                <span aria-hidden="true" className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${cor}`} />
                <span>
                  <span className="font-semibold text-slate-800">{nome}</span>: {significado}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-emerald-700">
          <ShieldCheck className="w-4 h-4" aria-hidden />
          {SEM_PUNICAO}
        </p>
      </div>
    </main>
  );
}
