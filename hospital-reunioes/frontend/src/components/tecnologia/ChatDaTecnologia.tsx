"use client";

/**
 * O chat da aba Tecnologia, com o Roteiro do bug (issue #1381, PRD #1380, ADR 0077).
 *
 * A aba abre aqui: "bug ou melhoria?", dois botões e um campo livre. A
 * conversa é do SERVIDOR, guardada na Demanda que nasce no primeiro turno; a
 * tela manda cada fala e mostra a conversa que volta. Quando o turno falha, a
 * conversa da tela fica como estava, e o texto digitado também.
 *
 * No bug, o resumo troca a caixa de mensagem por "Criar o card" e "Não
 * bateu". Na melhoria, o caminho desta fatia é o Planejamento da Demanda de
 * antes, numa tela própria.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, CheckCircle2, ImagePlus, ListChecks, Loader2, Mic, Send, Square } from "lucide-react";

import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";

import {
  AVISO_DE_IA,
  avisoDaImagem,
  corpoValidado,
  descreverAImagem,
  IMAGENS_ACEITAS,
  LIMITE_DA_MENSAGEM,
  mensagemComOrigem,
  PREFIXO_DE_PRINT,
  PRINT_SEM_LEITURA,
} from "./assistente";
import {
  ConversaDoChat,
  conversaValida,
  FalaDoChat,
  frasesDosPrints,
  ResumoDoBug,
  URL_DO_CHAT_DA_ABA,
  urlDaConversa,
  urlDoCriarOCard,
  urlDoNaoBateu,
} from "./chat";
import { FALHA_DE_CONEXAO, motivoDaRecusa } from "./demandas";
import { rotaDoPlanejamento } from "./planejamento";

// A mesma pergunta que o backend guarda como primeira fala da conversa.
export const ABERTURA = "Isso é um bug, algo que não funciona como deveria, ou uma melhoria?";
export const CRIAR_O_CARD = "Criar o card";
export const NAO_BATEU = "Não bateu";
export const TITULO_DO_CHAT = "Assistente de Tecnologia";
const TITULO_DO_RESUMO = "Resumo do bug";
const O_QUE_O_CARD_FAZ = "Criar o card manda o bug para o desenvolvimento da Vitta, que começa a trabalhar nele.";
const ENVIADO =
  "A Vitta recebeu o seu relato e o bug já está na fila do desenvolvimento. Os prints ficaram guardados no aplicativo.";
const MELHORIA =
  "Anotei a melhoria. As perguntas sobre o pedido continuam no Planejamento da Demanda, numa tela própria.";
const NAO_SEM_TEXTO = "Diga o que não bateu no resumo.";
const CORPO_ILEGIVEL = "O servidor respondeu algo que a tela não conseguiu ler. Recarregue a página.";

const ABERTURA_NA_TELA: FalaDoChat = {
  autor: "ia",
  texto: ABERTURA,
  fonte: null,
  opcoes: ["Bug", "Melhoria"],
  nao_bateu: false,
};

const ROTULOS_DO_RESUMO: [keyof ResumoDoBug, string][] = [
  ["onde", "Onde"],
  ["o_que_aconteceu", "O que aconteceu"],
  ["o_que_esperava", "O que esperava"],
  ["como_repetir", "Como repetir"],
];

function Fala({ fala }: { fala: FalaDoChat }) {
  if (fala.autor === "diretor") {
    return (
      <p className="ml-auto max-w-[85%] px-3 py-2 rounded-2xl bg-primary text-white text-sm whitespace-pre-line">
        {fala.nao_bateu && <span className="font-semibold">O que não bateu no resumo: </span>}
        {fala.texto}
      </p>
    );
  }
  return (
    <div className="mr-auto max-w-[85%] space-y-1">
      <p className="px-3 py-2 rounded-2xl bg-slate-100 text-slate-800 text-sm whitespace-pre-line">{fala.texto}</p>
      {fala.fonte && <p className="px-3 text-xs text-text-secondary">De onde veio: material da Vitta sobre {fala.fonte}</p>}
    </div>
  );
}

type PropsDoResumo = {
  resumo: ResumoDoBug;
  anexos: number;
  pensando: boolean;
  onCriar: () => void;
  /** Manda o que não bateu; devolve se o servidor aceitou. */
  onNaoBateu: (texto: string) => Promise<boolean>;
  onRecusaNaTela: (motivo: string) => void;
};

