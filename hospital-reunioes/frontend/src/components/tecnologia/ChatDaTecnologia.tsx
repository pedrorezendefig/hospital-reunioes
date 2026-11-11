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
 * bateu". Na melhoria (issue #1383), a conversa segue ali mesmo pelo
 * Planejamento da Demanda: cada pergunta com duas opções e a recomendada em
 * destaque, o campo livre, "Fechar e resumir" fixo no alto, e o resumo com as
 * decisões e o que ficou em aberto, com os mesmos dois botões.
 *
 * Com `demandaId`, a conversa vem do servidor e continua de onde parou: é o
 * clique numa conversa da lista lateral (issue #1384). `onMudou` avisa a lista
 * a cada turno que valeu, para a Demanda que acabou de nascer aparecer nela.
 */

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Bot, CheckCircle2, FileText, ListChecks, Loader2, Mic, Paperclip, Send, Square } from "lucide-react";

import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";

import {
  ACEITOS_NO_ANEXO,
  AVISO_DE_IA,
  avisoDaImagem,
  avisoDoDocumento,
  classeDoAnexo,
  corpoValidado,
  descreverAImagem,
  LIMITE_DA_MENSAGEM,
  lerODocumento,
  mensagemComOrigem,
  PREFIXO_DE_PRINT,
  PRINT_SEM_LEITURA,
  recusaDoTipo,
  tamanhoLegivel,
} from "./assistente";
import {
  blocoDoRascunho,
  ConversaDoChat,
  conversaValida,
  Desenvolvedor,
  desenvolvedoresValidos,
  DocumentoDoPlanejamento,
  esperaAPergunta,
  FalaDoChat,
  frasesDosPrints,
  LETRAS,
  LetraDaOpcao,
  ResumoDaMelhoria,
  ResumoDoBug,
  RetratoDeHoje,
  textoDoCusto,
  URL_DO_CHAT_DA_ABA,
  URL_DOS_DESENVOLVEDORES,
  urlDaConversa,
  urlDoCriarOCard,
  urlDoNaoBateu,
  urlDoResumoDaMelhoria,
} from "./chat";
import { FALHA_DE_CONEXAO, motivoDaRecusa } from "./demandas";
import { FraseEOQueMuda } from "./DocumentoDoCard";

// A mesma pergunta que o backend guarda como primeira fala da conversa.
export const ABERTURA = "Isso é um bug, algo que não funciona como deveria, ou uma melhoria?";
export const CRIAR_O_CARD = "Criar o card";
export const CONTINUAR_RESPONDENDO = "Continuar respondendo";
export const NAO_BATEU = "Não bateu";
export const TITULO_DO_CHAT = "Assistente de Tecnologia";
export const FECHAR_E_RESUMIR = "Fechar e resumir";
export const QUEM_CUIDA_DISTO = "Quem cuida disto?";
const SEM_ESCOLHA = "Sem escolha";
const TITULO_DO_RESUMO = "Resumo do bug";
const TITULO_DO_RESUMO_DA_MELHORIA = "Resumo da melhoria";
const O_QUE_O_CARD_FAZ = "Criar o card manda o bug para o desenvolvimento da Vitta, que começa a trabalhar nele.";
const O_QUE_O_CARD_DA_MELHORIA_FAZ =
  "Criar o card manda o pedido para a Vitta, com as suas decisões e o que ficou em aberto. A parte técnica a Vitta planeja antes de começar.";
const ENVIADO =
  "A Vitta recebeu o seu relato e o bug já está na fila do desenvolvimento. Os prints ficaram guardados no aplicativo.";
const ENVIADO_DA_MELHORIA =
  "A Vitta recebeu o seu pedido, com as suas decisões e o que ficou em aberto. Ela planeja a parte técnica e depois começa a construir.";
const ENCERRADO =
  "A IA já tem o que precisa. O resumo aparece em seguida; se não aparecer, clique em Fechar e resumir. Se quiser acrescentar algo, é só escrever.";
