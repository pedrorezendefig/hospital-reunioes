"use client";

/**
 * Planejar com a IA (issue #1345, PRD #1344, ADR 0075).
 *
 * Molde do Assistente de Tecnologia: a conversa de um lado, o que ela produz
 * do outro. Aqui o que ela produz é o "O que já decidimos", uma frase por
 * resposta que fechou alguma coisa.
 *
 * A diferença de fundo para o Assistente: a conversa é do SERVIDOR, guardada
 * na Demanda (decisão 3). A tela pede o que está guardado ao abrir, começa a
 * conversa quando não há nada, e a cada clique manda só a resposta. Quando o
 * turno falha, a conversa da tela fica como estava, e o texto digitado também.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, Loader2, Send } from "lucide-react";

import { AVISO_DE_IA, corpoValidado, LIMITE_DA_MENSAGEM } from "./assistente";
import { Demanda, FALHA_DE_CONEXAO, motivoDaRecusa } from "./demandas";
import {
  MensagemDoPlanejamento,
  perguntaEmAberto,
  Planejamento,
  planejamentoValido,
  PLANEJAR_COM_A_IA,
  podePlanejar,
  RespostaDoPlanejamento,
  rotaDoPlanejamento,
  urlDoPlanejamento,
} from "./planejamento";

export const TITULO_DAS_DECISOES = "O que já decidimos";
export const NADA_DECIDIDO = "Nada ainda. Cada resposta que fechar uma decisão aparece aqui.";
const NAO_ABRIU = "Não foi possível abrir o planejamento desta Demanda. Recarregue a página.";
const CORPO_ILEGIVEL = "O servidor respondeu algo que a tela não conseguiu ler. Recarregue a página.";
const TERMINOU =
  "O planejamento terminou. A conversa e as decisões ficam guardadas nesta Demanda até ela ser concluída ou cancelada.";

/** O botão do card aberto: só em Novo ou Ajuste, aberta e sem Vínculo. */
export function BotaoDePlanejar({ demanda }: { demanda: Demanda }) {
  if (!podePlanejar(demanda)) return null;
  return (
    <div className="md:col-span-2">
      <Link
        href={rotaDoPlanejamento(demanda.id)}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5 transition-colors"
      >
        <Bot className="w-4 h-4" />
        {PLANEJAR_COM_A_IA}
      </Link>
    </div>
  );
}

type Props = {
  demandaId: string;
  token: string | null;
  /** Avisa a página do título da Demanda, que vem junto do planejamento. */
  onTitulo?: (titulo: string) => void;
};

function Fala({ mensagem }: { mensagem: MensagemDoPlanejamento }) {
  if (mensagem.tipo === "resposta") {
    return (
      <p className="ml-auto max-w-[85%] px-3 py-2 rounded-2xl bg-primary text-white text-sm whitespace-pre-line">
        {mensagem.texto}
      </p>
    );
  }
  return (
    <p className="mr-auto max-w-[85%] px-3 py-2 rounded-2xl bg-slate-100 text-slate-800 text-sm whitespace-pre-line">
      {mensagem.contexto}
    </p>
  );
}