function ResumoNaTela({ resumo, anexos, pensando, onCriar, onNaoBateu, onRecusaNaTela }: PropsDoResumo) {
  const [dizendo, setDizendo] = useState(false);
  const [texto, setTexto] = useState("");

  async function enviar() {
    const oQue = texto.trim();
    if (!oQue) {
      onRecusaNaTela(NAO_SEM_TEXTO);
      return;
    }
    if (await onNaoBateu(oQue)) setTexto("");
  }

  return (
    <section
      aria-label={TITULO_DO_RESUMO}
      className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-6 space-y-5"
    >
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <ListChecks className="w-4 h-4 text-primary" />
        </span>
        <h2 className="text-base font-bold text-slate-900">{TITULO_DO_RESUMO}</h2>
      </div>
      <p className="text-sm font-semibold text-text-primary">{resumo.titulo}</p>

      <dl className="space-y-3 text-sm">
        {ROTULOS_DO_RESUMO.map(([campo, rotulo]) => (
          <div key={campo}>
            <dt className="font-semibold text-text-primary">{rotulo}</dt>
            <dd className="text-text-secondary whitespace-pre-line">{resumo[campo] as string}</dd>
          </div>
        ))}
        <div>
          <dt className="font-semibold text-text-primary">Prints</dt>
          <dd className="text-text-secondary">{frasesDosPrints(anexos)}</dd>
        </div>
      </dl>

      <div className="space-y-2">
        <h3 className="text-sm font-bold text-text-primary">Como saber que foi resolvido</h3>
        <ul className="list-disc pl-5 space-y-1 text-sm text-text-primary">
          {resumo.criterios.map((criterio, i) => (
            <li key={i}>{criterio}</li>
          ))}
        </ul>
      </div>

      <div className="space-y-2 border-t border-slate-100 pt-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCriar}
            disabled={pensando}
            className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
          >
            {CRIAR_O_CARD}
          </button>
          <button
            type="button"
            onClick={() => setDizendo(true)}
            disabled={pensando}
            className="px-4 py-2 rounded-xl border border-border text-sm font-semibold text-text-primary hover:border-primary disabled:opacity-50"
          >
            {NAO_BATEU}
          </button>
        </div>
        <p className="text-xs text-text-secondary">{O_QUE_O_CARD_FAZ}</p>
      </div>

      {dizendo && (
        <div className="space-y-2">
          <label htmlFor="o-que-nao-bateu-no-chat" className="text-sm font-semibold text-text-primary">
            O que não bateu
          </label>
          <textarea
            id="o-que-nao-bateu-no-chat"
            rows={3}
            maxLength={LIMITE_DA_MENSAGEM}
            placeholder="Diga o que está errado ou faltando. A conversa continua a partir daí."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white resize-y"
          />
          <button
            type="button"
            onClick={enviar}
            disabled={pensando}
            className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
          >
            Enviar o que não bateu
          </button>
        </div>
      )}
    </section>
  );
}

function Fechamento({ texto, children }: { texto: string; children?: React.ReactNode }) {
  return (
    <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-6 space-y-4">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <CheckCircle2 className="w-4 h-4 text-primary" />
        </span>
        <p className="text-sm text-text-primary">{texto}</p>
      </div>
      {children}
    </section>
  );
}