const CONTINUAR_ESCREVENDO = "Quer acrescentar alguma coisa? Escreva aqui, e a IA volta a perguntar.";
const NENHUMA_DECISAO = "Nenhuma pergunta respondida fechou uma decisão.";
const NADA_EM_ABERTO = "Nada ficou em aberto.";
const NAO_SEM_TEXTO = "Diga o que não bateu no resumo.";
// O documento vivo do planejamento (issue #1553, ADR 0084, decisão 7).
export const TITULO_DO_DOCUMENTO_VIVO = "Documento do pedido";
export const DOCUMENTO_AINDA_VAZIO = "O documento se monta aqui conforme você responde.";
const SOBRE_O_DOCUMENTO_VIVO = "É o que o pedido vai mostrar depois de criado.";
export const SEM_CONVERSA_GUARDADA = "Este pedido é de antes do chat, e a conversa dele não ficou guardada aqui.";
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

export function Fala({ fala }: { fala: FalaDoChat }) {
  if (fala.autor === "diretor") {
    const documentos = fala.documentos ?? [];
    return (
      <div className="ml-auto max-w-[85%] flex flex-col items-end gap-1">
        {/* Quem respondeu o turno (issue #1557): na revisão, o Desenvolvedor também responde. */}
        {fala.respondido_por && <span className="normal-case text-xs text-text-secondary">{fala.respondido_por}</span>}
        {(fala.texto || fala.nao_bateu) && (
          <p className="px-3 py-2 rounded-2xl bg-primary text-white text-sm whitespace-pre-line">
            {fala.nao_bateu && <span className="font-semibold">O que não bateu no resumo: </span>}
            {fala.texto}
          </p>
        )}
        {/* O documento aparece pelo nome e pelo tamanho; o texto dele é só do assistente (issue #1520). */}
        {documentos.map((documento, i) => (
          <div
            key={i}
            role="group"
            aria-label={`Documento anexado: ${documento.nome}`}
            className="flex items-center gap-2 px-3 py-2 rounded-2xl bg-primary text-white text-sm"
          >
            <FileText className="w-4 h-4 flex-shrink-0" />
            <span className="normal-case break-all">{documento.nome}</span>
            <span className="text-xs text-white/80 whitespace-nowrap">{tamanhoLegivel(documento.tamanho_bytes)}</span>
          </div>
        ))}
      </div>
    );
  }
  if (fala.retrato) return <RetratoNaConversa retrato={fala.retrato} />;
  return (
    <div className="mr-auto max-w-[85%] space-y-1">
      <p className="px-3 py-2 rounded-2xl bg-slate-100 text-slate-800 text-sm whitespace-pre-line">{fala.texto}</p>
      {fala.fonte && <p className="px-3 text-xs text-text-secondary">De onde veio: material da Vitta sobre {fala.fonte}</p>}
    </div>
  );
}

/** O Retrato de hoje da revisão (issue #1557): os três blocos, e a versão em cada item de Já existe. */
function RetratoNaConversa({ retrato }: { retrato: RetratoDeHoje }) {
  const blocos: [string, ReactNode[]][] = [
    [
      "Já existe",
      retrato.ja_existe.map((i, n) => (
        <li key={n}>
          <span>{i.item}</span> <span className="text-xs text-text-secondary">{`desde a ${i.versao}`}</span>
        </li>
      )),
    ],
    ["Mudou desde o card", retrato.mudou.map((t, n) => <li key={n}>{t}</li>)],
    ["Continua em aberto", retrato.em_aberto.map((t, n) => <li key={n}>{t}</li>)],
  ];
  return (
    <section
      role="region"
      aria-label="Retrato de hoje"
      className="mr-auto max-w-[85%] space-y-2 px-3 py-2 rounded-2xl bg-slate-100 text-slate-800 text-sm"
    >
      <h3 className="font-semibold">Retrato de hoje</h3>
      {blocos.map(([titulo, itens]) => (
        <div key={titulo}>
          <p className="text-xs font-semibold uppercase text-text-secondary">{titulo}</p>
          {itens.length > 0 ? (
            <ul className="list-disc pl-5 space-y-1">{itens}</ul>
          ) : (
            <p className="text-text-secondary">Nada.</p>
          )}
        </div>
      ))}
    </section>
  );
}

