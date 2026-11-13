"use client";

/**
 * Página de acompanhamento da Ouvidoria (issue #1623, ADR 0086 decisão 7).
 *
 * Pública, sem login, como o formulário. O anônimo entra com o protocolo e o
 * código que viu na confirmação; quem se identificou, com o protocolo e o
 * telefone ou e-mail que deixou. O servidor devolve só o estado em palavras
 * simples, a data da última movimentação e a resposta institucional, e a
 * mesma recusa para todo dado que não confere.
 */

import { useState } from "react";
import { AlertCircle, Loader2, Search } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

interface Situacao {
  protocolo: string;
  estado: string;
  ultima_movimentacao: string | null;
  resposta: string | null;
}

type Caminho = "anonimo" | "identificado";

// A legenda dos estados (regra T8): cor e significado, lidos juntos.
const ESTADOS: { nome: string; cor: string; significado: string }[] = [
  { nome: "Recebida", cor: "bg-slate-400", significado: "A Ouvidoria recebeu e está lendo o seu relato." },
  { nome: "Em análise", cor: "bg-amber-400", significado: "A área do hospital está apurando o que aconteceu." },
  { nome: "Respondida", cor: "bg-sky-500", significado: "A área respondeu, e a Ouvidoria está conferindo." },
  { nome: "Encerrada", cor: "bg-emerald-500", significado: "O caso terminou, e a resposta está aqui embaixo." },
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

function formatarData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: "America/Sao_Paulo",
  });
}

function corDoEstado(estado: string): string {
  return ESTADOS.find((e) => e.nome === estado)?.cor ?? "bg-slate-400";
}

export default function AcompanharPage() {
  const [caminho, setCaminho] = useState<Caminho | null>(null);
  const [protocolo, setProtocolo] = useState("");
  const [chave, setChave] = useState("");
  const [consultando, setConsultando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [situacao, setSituacao] = useState<Situacao | null>(null);

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
    const corpo =
      caminho === "anonimo"
        ? { protocolo: protocolo.trim(), codigo: chave.trim() }
        : { protocolo: protocolo.trim(), contato: chave.trim() };
    try {
      const res = await fetch("/api/ouvidoria/publico/acompanhamento", {
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
        setErro(detail ?? "Não encontramos uma manifestação com esses dados.");
        return;
      }
      if (!res.ok) {
        setErro("Não foi possível consultar agora. Tente novamente em instantes.");
        return;
      }
      setSituacao((await res.json()) as Situacao);
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
          <h1 className="text-xl font-bold text-slate-900">Acompanhar manifestação</h1>
          <p className="text-sm text-slate-500">
            Veja em que pé está a manifestação que você fez à Ouvidoria.
          </p>
        </div>

        <form
          onSubmit={consultar}
          noValidate
          className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-5"
        >
          <div className="space-y-1.5">
            <p id="rotulo-caminho" className={`etiqueta ${ROTULO}`}>
              Como você fez a manifestação?
            </p>
            <div role="group" aria-labelledby="rotulo-caminho" className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                aria-pressed={caminho === "anonimo"}
                onClick={() => escolher("anonimo")}
                className={opcao(caminho === "anonimo")}
              >
                Fiz anônimo
              </button>
              <button
                type="button"
                aria-pressed={caminho === "identificado"}
                onClick={() => escolher("identificado")}
                className={opcao(caminho === "identificado")}
              >
                Me identifiquei
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="protocolo" className={ROTULO}>
              Protocolo
            </label>
            <input
              id="protocolo"
              type="text"
              value={protocolo}
              onChange={(e) => setProtocolo(e.target.value)}
              maxLength={20}
              inputMode="numeric"
              autoComplete="off"
              placeholder="2026-0042"
              className={CAMPO}
            />
          </div>

          {caminho === "anonimo" && (
            <div className="space-y-1.5">
              <label htmlFor="chave" className={ROTULO}>
                Código de acompanhamento
              </label>
              <input
                id="chave"
                type="text"
                value={chave}
                onChange={(e) => setChave(e.target.value)}
                maxLength={40}
                autoComplete="off"
                autoCapitalize="characters"
                className={`${CAMPO} font-mono`}
              />
              <p className="text-xs text-slate-400">
                O código apareceu junto com o protocolo, na tela de confirmação.
              </p>
            </div>
          )}

          {caminho === "identificado" && (
            <div className="space-y-1.5">
              <label htmlFor="chave" className={ROTULO}>
                Telefone ou e-mail
              </label>
              <input
                id="chave"
                type="text"
                value={chave}
                onChange={(e) => setChave(e.target.value)}
                maxLength={200}
                autoComplete="off"
                className={CAMPO}
              />
              <p className="text-xs text-slate-400">O mesmo que você deixou na manifestação.</p>
            </div>
          )}

          {erro && (
            <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
              <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
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
          <section className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-4">
            <div className="space-y-1">
              <p className="text-sm text-slate-500">Protocolo {situacao.protocolo}</p>
              <p role="status" className="flex items-center gap-2 text-lg font-bold text-slate-900">
                <span aria-hidden="true" className={`h-3 w-3 rounded-full ${corDoEstado(situacao.estado)}`} />
                {situacao.estado}
              </p>
              {situacao.ultima_movimentacao && (
                <p className="text-sm text-slate-500">
                  Última movimentação em {formatarData(situacao.ultima_movimentacao)}.
                </p>
              )}
            </div>
            {situacao.resposta ? (
              <div className="space-y-1">
                <p className={`etiqueta ${ROTULO}`}>Resposta do hospital</p>
                <p className="text-base text-slate-800 whitespace-pre-line">{situacao.resposta}</p>
              </div>
            ) : (
              <p className="text-sm text-slate-500">A resposta aparece aqui quando o caso for encerrado.</p>
            )}
          </section>
        )}

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
      </div>
    </main>
  );
}