export function ChatDaTecnologia({ token }: { token: string | null }) {
  const [conversa, setConversa] = useState<ConversaDoChat | null>(null);
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const entradaDeImagem = useRef<HTMLInputElement>(null);
  const fimDaLista = useRef<HTMLDivElement>(null);

  // O texto falado entra DEPOIS do que já estava escrito, nunca no lugar dele.
  const { gravando, transcrevendo, iniciarGravacao, pararGravacao } = useGravacaoVoz({
    getToken: () => token,
    onTexto: (transcrito) => setTexto((atual) => (atual.trim() ? `${atual.trimEnd()} ${transcrito}` : transcrito)),
  });
  const ocupado = pensando || gravando || transcrevendo;

  /** Um POST que devolve a conversa inteira; nula quando não valeu. */
  const enviar = useCallback(
    async (url: string, corpo: unknown): Promise<ConversaDoChat | null> => {
      if (!token) return null;
      setPensando(true);
      setErro(null);
      try {
        const resposta = await fetch(url, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
        });
        if (!resposta.ok) {
          setErro(await motivoDaRecusa(resposta));
          return null;
        }
        const nova = await corpoValidado(resposta, conversaValida);
        if (nova === null) {
          setErro(CORPO_ILEGIVEL);
          return null;
        }
        setConversa(nova);
        if (nova.aviso_dos_anexos) setErro(nova.aviso_dos_anexos);
        return nova;
      } catch (e) {
        console.error("[admin/tecnologia] falha no chat", e);
        setErro(FALHA_DE_CONEXAO);
        return null;
      } finally {
        setPensando(false);
      }
    },
    [token],
  );

  /** A fala do diretor: o primeiro turno faz a Demanda nascer, os outros seguem nela. */
  const falar = useCallback(
    async (fala: string, prints: string[] = []): Promise<boolean> => {
      const url = conversa ? urlDaConversa(conversa.demanda_id) : URL_DO_CHAT_DA_ABA;
      return (await enviar(url, { texto: fala, prints })) !== null;
    },
    [conversa, enviar],
  );

  useEffect(() => {
    fimDaLista.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [conversa, pensando]);

  async function enviarOTexto() {
    const fala = texto.trim();
    if (!fala || ocupado) return;
    // O texto só sai da caixa quando o turno valeu: se falhar, ele continua lá.
    if (await falar(fala)) setTexto("");
  }

  async function escolher(opcao: string) {
    if (ocupado) return;
    if (conversa === null) {
      await enviar(URL_DO_CHAT_DA_ABA, { escolha: opcao === "Bug" ? "bug" : "melhoria" });
      return;
    }
    await falar(opcao);
  }

  /** O print vira a descrição lida pelo servidor, e a fala leva o identificador que o faz Anexo. */
  async function anexarOPrint(arquivo: File) {
    const aviso = avisoDaImagem(arquivo);
    if (aviso) {
      setErro(aviso);
      return;
    }
    setPensando(true);
    const leitura = await descreverAImagem(arquivo, token);
    setPensando(false);
    if ("aviso" in leitura) {
      setErro(leitura.aviso);
      return;
    }
    const descricao = leitura.corpo.texto.trim();
    if (!descricao) {
      setErro(PRINT_SEM_LEITURA);
      return;
    }
    const printId = leitura.corpo.print_id;
    await falar(mensagemComOrigem(PREFIXO_DE_PRINT, descricao), printId ? [printId] : []);
  }

  async function naoBateu(oQue: string): Promise<boolean> {
    if (!conversa) return false;
    const voltou = await enviar(urlDoNaoBateu(conversa.demanda_id), { texto: oQue });
    if (voltou === null) return false;
    // A conversa voltou a em andamento com a fala no fim: a IA retoma dali.
    await enviar(urlDaConversa(voltou.demanda_id), {});
    return true;
  }

  function recomecar() {
    setConversa(null);
    setErro(null);
    setTexto("");
  }

  const aviso = erro && (
    <p role="alert" className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm whitespace-pre-line">
      {erro}
    </p>
  );

  if (conversa?.planejamento) {
    return (
      <div className="space-y-4">
        {aviso}
        <Fechamento texto={MELHORIA}>
          <Link
            href={rotaDoPlanejamento(conversa.demanda_id)}
            className="inline-flex items-center px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold"
          >
            Continuar no planejamento
          </Link>
        </Fechamento>
      </div>
    );
  }

  if (conversa?.estado === "enviado") {
    return (
      <Fechamento texto={ENVIADO}>
        <button
          type="button"
          onClick={recomecar}
          className="px-4 py-2 rounded-xl border border-border text-sm font-semibold text-text-primary hover:border-primary"
        >
          Começar outra conversa
        </button>
      </Fechamento>
    );
  }

  if (conversa?.estado === "resumido" && conversa.resumo) {
    return (
      <div className="space-y-4">
        {aviso}
        <ResumoNaTela
          resumo={conversa.resumo}
          anexos={conversa.anexos}
          pensando={pensando}
          onCriar={() => enviar(urlDoCriarOCard(conversa.demanda_id), {})}
          onNaoBateu={naoBateu}
          onRecusaNaTela={setErro}
        />
      </div>
    );
  }

  const falas = conversa?.mensagens ?? [ABERTURA_NA_TELA];
  const ultima = falas[falas.length - 1];
  const opcoes = ultima?.autor === "ia" ? ultima.opcoes : [];
  // A última fala é do diretor e nada respondeu: o "não bateu" cuja retomada falhou.
  const esperaAIA = conversa !== null && ultima?.autor === "diretor" && !pensando;

  return (
    <div className="space-y-4">
      {aviso}
      <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-[calc(100vh-18rem)] min-h-[420px] overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100">
          <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" />
          </span>
          <h2 className="text-sm font-bold text-slate-900">{TITULO_DO_CHAT}</h2>
        </div>

        <div role="log" className="flex-1 overflow-y-auto px-5 py-4 space-y-3 overscroll-contain">
          {falas.map((fala, i) => (
            <Fala key={i} fala={fala} />
          ))}

          {opcoes.length > 0 && !pensando && (
            <div role="group" aria-label="Opções" className="flex flex-wrap gap-2 max-w-[85%]">
              {opcoes.map((opcao) => (
                <button
                  key={opcao}
                  type="button"
                  onClick={() => escolher(opcao)}
                  className="px-4 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5"
                >
                  {opcao}
                </button>
              ))}
            </div>
          )}

          {pensando && (
            <p role="status" className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Pensando...
            </p>
          )}

          {esperaAIA && (
            <button
              type="button"
              onClick={() => conversa && enviar(urlDaConversa(conversa.demanda_id), {})}
              className="px-3 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5"
            >
              Tentar de novo
            </button>
          )}
          <div ref={fimDaLista} />
        </div>

        <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
          <div className="flex gap-2">
            <textarea
              aria-label="Sua mensagem"
              rows={1}
              maxLength={LIMITE_DA_MENSAGEM}
              placeholder={transcrevendo ? "Transcrevendo a sua fala..." : "Escreva, fale no microfone ou mande um print"}
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
            <input
              ref={entradaDeImagem}
              type="file"
              accept={IMAGENS_ACEITAS.join(",")}
              className="hidden"
              onChange={(e) => {
                const arquivo = e.target.files?.[0];
                e.target.value = "";
                if (arquivo) void anexarOPrint(arquivo);
              }}
            />
            <button
              type="button"
              onClick={() => entradaDeImagem.current?.click()}
              disabled={ocupado}
              aria-label="Mandar um print"
              title="Mandar um print"
              className="px-3 py-2 rounded-xl border border-border text-text-secondary hover:border-primary hover:text-primary disabled:opacity-50 transition-colors"
            >
              <ImagePlus className="w-4 h-4" />
            </button>
            {/* O microfone fica vivo enquanto grava: é o caminho de volta. */}
            <button
              type="button"
              onClick={() => (gravando ? pararGravacao() : iniciarGravacao())}
              disabled={!gravando && ocupado}
              aria-label={gravando ? "Parar de gravar" : "Gravar voz"}
              title={gravando ? "Parar de gravar" : "Gravar voz"}
              className={`px-3 py-2 rounded-xl border text-text-secondary disabled:opacity-50 ${
                gravando ? "border-red-300 bg-red-50 text-red-600" : "border-border hover:border-primary hover:text-primary"
              } transition-colors`}
            >
              {gravando ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
            <button
              type="button"
              onClick={enviarOTexto}
              disabled={ocupado || !texto.trim()}
              aria-label="Enviar mensagem"
              className="px-3 py-2 rounded-xl bg-primary text-white disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="mt-1.5 text-xs text-slate-400">{AVISO_DE_IA}</p>
        </div>
      </section>
    </div>
  );
}