function CorpoDoResumoDoBug({ resumo, anexos }: { resumo: ResumoDoBug; anexos: number }) {
  return (
    <>
      <p className="text-sm font-semibold text-text-primary">{resumo.titulo}</p>

      <dl className="space-y-3 text-sm">
        {ROTULOS_DO_RESUMO.map(([campo, rotulo]) => (
          <div key={campo}>
            <dt className="font-semibold uppercase text-text-primary">{rotulo}</dt>
            <dd className="text-text-secondary whitespace-pre-line">{resumo[campo] as string}</dd>
          </div>
        ))}
        <div>
          <dt className="font-semibold uppercase text-text-primary">Prints</dt>
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
    </>
  );
}

type PropsDoResumoDaMelhoria = {
  resumo: ResumoDaMelhoria;
  pensando: boolean;
  /** Volta às perguntas pelo que ficou em aberto (ADR 0079, decisão 4). */
  onContinuar: () => void;
};

/** O resumo da melhoria: as decisões do diretor e o que ficou em aberto. */
function CorpoDoResumoDaMelhoria({ resumo, pensando, onContinuar }: PropsDoResumoDaMelhoria) {
  return (
    <>
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-text-primary">Decisões</h3>
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
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-bold text-text-primary">Ficou em aberto</h3>
        {resumo.em_aberto.length > 0 ? (
          <>
            <ul className="list-disc pl-5 space-y-1 text-sm text-text-primary">
              {resumo.em_aberto.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
            <button
              type="button"
              onClick={onContinuar}
              disabled={pensando}
              className="px-4 py-2 rounded-xl border border-primary text-sm font-semibold text-primary hover:bg-primary/5 disabled:opacity-50"
            >
              {CONTINUAR_RESPONDENDO}
            </button>
          </>
        ) : (
          <p className="text-sm text-text-secondary">{NADA_EM_ABERTO}</p>
        )}
      </div>
    </>
  );
}

/**
 * "Quem cuida disto?" (issue #1533, ADR 0083, decisão 5): os Desenvolvedores
 * que o servidor lista. A escolha é opcional; sem a lista (a rede fora), a
 * pergunta não aparece e o Criar o card segue valendo.
 */
function QuemCuidaDisto({
  token,
  escolhido,
  onEscolher,
}: {
  token: string | null;
  escolhido: string;
  onEscolher: (id: string) => void;
}) {
  const [desenvolvedores, setDesenvolvedores] = useState<Desenvolvedor[]>([]);

  useEffect(() => {
    if (!token) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(URL_DOS_DESENVOLVEDORES, { headers: { Authorization: `Bearer ${token}` } });
        if (!resposta.ok) return;
        const lidos = desenvolvedoresValidos(await resposta.json());
        if (viva) setDesenvolvedores(lidos);
      } catch (e) {
        console.error("[admin/tecnologia] falha ao listar quem cuida", e);
      }
    })();
    return () => {
      viva = false;
    };
  }, [token]);

  if (desenvolvedores.length === 0) return null;
  const padrao = desenvolvedores.find((d) => d.padrao);
  return (
    <div className="space-y-1">
      <label htmlFor="quem-cuida-disto" className="text-sm font-semibold text-text-primary">
        {QUEM_CUIDA_DISTO}
      </label>
      <select
        id="quem-cuida-disto"
        value={escolhido}
        onChange={(e) => onEscolher(e.target.value)}
        className="w-full sm:w-72 px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
      >
        <option value="">{SEM_ESCOLHA}</option>
        {desenvolvedores.map((d) => (
          <option key={d.id} value={d.id}>
            {d.nome}
          </option>
        ))}
      </select>
      <p className="text-xs text-text-secondary">
        {padrao ? `Escolher é opcional. Sem escolha, o card vai para ${padrao.nome}.` : "Escolher é opcional."}
      </p>
    </div>
  );
}

type PropsDoResumo = {
  titulo: string;
  token: string | null;
  /** A frase debaixo dos botões, que diz o que o Criar o card faz. */
  oQueOCardFaz: string;
  pensando: boolean;
  /** Cria o card com o Responsável escolhido, ou sem ninguém escolhido. */
  onCriar: (responsavelId: string | null) => void;
  /** Manda o que não bateu; devolve se o servidor aceitou. */
  onNaoBateu: (texto: string) => Promise<boolean>;
  onRecusaNaTela: (motivo: string) => void;
  children: React.ReactNode;
};

