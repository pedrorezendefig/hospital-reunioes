"use client";

/**
 * A Conversa da Demanda (issue #1537, PRD #1529, ADR 0083, decisão 8).
 *
 * A troca de mensagens entre o diretor e os Desenvolvedores dentro de uma
 * Demanda, numa área própria, separada da conversa com a IA. A menção é por
 * nome, no formato dos comentários de Pendência: "@" abre a lista de quem vê
 * a Demanda, que o servidor manda, e o clique escreve "@Nome Completo ". Quem
 * é avisado no sino é o servidor que decide.
 */

import { useEffect, useRef, useState } from "react";
import { Loader2, Send } from "lucide-react";

import { LIMITE_DA_MENSAGEM } from "./assistente";
import { BASE_TECNOLOGIA, FALHA_DE_CONEXAO, motivoDaRecusa } from "./demandas";

type Mensagem = { id: string; autor: string | null; texto: string; criado_em: string | null; minha: boolean };
type Mencionavel = { id: string; nome: string };

const CONVERSA_FALHOU = "Não foi possível carregar a Conversa da Demanda. Tente recarregar a página.";

export function urlDaConversaDaDemanda(demandaId: string): string {
  return `${BASE_TECNOLOGIA}/chat/${encodeURIComponent(demandaId)}/conversa`;
}

function mensagemValida(item: unknown): item is Mensagem {
  if (typeof item !== "object" || item === null) return false;
  const m = item as Record<string, unknown>;
  return typeof m.id === "string" && typeof m.texto === "string";
}

function quando(criadoEm: string | null): string {
  if (!criadoEm) return "";
  const data = new Date(criadoEm);
  if (Number.isNaN(data.getTime())) return "";
  return data.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** O trecho depois do último "@" antes do cursor, se ele ainda parece um nome. */
function buscaDaMencao(texto: string, cursor: number): string | null {
  const antes = texto.slice(0, cursor);
  const arroba = antes.lastIndexOf("@");
  if (arroba < 0) return null;
  const depois = antes.slice(arroba + 1);
  return depois.split(" ").length <= 3 ? depois.toLowerCase() : null;
}

export function ConversaDaDemanda({ demandaId, token }: { demandaId: string; token: string | null }) {
  const [mensagens, setMensagens] = useState<Mensagem[] | null>(null);
  const [mencionaveis, setMencionaveis] = useState<Mencionavel[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [busca, setBusca] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const caixa = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!token) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(urlDaConversaDaDemanda(demandaId), {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!viva) return;
        if (!resposta.ok) {
          setErro(CONVERSA_FALHOU);
          return;
        }
        const corpo = (await resposta.json()) as { mensagens?: unknown; mencionaveis?: unknown };
        if (!viva) return;
        setMensagens(Array.isArray(corpo.mensagens) ? corpo.mensagens.filter(mensagemValida) : []);
        setMencionaveis(Array.isArray(corpo.mencionaveis) ? (corpo.mencionaveis as Mencionavel[]) : []);
      } catch (e) {
        console.error("[admin/tecnologia] falha ao abrir a Conversa da Demanda", e);
        if (viva) setErro(FALHA_DE_CONEXAO);
      }
    })();
    return () => {
      viva = false;
    };
  }, [demandaId, token]);

  function aoDigitar(valor: string, cursor: number) {
    setTexto(valor);
    setBusca(buscaDaMencao(valor, cursor));
  }

  function mencionar(nome: string) {
    const cursor = caixa.current?.selectionStart ?? texto.length;
    const antes = texto.slice(0, cursor);
    const arroba = antes.lastIndexOf("@");
    setTexto(`${texto.slice(0, arroba)}@${nome} ${texto.slice(cursor)}`);
    setBusca(null);
    caixa.current?.focus();
  }

  async function enviar() {
    const limpo = texto.trim();
    if (!limpo || !token || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDaConversaDaDemanda(demandaId), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ texto: limpo }),
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      const nova: unknown = await resposta.json();
      if (mensagemValida(nova)) setMensagens((atuais) => [...(atuais ?? []), nova]);
      setTexto("");
      setBusca(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao enviar a mensagem", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setEnviando(false);
    }
  }

  const sugestoes = busca === null ? [] : mencionaveis.filter((p) => p.nome.toLowerCase().includes(busca));

  return (
    <section
      aria-label="Conversa da Demanda"
      className="w-full bg-white rounded-2xl border border-border shadow-premium p-5 space-y-4"
    >
      <div>
        <h2 className="text-sm font-bold text-slate-900">Conversa da Demanda</h2>
        <p className="normal-case text-xs text-text-secondary">
          Para falar com quem cuida deste pedido. A IA não lê esta conversa, e nada daqui sai do aplicativo.
        </p>
      </div>

      {mensagens === null && !erro && (
        <p role="status" className="flex items-center gap-2 text-xs text-text-secondary">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Carregando a conversa...
        </p>
      )}
      {mensagens !== null && mensagens.length === 0 && (
        <p className="normal-case text-sm text-text-secondary">Nenhuma mensagem ainda.</p>
      )}
      {mensagens !== null && mensagens.length > 0 && (
        <ul className="space-y-3">
          {mensagens.map((mensagem) => (
            <li key={mensagem.id} className={`flex ${mensagem.minha ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  mensagem.minha ? "bg-primary/5 border border-primary/20" : "bg-slate-50 border border-slate-200"
                }`}
              >
                <p className="flex flex-wrap items-baseline gap-2 text-xs text-text-secondary">
                  <span className="normal-case font-semibold text-slate-800">{mensagem.autor}</span>
                  <span className="normal-case">{quando(mensagem.criado_em)}</span>
                </p>
                <p className="normal-case whitespace-pre-wrap text-slate-800">{mensagem.texto}</p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {erro && (
        <p role="alert" className="normal-case px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          {erro}
        </p>
      )}

      <div className="relative">
        <textarea
          ref={caixa}
          aria-label="Mensagem para a Conversa"
          rows={2}
          maxLength={LIMITE_DA_MENSAGEM}
          placeholder="Escreva uma mensagem. Use @ para chamar alguém pelo nome."
          value={texto}
          onChange={(e) => aoDigitar(e.target.value, e.target.selectionStart ?? e.target.value.length)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setBusca(null);
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              enviar();
            }
          }}
          className="w-full px-3 py-2 pr-12 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white resize-y"
        />
        <button
          type="button"
          aria-label="Enviar na Conversa"
          onClick={enviar}
          disabled={!texto.trim() || enviando}
          className="absolute right-2 bottom-3 w-8 h-8 rounded-lg bg-primary text-white flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {enviando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
        </button>
        {sugestoes.length > 0 && (
          <ul
            role="listbox"
            aria-label="Quem vê este pedido"
            className="absolute bottom-full left-0 mb-2 w-full max-h-48 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-premium z-10"
          >
            {sugestoes.map((pessoa) => (
              <li
                key={pessoa.id}
                role="option"
                aria-selected={false}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => mencionar(pessoa.nome)}
                className="normal-case px-4 py-2 text-sm text-slate-800 cursor-pointer hover:bg-slate-50"
              >
                {pessoa.nome}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