export function PlanejamentoDaDemanda({ demandaId, token, onTitulo }: Props) {
  const [planejamento, setPlanejamento] = useState<Planejamento | null>(null);
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const fimDaLista = useRef<HTMLDivElement>(null);

  const responder = useCallback(
    async (corpo: RespostaDoPlanejamento): Promise<boolean> => {
      if (!token) return false;
      setPensando(true);
      setErro(null);
      try {
        const resposta = await fetch(urlDoPlanejamento(demandaId), {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
        });
        if (!resposta.ok) {
          setErro(await motivoDaRecusa(resposta));
          return false;
        }
        const novo = await corpoValidado(resposta, planejamentoValido);
        if (novo === null) {
          setErro(CORPO_ILEGIVEL);
          return false;
        }
        setPlanejamento(novo);
        return true;
      } catch (e) {
        console.error("[admin/tecnologia] falha no turno do planejamento", e);
        setErro(FALHA_DE_CONEXAO);
        return false;
      } finally {
        setPensando(false);
      }
    },
    [demandaId, token],
  );

  useEffect(() => {
    if (!token) return;
    let vivo = true;
    fetch(urlDoPlanejamento(demandaId), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (resposta) => {
        if (!resposta.ok) {
          if (vivo) setErro(await motivoDaRecusa(resposta));
          return;
        }
        const lido = await corpoValidado(resposta, planejamentoValido);
        if (!vivo) return;
        if (lido === null) {
          setErro(NAO_ABRIU);
          return;
        }
        setPlanejamento(lido);
        // Nada guardado: quem clicou em "Planejar com a IA" quer a primeira pergunta.
        if (lido.estado === null) responder({});
      })
      .catch((e) => {
        console.error("[admin/tecnologia] falha ao abrir o planejamento", e);
        if (vivo) setErro(FALHA_DE_CONEXAO);
      });
    return () => {
      vivo = false;
    };
  }, [demandaId, token, responder]);

  useEffect(() => {
    if (planejamento) onTitulo?.(planejamento.titulo);
  }, [planejamento, onTitulo]);

  useEffect(() => {
    fimDaLista.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [planejamento, pensando]);

  const pergunta = planejamento?.estado === "em_andamento" ? perguntaEmAberto(planejamento) : null;
  const terminou = planejamento?.estado !== null && planejamento?.estado !== undefined && !pergunta;

  async function enviarOTexto() {
    const resposta = texto.trim();
    if (!resposta || pensando) return;
    // O texto só sai da caixa quando o turno valeu: se falhar, ele continua lá.
    if (await responder({ texto: resposta })) setTexto("");
  }

  return (
    <div className="grid lg:grid-cols-[1fr_minmax(320px,380px)] gap-6 items-start">
      {erro && (
        <p
          role="alert"
          className="lg:col-span-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm whitespace-pre-line"
        >
          {erro}
        </p>
      )}

      {/* A conversa, à esquerda. */}
      <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-[calc(100vh-14rem)] min-h-[420px] overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100">
          <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" />
          </span>
          <h2 className="text-sm font-bold text-slate-900">{PLANEJAR_COM_A_IA}</h2>
        </div>

        <div role="log" className="flex-1 overflow-y-auto px-5 py-4 space-y-3 overscroll-contain">
          {planejamento?.mensagens.map((m, i) => <Fala key={i} mensagem={m} />)}

          {pergunta && !pensando && (
            <div role="group" aria-label="Opções" className="flex flex-col gap-2 max-w-[85%]">
              {(pergunta.opcoes ?? []).map((opcao) => {
                const recomendada = opcao.letra === pergunta.recomendada;
                return (
                  <button
                    key={opcao.letra}
                    type="button"
                    onClick={() => responder({ opcao: opcao.letra })}
                    className={`text-left px-3 py-2 rounded-xl border text-sm transition-colors ${
                      recomendada
                        ? "border-primary bg-primary/5 text-slate-900 ring-1 ring-primary"
                        : "border-border text-slate-800 hover:border-primary"
                    }`}
                  >
                    <span className="font-semibold">{opcao.letra}) </span>
                    {opcao.texto}
                    {recomendada && (
                      <span className="ml-2 inline-block px-2 py-0.5 rounded-full bg-primary text-white text-xs font-semibold">
                        Recomendada
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {pensando && (
            <p role="status" className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Pensando...
            </p>
          )}

          {terminou && (
            <p role="status" className="text-xs text-text-secondary">
              {TERMINOU}
            </p>
          )}
          <div ref={fimDaLista} />
        </div>

        {!terminou && (
          <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
            <div className="flex gap-2">
              <textarea
                aria-label="Sua resposta"
                rows={1}
                maxLength={LIMITE_DA_MENSAGEM}
                placeholder="Ou escreva a sua resposta"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    enviarOTexto();
                  }
                }}
                className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white resize-none"
              />
              <button
                type="button"
                onClick={enviarOTexto}
                disabled={pensando || !pergunta || !texto.trim()}
                aria-label="Enviar resposta"
                className="px-3 py-2 rounded-xl bg-primary text-white disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="mt-1.5 text-xs text-slate-400">{AVISO_DE_IA}</p>
          </div>
        )}
      </section>

      {/* O que já decidimos, à direita, crescendo a cada resposta. */}
      <section
        aria-labelledby="titulo-das-decisoes"
        className="rounded-2xl border border-border bg-surface p-4 space-y-3 w-full"
      >
        <h2 id="titulo-das-decisoes" className="text-sm font-bold text-text-primary">
          {TITULO_DAS_DECISOES}
        </h2>
        {planejamento && planejamento.decisoes.length > 0 ? (
          <ol className="list-decimal pl-5 space-y-2 text-sm text-text-primary">
            {planejamento.decisoes.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-text-secondary">{NADA_DECIDIDO}</p>
        )}
      </section>
    </div>
  );
}