/** A caixa do resumo, do bug ou da melhoria, com Criar o card e Não bateu. */
function ResumoNaTela({
  titulo,
  token,
  oQueOCardFaz,
  pensando,
  onCriar,
  onNaoBateu,
  onRecusaNaTela,
  children,
}: PropsDoResumo) {
  const [dizendo, setDizendo] = useState(false);
  const [responsavel, setResponsavel] = useState("");
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
      aria-label={titulo}
      className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-6 space-y-5"
    >
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <ListChecks className="w-4 h-4 text-primary" />
        </span>
        <h2 className="text-base font-bold text-slate-900">{titulo}</h2>
      </div>

      {children}

      <div className="space-y-3 border-t border-slate-100 pt-4">
        <QuemCuidaDisto token={token} escolhido={responsavel} onEscolher={setResponsavel} />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onCriar(responsavel || null)}
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
        <p className="text-xs text-text-secondary">{oQueOCardFaz}</p>
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

/**
 * O documento do pedido ao lado do chat da melhoria (issue #1553), no molde da
 * ata viva da Ata Guiada: o agente o reescreve a cada turno, e ele é lido pelo
 * mesmo componente do Documento do card, para o diretor ver aqui o que o card
 * vai mostrar.
 */
function DocumentoVivo({ documento, chave }: { documento: DocumentoDoPlanejamento | null; chave: string }) {
  const texto = documento ? blocoDoRascunho(documento) : "";
  return (
    <section
      aria-label={TITULO_DO_DOCUMENTO_VIVO}
      className="w-full bg-white rounded-2xl border border-slate-200 shadow-premium px-5 py-4 space-y-2"
    >
      <div className="flex items-center gap-2">
        <FileText className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-bold text-slate-900">{TITULO_DO_DOCUMENTO_VIVO}</h2>
      </div>
      <p className="text-xs text-text-secondary">{SOBRE_O_DOCUMENTO_VIVO}</p>
      {texto ? (
        <FraseEOQueMuda texto={texto} chave={chave} />
      ) : (
        <p className="text-sm text-text-secondary italic">{DOCUMENTO_AINDA_VAZIO}</p>
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

type PropsDoChat = {
  token: string | null;
  /** A conversa da lista a retomar; sem ela, o chat abre do zero. */
  demandaId?: string | null;
  /** Um turno valeu: a Demanda nasceu ou mudou de título. */
  onMudou?: (demandaId: string) => void;
};

/** Como está a leitura da conversa guardada, quando há uma a retomar. */
type Carga = "carregando" | "pronta" | "sem_chat" | "falhou";

export function ChatDaTecnologia({ token, demandaId = null, onMudou }: PropsDoChat) {
  const [conversa, setConversa] = useState<ConversaDoChat | null>(null);
  const [carga, setCarga] = useState<Carga>(demandaId ? "carregando" : "pronta");
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const entradaDeAnexo = useRef<HTMLInputElement>(null);
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
        onMudou?.(nova.demanda_id);
        return nova;
      } catch (e) {
        console.error("[admin/tecnologia] falha no chat", e);
        setErro(FALHA_DE_CONEXAO);
        return null;
      } finally {
        setPensando(false);
      }
    },
    [token, onMudou],
  );

  /**
   * O "Criar o card". A falha fica gravada na Demanda como Envio falhou
   * (issue #1535), e a lista relê para mostrar o selo.
   */
  const criarOCard = useCallback(
    async (demandaId: string, responsavelId: string | null): Promise<ConversaDoChat | null> => {
      const nova = await enviar(urlDoCriarOCard(demandaId), responsavelId ? { responsavel_id: responsavelId } : {});
      if (nova === null) onMudou?.(demandaId);
      return nova;
    },
    [enviar, onMudou],
  );

  /**
   * O que a melhoria pede sozinha depois de um turno (issue #1383): a pergunta
   * seguinte quando ainda não há pergunta esperando (a passagem ao
   * planejamento, o "Não bateu"), e o resumo quando as perguntas acabaram.
   */
  const seguir = useCallback(
    async (nova: ConversaDoChat | null): Promise<void> => {
      let atual = nova;
      if (atual && esperaAPergunta(atual)) atual = await enviar(urlDaConversa(atual.demanda_id), {});
      if (atual?.planejamento && atual.estado === "encerrado") {
        await enviar(urlDoResumoDaMelhoria(atual.demanda_id), {});
      }
    },
    [enviar],
  );

  /** Um turno que, valendo, deixa a melhoria seguir sozinha; diz se valeu. */
  const turno = useCallback(
    async (url: string, corpo: unknown): Promise<boolean> => {
      const nova = await enviar(url, corpo);
      if (nova === null) return false;
      await seguir(nova);
      return true;
    },
    [enviar, seguir],
  );

  /**
   * A conversa guardada, para retomar de onde parou. Sem conversa do chat
   * (404) é um pedido de antes do chat (ADR 0077): não há o que retomar, e a
   * tela da conversa que ele tinha saiu na issue #1386.
   */
  useEffect(() => {
    if (!demandaId || !token) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(urlDaConversa(demandaId), { headers: { Authorization: `Bearer ${token}` } });
        if (!viva) return;
        if (resposta.status === 404) {
          setCarga("sem_chat");
          return;
        }
        if (!resposta.ok) {
          setErro(await motivoDaRecusa(resposta));
          setCarga("falhou");
          return;
        }
        const guardada = await corpoValidado(resposta, conversaValida);
        if (!viva) return;
        if (guardada === null) {
          setErro(CORPO_ILEGIVEL);
          setCarga("falhou");
          return;
        }
        setConversa(guardada);
        setCarga("pronta");
      } catch (e) {
        console.error("[admin/tecnologia] falha ao abrir a conversa", e);
        if (!viva) return;
        setErro(FALHA_DE_CONEXAO);
        setCarga("falhou");
      }
    })();
    return () => {
      viva = false;
    };
  }, [demandaId, token]);

  /** A fala do diretor: o primeiro turno faz a Demanda nascer, os outros seguem nela. */
  const falar = useCallback(
    async (fala: string, prints: string[] = [], documentos: string[] = []): Promise<boolean> => {
      const url = conversa ? urlDaConversa(conversa.demanda_id) : URL_DO_CHAT_DA_ABA;
      return turno(url, { texto: fala, prints, ...(documentos.length > 0 ? { documentos } : {}) });
    },
    [conversa, turno],
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
      await turno(URL_DO_CHAT_DA_ABA, { escolha: opcao === "Bug" ? "bug" : "melhoria" });
      return;
    }
    await falar(opcao);
  }

  /** A opção da pergunta da melhoria vai pela letra: o texto o servidor tira da própria pergunta. */
  async function escolherALetra(letra: LetraDaOpcao) {
    if (ocupado || !conversa) return;
    await turno(urlDaConversa(conversa.demanda_id), { opcao: letra });
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

  /**
   * O documento sobe à rota que extrai o texto, e a fala leva só o
   * identificador (issue #1520): o texto vai do servidor ao assistente, e a
   * conversa mostra o nome e o tamanho.
   */
  async function anexarODocumento(arquivo: File) {
    const aviso = avisoDoDocumento(arquivo);
    if (aviso) {
      setErro(aviso);
      return;
    }
    setPensando(true);
    const leitura = await lerODocumento(arquivo, token);
    setPensando(false);
    if ("aviso" in leitura) {
      setErro(leitura.aviso);
      return;
    }
    await falar("", [], [leitura.corpo.documento_id]);
  }

  /** O botão de anexo é um só: a extensão diz se é print ou documento. */
  function anexar(arquivo: File) {
    const classe = classeDoAnexo(arquivo.name);
    if (classe === "imagem") return anexarOPrint(arquivo);
    if (classe === "documento") return anexarODocumento(arquivo);
    setErro(recusaDoTipo(arquivo.name));
  }

  async function naoBateu(oQue: string): Promise<boolean> {
    if (!conversa) return false;
    const voltou = await enviar(urlDoNaoBateu(conversa.demanda_id), { texto: oQue });
    if (voltou === null) return false;
    // A conversa voltou a em andamento com a fala no fim: a IA retoma dali.
    await turno(urlDaConversa(voltou.demanda_id), {});
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

  if (carga === "carregando") {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-text-secondary">
        <Loader2 className="w-4 h-4 animate-spin" />
        Abrindo a conversa...
      </p>
    );
  }

  if (carga === "falhou") return aviso || null;

  if (carga === "sem_chat") {
    return (
      <p role="status" className="px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-sm text-text-secondary">
        {SEM_CONVERSA_GUARDADA}
      </p>
    );
  }

  if (conversa?.estado === "enviado") {
    return (
      <Fechamento texto={conversa.planejamento ? ENVIADO_DA_MELHORIA : ENVIADO}>
        {/* Só leitura: o Responsável muda no GitHub e a tela acompanha (issue #1534, ADR 0083, decisão 6). */}
        {conversa.responsavel && <p className="text-sm text-text-secondary">Responsável: {conversa.responsavel}</p>}
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
          titulo={TITULO_DO_RESUMO}
          oQueOCardFaz={O_QUE_O_CARD_FAZ}
          pensando={pensando}
          token={token}
          onCriar={(responsavelId) => criarOCard(conversa.demanda_id, responsavelId)}
          onNaoBateu={naoBateu}
          onRecusaNaTela={setErro}
        >
          <CorpoDoResumoDoBug resumo={conversa.resumo} anexos={conversa.anexos} />
        </ResumoNaTela>
      </div>
    );
  }

  // O campo livre da conversa. Na melhoria ele segue ativo depois do
  // encerramento e do resumo, até o Criar o card (ADR 0079, decisão 3).
  const campoLivre = (
    <div className="flex gap-2">
      <textarea
        aria-label="Sua mensagem"
        rows={1}
        maxLength={LIMITE_DA_MENSAGEM}
        placeholder={
          transcrevendo ? "Transcrevendo a sua fala..." : "Escreva, fale no microfone ou anexe um print ou documento"
        }
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
        ref={entradaDeAnexo}
        type="file"
        accept={ACEITOS_NO_ANEXO}
        className="hidden"
        onChange={(e) => {
          const arquivo = e.target.files?.[0];
          e.target.value = "";
          if (arquivo) void anexar(arquivo);
        }}
      />
      <button
        type="button"
        onClick={() => entradaDeAnexo.current?.click()}
        disabled={ocupado}
        aria-label="Anexar print ou documento"
        title="Anexar print ou documento"
        className="px-3 py-2 rounded-xl border border-border text-text-secondary hover:border-primary hover:text-primary disabled:opacity-50 transition-colors"
      >
        <Paperclip className="w-4 h-4" />
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
  );

  if (conversa?.estado === "resumido" && conversa.resumo_da_melhoria) {
    return (
      <div className="space-y-4">
        {aviso}
        <ResumoNaTela
          titulo={TITULO_DO_RESUMO_DA_MELHORIA}
          oQueOCardFaz={O_QUE_O_CARD_DA_MELHORIA_FAZ}
          pensando={pensando}
          token={token}
          onCriar={(responsavelId) => criarOCard(conversa.demanda_id, responsavelId)}
          onNaoBateu={naoBateu}
          onRecusaNaTela={setErro}
        >
          <CorpoDoResumoDaMelhoria
            resumo={conversa.resumo_da_melhoria}
            pensando={pensando}
            onContinuar={() => void turno(urlDaConversa(conversa.demanda_id), { continuar: true })}
          />
        </ResumoNaTela>
        <section
          aria-label="Continuar a conversa"
          className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium px-5 py-3 space-y-2"
        >
          <p className="text-xs text-text-secondary">{CONTINUAR_ESCREVENDO}</p>
          {campoLivre}
        </section>
      </div>
    );
  }

  const falas = conversa?.mensagens ?? [ABERTURA_NA_TELA];
  const ultima = falas[falas.length - 1];
  const opcoes = ultima?.autor === "ia" ? ultima.opcoes : [];
  const recomendada = ultima?.autor === "ia" ? ultima.recomendada : null;
  const naMelhoria = conversa?.planejamento ?? false;
  const encerrado = naMelhoria && conversa?.estado === "encerrado";
  const podeResumir = naMelhoria && (conversa?.estado === "em_andamento" || encerrado);
  // Nada respondeu à última fala: o "não bateu" cuja retomada falhou, ou a
  // pergunta da melhoria que não veio.
  const esperaAIA =
    conversa !== null && !pensando && (naMelhoria ? esperaAPergunta(conversa) : ultima?.autor === "diretor");

  const chat = (
    <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-[calc(100vh-18rem)] min-h-[420px] overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100">
        <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <Bot className="w-4 h-4 text-primary" />
        </span>
        <h2 className="text-sm font-bold text-slate-900">{TITULO_DO_CHAT}</h2>
        {conversa?.custo && <span className="text-xs text-text-secondary">{textoDoCusto(conversa.custo)}</span>}
        {podeResumir && conversa && (
          <button
            type="button"
            onClick={() => enviar(urlDoResumoDaMelhoria(conversa.demanda_id), {})}
            disabled={ocupado}
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-primary/40 text-xs font-semibold text-primary hover:bg-primary/5 disabled:opacity-50"
          >
            <ListChecks className="w-3.5 h-3.5" />
            {FECHAR_E_RESUMIR}
          </button>
        )}
      </div>

      <div role="log" className="flex-1 overflow-y-auto px-5 py-4 space-y-3 overscroll-contain">
        {falas.map((fala, i) => (
          <Fala key={i} fala={fala} />
        ))}

        {opcoes.length > 0 && !pensando && recomendada && (
          <div role="group" aria-label="Opções" className="flex flex-col gap-2 max-w-[85%]">
            {opcoes.map((opcao, i) => {
              const letra = LETRAS[i];
              const destaque = letra === recomendada;
              return (
                <button
                  key={letra}
                  type="button"
                  onClick={() => escolherALetra(letra)}
                  className={`text-left px-3 py-2 rounded-xl border text-sm transition-colors ${
                    destaque
                      ? "border-primary bg-primary/5 text-slate-900 ring-1 ring-primary"
                      : "border-border text-slate-800 hover:border-primary"
                  }`}
                >
                  <span className="font-semibold">{letra}) </span>
                  <span className="normal-case">{opcao}</span>
                  {destaque && (
                    <span className="ml-2 inline-block px-2 py-0.5 rounded-full bg-primary text-white text-xs font-semibold">
                      Recomendada
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {opcoes.length > 0 && !pensando && !recomendada && (
          <div role="group" aria-label="Opções" className="flex flex-wrap gap-2 max-w-[85%]">
            {opcoes.map((opcao) => (
              <button
                key={opcao}
                type="button"
                onClick={() => escolher(opcao)}
                className="normal-case px-4 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5"
              >
                {opcao}
              </button>
            ))}
          </div>
        )}

        {encerrado && !pensando && (
          <p role="status" className="text-xs text-text-secondary">
            {ENCERRADO}
          </p>
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
            onClick={() => conversa && turno(urlDaConversa(conversa.demanda_id), {})}
            className="px-3 py-2 rounded-xl border border-primary/40 text-sm font-semibold text-primary hover:bg-primary/5"
          >
            Tentar de novo
          </button>
        )}
        <div ref={fimDaLista} />
      </div>

      <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
        {campoLivre}
        <p className="mt-1.5 text-xs text-slate-400">{AVISO_DE_IA}</p>
      </div>
    </section>
  );

  return (
    <div className="space-y-4">
      {aviso}
      {naMelhoria && conversa ? (
        // O documento ao lado do chat, como a ata viva da Ata Guiada (issue #1553).
        <div className="grid lg:grid-cols-[1fr_minmax(260px,340px)] gap-4 items-start">
          {chat}
          <div className="lg:sticky lg:top-4">
            <DocumentoVivo documento={conversa.documento ?? null} chave={conversa.demanda_id} />
          </div>
        </div>
      ) : (
        chat
      )}
    </div>
  );
}
