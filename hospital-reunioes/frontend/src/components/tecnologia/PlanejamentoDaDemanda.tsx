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
 *
 * O fim (issue #1347): "Fechar e resumir", fixo no topo da conversa, pede o
 * resumo a qualquer altura. Com o planejamento resumido, a tela troca a
 * conversa pelo resumo, com o "sim" e o "não". O "não" exige dizer o que não
 * bateu e devolve a conversa à IA. O "sim" (issue #1349) manda o PRD do
 * diretor para os desenvolvedores, e a tela passa a dizer que foi.
 *
 * A voz (issue #1348) entra pelo microfone do Assistente: o mesmo hook, a
 * mesma rota de transcrição. O texto transcrito cai no campo livre, editável,
 * e só vai para a IA quando o diretor envia.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, CheckCircle2, ListChecks, Loader2, Mic, Send, Square } from "lucide-react";

import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";

import { AVISO_DE_IA, corpoValidado, LIMITE_DA_MENSAGEM } from "./assistente";
import { FALHA_DE_CONEXAO, motivoDaRecusa, ROTA_TECNOLOGIA } from "./demandas";
import {
  esperaAIA,
  MensagemDoPlanejamento,
  perguntaEmAberto,
  Planejamento,
  planejamentoValido,
  PLANEJAR_COM_A_IA,
  RespostaDoPlanejamento,
  ResumoDoPlanejamento,
  urlDoEnvio,
  urlDoNao,
  urlDoPlanejamento,
  urlDoResumo,
} from "./planejamento";

export const TITULO_DAS_DECISOES = "O que já decidimos";
export const NADA_DECIDIDO = "Nada ainda. Cada resposta que fechar uma decisão aparece aqui.";
export const FECHAR_E_RESUMIR = "Fechar e resumir";
export const TITULO_DO_RESUMO = "Resumo do planejamento";
export const TITULO_DAS_DECISOES_DO_RESUMO = "Decisões";
export const TITULO_DO_EM_ABERTO = "Ficou em aberto";
export const SIM_MANDAR = "Sim, mandar para os desenvolvedores";
export const O_QUE_NAO_BATEU = "O que não bateu";
export const TITULO_DO_ENVIADO = "Mandado para os desenvolvedores";
export const VOLTAR_PARA_A_TECNOLOGIA = "Voltar para a Tecnologia";
const NAO_SEM_TEXTO = "Diga o que não bateu no resumo.";
const O_QUE_O_SIM_FAZ = "O sim manda as suas decisões e o que ficou em aberto para a Vitta.";
const ENVIADO = "A Vitta recebeu as suas decisões e o que ficou em aberto. A Demanda agora está Em análise, e o card mostra O que muda com o que você decidiu.";
const NENHUMA_DECISAO = "Nenhuma pergunta respondida fechou uma decisão.";
const NADA_EM_ABERTO = "Nada ficou em aberto.";
const NAO_ABRIU = "Não foi possível abrir o planejamento desta Demanda. Recarregue a página.";
const CORPO_ILEGIVEL = "O servidor respondeu algo que a tela não conseguiu ler. Recarregue a página.";
const TERMINOU = "A IA já tem o que precisa. Clique em Fechar e resumir para ver as decisões.";

type Props = {
  demandaId: string;
  token: string | null;
  /** Avisa a página do título da Demanda, que vem junto do planejamento. */
  onTitulo?: (titulo: string) => void;
};

function Fala({ mensagem }: { mensagem: MensagemDoPlanejamento }) {
  if (mensagem.tipo === "resposta" || mensagem.tipo === "nao_bateu") {
    return (
      <p className="ml-auto max-w-[85%] px-3 py-2 rounded-2xl bg-primary text-white text-sm whitespace-pre-line">
        {mensagem.tipo === "nao_bateu" && <span className="font-semibold">O que não bateu no resumo: </span>}
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

type PropsDoResumo = {
  resumo: ResumoDoPlanejamento;
  pensando: boolean;
  /** Manda o resumo para os desenvolvedores (o "sim"). */
  onSim: () => void;
  /** Manda o que não bateu; devolve se o servidor aceitou. */
  onNao: (texto: string) => Promise<boolean>;
  onRecusaNaTela: (motivo: string) => void;
};

/** O resumo, na tela própria: as decisões, o que ficou em aberto, o sim e o não. */
function ResumoDaConversa({ resumo, pensando, onSim, onNao, onRecusaNaTela }: PropsDoResumo) {
  const [dizendoNao, setDizendoNao] = useState(false);
  const [texto, setTexto] = useState("");

  async function enviarONao() {
    const oQue = texto.trim();
    if (!oQue) {
      onRecusaNaTela(NAO_SEM_TEXTO);
      return;
    }
    if (await onNao(oQue)) setTexto("");
  }

  return (
    <section className="w-full max-w-3xl bg-white rounded-2xl border border-primary/30 shadow-premium p-6 space-y-6">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <ListChecks className="w-4 h-4 text-primary" />
        </span>
        <h2 className="text-base font-bold text-slate-900">{TITULO_DO_RESUMO}</h2>
      </div>
      <p className="text-sm text-text-secondary">Confira se o resumo diz o que você decidiu.</p>

      <section aria-labelledby="titulo-decisoes-do-resumo" className="space-y-3">
        <h3 id="titulo-decisoes-do-resumo" className="text-sm font-bold text-text-primary">
          {TITULO_DAS_DECISOES_DO_RESUMO}
        </h3>
        {resumo.decisoes.length > 0 ? (
          <ol className="space-y-3">
            {resumo.decisoes.map((d, i) => (
              <li key={i} className="rounded-xl border border-border p-3 space-y-1 text-sm">
                <p className="text-text-secondary">{d.pergunta}</p>
                <p className="text-text-primary">
                  <span className="font-semibold">Escolha: </span>
                  <span>{d.escolha}</span>
                </p>
                <p className="text-text-primary">
                  <span className="font-semibold">Por quê: </span>
                  <span>{d.porque}</span>
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-text-secondary">{NENHUMA_DECISAO}</p>
        )}
      </section>

      <section aria-labelledby="titulo-em-aberto" className="space-y-3">
        <h3 id="titulo-em-aberto" className="text-sm font-bold text-text-primary">
          {TITULO_DO_EM_ABERTO}
        </h3>
        {resumo.em_aberto.length > 0 ? (
          <ul className="list-disc pl-5 space-y-1 text-sm text-text-primary">
            {resumo.em_aberto.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-secondary">{NADA_EM_ABERTO}</p>
        )}
      </section>

      <div className="space-y-2 border-t border-slate-100 pt-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onSim}
            disabled={pensando}
            className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
          >
            {SIM_MANDAR}
          </button>
          <button
            type="button"
            onClick={() => setDizendoNao(true)}
            disabled={pensando}
            className="px-4 py-2 rounded-xl border border-border text-sm font-semibold text-text-primary hover:border-primary disabled:opacity-50"
          >
            Não
          </button>
        </div>
        <p className="text-xs text-text-secondary">{O_QUE_O_SIM_FAZ}</p>
      </div>

      {dizendoNao && (
        <div className="space-y-2">
          <label htmlFor="o-que-nao-bateu" className="text-sm font-semibold text-text-primary">
            {O_QUE_NAO_BATEU}
          </label>
          <textarea
            id="o-que-nao-bateu"
            rows={3}
            maxLength={LIMITE_DA_MENSAGEM}
            placeholder="Diga o que está errado ou faltando. A IA volta à conversa a partir daí."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white resize-y"
          />
          <button
            type="button"
            onClick={enviarONao}
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

/** Depois do "sim": o plano já foi, e não há mais o que responder aqui. */
function PlanejamentoEnviado() {
  return (
    <section className="w-full max-w-3xl bg-white rounded-2xl border border-primary/30 shadow-premium p-6 space-y-4">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <CheckCircle2 className="w-4 h-4 text-primary" />
        </span>
        <h2 className="text-base font-bold text-slate-900">{TITULO_DO_ENVIADO}</h2>
      </div>
      <p className="text-sm text-text-primary">{ENVIADO}</p>
      <Link
        href={ROTA_TECNOLOGIA}
        className="inline-flex items-center px-4 py-2 rounded-xl border border-border text-sm font-semibold text-text-primary hover:border-primary"
      >
        {VOLTAR_PARA_A_TECNOLOGIA}
      </Link>
    </section>
  );
}

export function PlanejamentoDaDemanda({ demandaId, token, onTitulo }: Props) {
  const [planejamento, setPlanejamento] = useState<Planejamento | null>(null);
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const fimDaLista = useRef<HTMLDivElement>(null);

  // O texto falado entra DEPOIS do que já estava escrito, nunca no lugar dele.
  const { gravando, transcrevendo, iniciarGravacao, pararGravacao } = useGravacaoVoz({
    getToken: () => token,
    onTexto: (transcrito) => setTexto((atual) => (atual.trim() ? `${atual.trimEnd()} ${transcrito}` : transcrito)),
  });
  // Enviar no meio da gravação mandaria a resposta sem a fala.
  const ocupado = pensando || gravando || transcrevendo;

  /** Um POST que devolve o planejamento inteiro; nulo quando não valeu. */
  const enviar = useCallback(
    async (url: string, corpo: unknown): Promise<Planejamento | null> => {
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
        const novo = await corpoValidado(resposta, planejamentoValido);
        if (novo === null) {
          setErro(CORPO_ILEGIVEL);
          return null;
        }
        setPlanejamento(novo);
        return novo;
      } catch (e) {
        console.error("[admin/tecnologia] falha no planejamento", e);
        setErro(FALHA_DE_CONEXAO);
        return null;
      } finally {
        setPensando(false);
      }
    },
    [token],
  );

  const responder = useCallback(
    async (corpo: RespostaDoPlanejamento): Promise<boolean> => {
      const novo = await enviar(urlDoPlanejamento(demandaId), corpo);
      // A IA encerrou: o resumo vem sozinho, sem esperar o clique em Fechar e
      // resumir. Se ele falhar, o botão continua lá para tentar de novo.
      if (novo?.estado === "encerrado") await enviar(urlDoResumo(demandaId), {});
      return novo !== null;
    },
    [demandaId, enviar],
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
        // Nada guardado, ou o "não" do resumo sem a pergunta seguinte: a IA fala.
        if (esperaAIA(lido)) responder({});
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
  const terminou = planejamento?.estado === "encerrado";
  const podeResumir = planejamento?.estado === "em_andamento" || planejamento?.estado === "encerrado";
  const semPerguntaDepoisDoErro = planejamento !== null && esperaAIA(planejamento) && !pensando && erro !== null;

  async function enviarOTexto() {
    const resposta = texto.trim();
    if (!resposta || ocupado) return;
    // O texto só sai da caixa quando o turno valeu: se falhar, ele continua lá.
    if (await responder({ texto: resposta })) setTexto("");
  }

  async function dizerNao(oQue: string): Promise<boolean> {
    const voltou = await enviar(urlDoNao(demandaId), { texto: oQue });
    if (voltou === null) return false;
    // A conversa voltou a em andamento com a fala no fim: a IA retoma dali.
    await responder({});
    return true;
  }

  const aviso = erro && (
    <p
      role="alert"
      className="lg:col-span-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm whitespace-pre-line"
    >
      {erro}
    </p>
  );

  if (planejamento?.estado === "enviado") return <PlanejamentoEnviado />;

  if (planejamento?.estado === "resumido" && planejamento.resumo) {
    return (
      <div className="space-y-4">
        {aviso}
        <ResumoDaConversa
          resumo={planejamento.resumo}
          pensando={pensando}
          onSim={() => enviar(urlDoEnvio(demandaId), {})}
          onNao={dizerNao}
          onRecusaNaTela={setErro}
        />
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[1fr_minmax(320px,380px)] gap-6 items-start">
      {aviso}

      {/* A conversa, à esquerda. */}
      <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-[calc(100vh-14rem)] min-h-[420px] overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100">
          <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" />
          </span>
          <h2 className="text-sm font-bold text-slate-900">{PLANEJAR_COM_A_IA}</h2>
          {podeResumir && (
            <button
              type="button"
              onClick={() => enviar(urlDoResumo(demandaId), {})}
              disabled={pensando}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-primary/40 text-xs font-semibold text-primary hover:bg-primary/5 disabled:opacity-50"
            >
              <ListChecks className="w-3.5 h-3.5" />
              {FECHAR_E_RESUMIR}
            </button>
          )}
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

          {semPerguntaDepoisDoErro && (
            <button
              type="button"
              onClick={() => responder({})}
              className="px-3 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5"
            >
              Tentar de novo
            </button>
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
                placeholder={transcrevendo ? "Transcrevendo a sua fala..." : "Ou responda por escrito ou pelo microfone"}
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
              {/* O microfone fica vivo enquanto grava: é o caminho de volta. */}
              <button
                type="button"
                onClick={() => (gravando ? pararGravacao() : iniciarGravacao())}
                disabled={!gravando && (ocupado || !pergunta)}
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
                disabled={ocupado || !pergunta || !texto.trim()}
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
