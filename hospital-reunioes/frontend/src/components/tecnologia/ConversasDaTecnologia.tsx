"use client";

/**
 * A aba Assistente da Tecnologia com a lista lateral (issue #1384, PRD #1380, ADR 0077).
 *
 * Ao lado do chat, a lista das Demandas de quem está logado, com o título e a
 * Etapa, da mais recente para a mais antiga (a ordem é do servidor). Clicar
 * numa conversa sem card retoma o chat de onde parou; clicar numa que já tem
 * Vínculo mostra a conversa e O que muda. "Nova conversa" abre o chat do zero.
 *
 * No celular só um dos dois lados aparece por vez: a lista é a tela de
 * entrada, e a conversa aberta tem o caminho de volta. Na tela larga os dois
 * ficam lado a lado.
 *
 * O Desenvolvedor (issue #1531, ADR 0083) tem o filtro "Todas", com o autor
 * em cada linha. A Demanda de outro autor abre só para leitura, com a
 * entrevista inteira, os Anexos e o número e o link da issue. Quem é
 * Desenvolvedor é o servidor que diz.
 *
 * Cada linha com card mostra o Responsável, para todos, e a lista do
 * Desenvolvedor abre em "Para mim", as Demandas de que ele cuida (issue
 * #1533, ADR 0083, decisão 5).
 *
 * Toda Demanda aberta tem, embaixo, a Conversa da Demanda, numa área própria
 * (issue #1537, ADR 0083, decisão 8). O aviso do sino chega com a Demanda em
 * `demandaInicial` e a abre: o Desenvolvedor a procura em "Todas", porque a
 * menção pode ser numa Demanda de que ele não é o Responsável.
 *
 * O card que não chegou ao GitHub fica com o selo "Envio falhou" na lista, e a
 * conversa aberta traz o "Reenviar", para o autor e para o Desenvolvedor. Só o
 * Desenvolvedor lê o motivo técnico e tem o filtro "Envio falhou" (issue
 * #1535, ADR 0083, decisão 7). O card que nasceu sem o Responsável aparece
 * só para o Desenvolvedor, com o "Designar de novo" (issue #1536).
 *
 * A conversa aberta tem o "Apagar" para quem pode, com confirmação: o autor
 * na conversa Registrada, o Desenvolvedor no card até Planejada (issue
 * #1549, ADR 0084, decisão 2). Quem pode é o servidor que diz.
 *
 * Os filtros ficam numa barra em cima, na largura toda, um campo com rótulo
 * por categoria (issue #1578, emenda da ADR 0084, que trocou os chips da
 * #1551): Tipo, Etapa e Origem para todos; o recorte (Para mim, Minhas,
 * Todas, controle segmentado), o Responsável e o "Só envio falhou" só para o
 * Desenvolvedor. Tudo combina, e quem filtra é o servidor.
 *
 * Na tela larga o clique no card abre a Demanda ao lado da lista (issue #1593,
 * que reverteu o recolher da #1551). O Ampliar, no canto do card e no topo da
 * Demanda aberta, recolhe a barra e a lista, e o Voltar às conversas as traz de
 * volta; o próximo clique num card volta a abrir ao lado. No celular, a lista e
 * a Demanda seguem uma de cada vez, com o Voltar.
 *
 * Cada conversa é um card com contorno: título, data de abertura, quem pediu
 * e quem cuida com as iniciais, as partes do PRD numa barra e os selos. O
 * "Conversar" do card abre a Demanda com a caixa da Conversa da Demanda em
 * foco. Ao lado da lista, a Conversa da Demanda fica embaixo do documento;
 * ampliada, numa coluna à direita, fixa na rolagem (issues #1578 e #1593).
 *
 * Os cards que a Vitta abre pelo terminal aparecem na lista com o selo
 * "Vitta", e os do chat com "Pedido do diretor"; o chip Origem filtra (issue
 * #1554, ADR 0084, decisão 4). O card da Vitta abre o documento e a Conversa
 * da Demanda, sem conversa com o agente.
 *
 * O card de melhoria Em análise ou Planejada tem o "Revisar com o código de
 * hoje" para o autor e o Desenvolvedor (issue #1557, ADR 0084, decisão 3). O
 * clique mostra antes quanto o Retrato de hoje deve custar, e a revisão só
 * começa com a confirmação (ADR 0082). Em revisão, o card abre a conversa para
 * responder. Quem pode é o servidor que diz.
 */

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, Maximize2, MessageSquare, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Select } from "@/components/ui/Select";

import { ChatDaTecnologia, Fala } from "./ChatDaTecnologia";
import { ConversaDaDemanda } from "./ConversaDaDemanda";
import { DocumentoDoCard } from "./DocumentoDoCard";
import { SeloDeEtapa } from "./SeloDeEtapa";
import {
  AnexoDaDemanda,
  conversaValida,
  Desenvolvedor,
  desenvolvedoresValidos,
  EstimativaDaRevisao,
  FalaDoChat,
  textoDaEstimativa,
  URL_DO_CHAT_DA_ABA,
  URL_DOS_DESENVOLVEDORES,
  urlDaConversa,
  urlDaRevisao,
  urlDoDesignarDeNovo,
  urlDoReenviar,
} from "./chat";
import {
  BASE_TECNOLOGIA,
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  Classificacao,
  Demanda,
  ETAPA_CLASSE,
  EtapaDemanda,
  ETAPA_ROTULO,
  FALHA_DE_CONEXAO,
  iniciais,
  linkDaDemonstracao,
  motivoDaRecusa,
  Origem,
  ORIGEM_CLASSE,
  ORIGEM_ROTULO,
  partesDoCard,
  rotuloDaEtapa,
  TEM_DEMONSTRACAO,
  temSelo,
  textoDaAbertura,
} from "./demandas";

export const NOVA_CONVERSA = "Nova conversa";
export const VOLTAR_PARA_A_LISTA = "Voltar às conversas";
export const AMPLIAR = "Ampliar";
const AMPLIAR_EXPLICADO = "Abrir este pedido em tela cheia";
export const ENVIO_FALHOU = "Envio falhou";
export const REENVIAR = "Reenviar";
export const DESIGNACAO_FALHOU = "Designação falhou";
export const DESIGNAR_DE_NOVO = "Designar de novo";
export const APAGAR = "Apagar";
export const REVISAR_COM_O_CODIGO_DE_HOJE = "Revisar com o código de hoje";
const REVISAR_TITULO = "Revisar este pedido com o código de hoje?";
const REVISAR = "Revisar";
const APAGAR_TITULO = "Apagar este pedido?";
const APAGAR_A_CONVERSA_EXPLICADO =
  "A conversa sai da lista com os anexos. Não dá para desfazer.";
const APAGAR_O_CARD_EXPLICADO =
  "O pedido sai da lista com a conversa e os anexos, e o card fecha como não planejado no desenvolvimento. Não dá para desfazer.";
const DESIGNACAO_FALHOU_EXPLICADO =
  "O card nasceu no GitHub sem o Responsável. Designar de novo pede só a designação, sem criar outro card.";
const ENVIO_FALHOU_EXPLICADO =
  "Este card não chegou à Vitta. O que você disse continua guardado: clique em Reenviar para tentar de novo.";
const LISTA_VAZIA = "Nenhuma conversa ainda.";
const LISTA_FALHOU = "Não foi possível carregar as suas conversas. Tente recarregar a página.";
const URL_QUEM_SOU = `${BASE_TECNOLOGIA}/eu`;

type Filtro = "para_mim" | "minhas" | "todas";
const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "para_mim", rotulo: "Para mim" },
  { valor: "minhas", rotulo: "Minhas" },
  { valor: "todas", rotulo: "Todas" },
];
const CLASSIFICACOES = Object.keys(CLASSIFICACAO_ROTULO) as Classificacao[];
const ETAPAS = Object.keys(ETAPA_ROTULO) as EtapaDemanda[];
const ORIGENS = Object.keys(ORIGEM_ROTULO) as Origem[];
/** As opções de cada campo da barra; o valor vazio é "sem filtro" (issue #1578). */
const OPCOES_DE_TIPO = [
  { value: "", label: "Todos" },
  ...CLASSIFICACOES.map((valor) => ({ value: valor, label: CLASSIFICACAO_ROTULO[valor] })),
];
const OPCOES_DE_ETAPA = [
  { value: "", label: "Todas" },
  ...ETAPAS.map((valor) => ({ value: valor, label: ETAPA_ROTULO[valor] })),
];
const OPCOES_DE_ORIGEM = [
  { value: "", label: "Todas" },
  ...ORIGENS.map((valor) => ({ value: valor, label: ORIGEM_ROTULO[valor] })),
];
const LIMPAR_FILTROS = "Limpar filtros";
const SO_ENVIO_FALHOU = "Só envio falhou";
const CONVERSAR = "Conversar";
/** A espera depois da última tecla, para a busca não pedir a lista a cada letra. */
const ESPERA_DA_BUSCA_MS = 300;

/** O que a lista pede ao servidor (issue #1551). */
type FiltrosDaLista = {
  recorte: Filtro;
  busca: string;
  tipo: Classificacao | null;
  etapa: EtapaDemanda | null;
  origem: Origem | null;
  responsavel: string | null;
  envioFalhou: boolean;
};

/** A URL da lista: sem nenhum filtro, a de antes (as Demandas de quem está logado). */
function urlDaLista(filtros: FiltrosDaLista): string {
  const consulta = new URLSearchParams();
  if (filtros.recorte !== "minhas") consulta.set("filtro", filtros.recorte);
  if (filtros.busca) consulta.set("busca", filtros.busca);
  if (filtros.tipo) consulta.set("tipo", filtros.tipo);
  if (filtros.etapa) consulta.set("etapa", filtros.etapa);
  if (filtros.origem) consulta.set("origem", filtros.origem);
  if (filtros.responsavel) consulta.set("responsavel", filtros.responsavel);
  if (filtros.envioFalhou) consulta.set("envio_falhou", "true");
  const texto = consulta.toString();
  return texto ? `${URL_DO_CHAT_DA_ABA}?${texto}` : URL_DO_CHAT_DA_ABA;
}

/** Um chip de filtro. Nada de `flex-1` nem `nowrap`: a linha quebra dentro da coluna. */
export function Chip({ ativo, onClick, children }: { ativo: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={`px-3 py-1 rounded-full border text-xs font-semibold ${
        ativo ? "border-primary bg-primary/5 text-primary" : "border-border text-text-secondary"
      }`}
    >
      {children}
    </button>
  );
}

export function GrupoDeChips({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={rotulo} className="flex flex-wrap gap-1">
      {children}
    </div>
  );
}

/** O item serve para a lista? O resto da Demanda é opcional para ela. */
function itemValido(item: unknown): item is Demanda {
  if (typeof item !== "object" || item === null) return false;
  const d = item as Record<string, unknown>;
  return typeof d.id === "string" && typeof d.titulo === "string";
}

/**
 * A Etapa na lista. Aqui "Registrada" aparece escrita: é a conversa sem card,
 * e a lista mostra a Etapa de toda conversa (na conversa aberta ela é a
 * ausência de selo).
 */
function EtapaNaLista({ demanda }: { demanda: Demanda }) {
  const classe = temSelo(demanda) && demanda.etapa ? ETAPA_CLASSE[demanda.etapa] : ETAPA_CLASSE.registrada;
  return <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${classe}`}>{rotuloDaEtapa(demanda)}</span>;
}

/** Bug ou Melhoria, ao lado da Etapa (issue #1438). O pedido de antes do chat fica sem. */
function ClassificacaoNaLista({ demanda }: { demanda: Demanda }) {
  if (!demanda.classificacao) return null;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${CLASSIFICACAO_CLASSE[demanda.classificacao]}`}>
      {CLASSIFICACAO_ROTULO[demanda.classificacao]}
    </span>
  );
}

/** Pedido do diretor ou Vitta (issue #1554). Sem o campo, sem selo. */
function OrigemNaLista({ demanda }: { demanda: Demanda }) {
  if (!demanda.origem) return null;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ORIGEM_CLASSE[demanda.origem]}`}>
      {ORIGEM_ROTULO[demanda.origem]}
    </span>
  );
}

/** O pedido que tem vídeo de demonstração (issue #1559). Sem link, sem selo. */
function SeloDaDemonstracao({ demanda }: { demanda: Demanda }) {
  if (!linkDaDemonstracao(demanda)) return null;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-700">{TEM_DEMONSTRACAO}</span>;
}

/** O selo do card que não chegou ao GitHub (issue #1535). */
function SeloDoEnvioFalhou({ demanda }: { demanda: Demanda }) {
  if (!demanda.envio_falhou) return null;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700">{ENVIO_FALHOU}</span>;
}

/** Quem pediu ou quem cuida, com as iniciais num círculo (issue #1578). */
function PessoaNoCard({ papel, nome }: { papel: string; nome: string }) {
  return (
    <span className="flex items-center gap-2 min-w-0">
      <span
        aria-hidden="true"
        className="w-7 h-7 shrink-0 rounded-full bg-primary/10 text-primary text-[11px] font-bold flex items-center justify-center"
      >
        {iniciais(nome)}
      </span>
      <span className="flex flex-col min-w-0 leading-tight">
        <span className="text-[10px] font-semibold tracking-wide text-slate-400">{papel}</span>
        <span className="normal-case text-xs font-medium text-text-primary truncate">{nome}</span>
      </span>
    </span>
  );
}

/** As partes do PRD numa barra (issue #1578). A issue simples não tem barra. */
function PartesNoCard({ demanda }: { demanda: Demanda }) {
  const partes = partesDoCard(demanda);
  if (!partes) return null;
  const largura = `${Math.round((partes.entregues / partes.total) * 100)}%`;
  return (
    <span className="flex items-center gap-3">
      <span
        role="progressbar"
        aria-label="Partes entregues"
        aria-valuemin={0}
        aria-valuemax={partes.total}
        aria-valuenow={partes.entregues}
        className="h-1.5 flex-1 rounded-full bg-slate-100 overflow-hidden"
      >
        <span className="block h-full rounded-full bg-emerald-500" style={{ width: largura }} />
      </span>
      <span className="normal-case text-xs font-medium text-text-secondary whitespace-nowrap">
        {partes.entregues} de {partes.total} partes
      </span>
    </span>
  );
}

/**
 * O card de uma conversa na lista (issue #1578). Contorno sempre visível; no
 * hover e no foco ele se destaca e sobe um pouco, sem movimento para quem
 * pediu menos animação ao sistema. O "Conversar" fica num botão próprio, ao
 * lado do card, porque botão dentro de botão não existe no HTML. Ao lado dele,
 * o Ampliar abre o pedido em tela cheia, e fica sempre à vista na tela larga
 * (issue #1593).
 */
function CardDaConversa({
  demanda,
  destacada,
  onAbrir,
  onConversar,
  onAmpliar,
}: {
  demanda: Demanda;
  destacada: boolean;
  onAbrir: () => void;
  onConversar: () => void;
  onAmpliar: () => void;
}) {
  const abertura = textoDaAbertura(demanda.criado_em);
  return (
    <div
      className={`group relative rounded-2xl border bg-white transition duration-150 ease-out motion-reduce:transition-none ${
        destacada
          ? "border-primary ring-2 ring-primary/15 shadow-md"
          : "border-border shadow-sm motion-safe:hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-within:border-primary/40 focus-within:shadow-md"
      }`}
    >
      <button
        type="button"
        onClick={onAbrir}
        aria-current={destacada ? "true" : undefined}
        className="w-full flex flex-col gap-3 p-4 pr-14 md:pr-24 text-left rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="flex flex-col gap-1">
          <span className="normal-case text-[15px] font-semibold leading-snug text-text-primary line-clamp-2">
            {demanda.titulo}
          </span>
          {abertura && <span className="normal-case text-xs text-text-secondary">{abertura}</span>}
        </span>
        {(demanda.autor || demanda.responsavel) && (
          <span className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {demanda.autor && <PessoaNoCard papel="Pediu" nome={demanda.autor} />}
            {demanda.responsavel && <PessoaNoCard papel="Responsável" nome={demanda.responsavel} />}
          </span>
        )}
        <PartesNoCard demanda={demanda} />
        <span className="flex flex-wrap items-center gap-1.5">
          <EtapaNaLista demanda={demanda} />
          <ClassificacaoNaLista demanda={demanda} />
          <OrigemNaLista demanda={demanda} />
          <SeloDaDemonstracao demanda={demanda} />
          <SeloDoEnvioFalhou demanda={demanda} />
        </span>
      </button>
      <div className="absolute top-3 right-3 flex items-center gap-1.5">
        <button
          type="button"
          onClick={onConversar}
          aria-label={CONVERSAR}
          title="Conversar com quem cuida deste pedido"
          className="w-9 h-9 inline-flex items-center justify-center rounded-xl border border-border bg-white text-primary shadow-sm transition-opacity duration-150 motion-reduce:transition-none hover:bg-primary/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
        >
          <MessageSquare className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onAmpliar}
          aria-label={AMPLIAR}
          title={AMPLIAR_EXPLICADO}
          className="hidden md:inline-flex w-9 h-9 items-center justify-center rounded-xl border border-border bg-white text-primary shadow-sm hover:bg-primary/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

/** Para mim, Minhas e Todas, numa peça só: um dos três está sempre escolhido. */
function RecorteDaLista({ valor, onMudar }: { valor: Filtro | null; onMudar: (filtro: Filtro) => void }) {
  return (
    <div role="group" aria-label="Recorte" className="inline-flex shrink-0 p-1 rounded-xl bg-slate-100">
      {FILTROS.map(({ valor: opcao, rotulo }) => (
        <button
          key={opcao}
          type="button"
          aria-pressed={valor === opcao}
          onClick={() => onMudar(opcao)}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors motion-reduce:transition-none ${
            valor === opcao ? "bg-white text-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
          }`}
        >
          {rotulo}
        </button>
      ))}
    </div>
  );
}

/** O "Só envio falhou" do Desenvolvedor, um interruptor: não é Etapa (issue #1578). */
function InterruptorDoEnvioFalhou({ ligado, onMudar }: { ligado: boolean; onMudar: (ligado: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={ligado}
      onClick={() => onMudar(!ligado)}
      className="inline-flex items-center gap-2 text-xs font-semibold text-text-secondary"
    >
      <span
        aria-hidden="true"
        className={`relative w-9 h-5 rounded-full transition-colors motion-reduce:transition-none ${
          ligado ? "bg-primary" : "bg-slate-300"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform motion-reduce:transition-none ${
            ligado ? "translate-x-4" : ""
          }`}
        />
      </span>
      {SO_ENVIO_FALHOU}
    </button>
  );
}

/**
 * O aviso do Envio falhou no alto da conversa aberta, com o Reenviar (issue
 * #1535). O motivo técnico só vem do servidor para o Desenvolvedor.
 */
function AvisoDoEnvioFalhou({
  demanda,
  token,
  onReenviado,
}: {
  demanda: Demanda;
  token: string | null;
  onReenviado: (demandaId: string) => void;
}) {
  const [reenviando, setReenviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function reenviar() {
    if (!token) return;
    setReenviando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDoReenviar(demanda.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onReenviado(demanda.id);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao reenviar o card", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setReenviando(false);
    }
  }

  return (
    <section
      role="region"
      aria-label={ENVIO_FALHOU}
      className="w-full rounded-2xl border border-red-200 bg-red-50 p-4 space-y-2 text-sm text-red-800"
    >
      <p className="font-semibold">{ENVIO_FALHOU}</p>
      <p>{ENVIO_FALHOU_EXPLICADO}</p>
      {demanda.envio_motivo && <p className="normal-case font-mono text-xs">{demanda.envio_motivo}</p>}
      {erro && <p role="alert">{erro}</p>}
      <button
        type="button"
        onClick={reenviar}
        disabled={reenviando}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60"
      >
        {reenviando && <Loader2 className="w-4 h-4 animate-spin" />}
        {REENVIAR}
      </button>
    </section>
  );
}

/**
 * O aviso da designação falhada no alto da conversa aberta, com o Designar de
 * novo (issue #1536). Só o Desenvolvedor o recebe do servidor.
 */
function AvisoDaDesignacaoFalhou({
  demanda,
  token,
  onDesignado,
}: {
  demanda: Demanda;
  token: string | null;
  onDesignado: (demandaId: string) => void;
}) {
  const [designando, setDesignando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function designarDeNovo() {
    if (!token) return;
    setDesignando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDoDesignarDeNovo(demanda.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onDesignado(demanda.id);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao designar de novo", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setDesignando(false);
    }
  }

  return (
    <section
      role="region"
      aria-label={DESIGNACAO_FALHOU}
      className="w-full rounded-2xl border border-amber-200 bg-amber-50 p-4 space-y-2 text-sm text-amber-900"
    >
      <p className="font-semibold">{DESIGNACAO_FALHOU}</p>
      <p>{DESIGNACAO_FALHOU_EXPLICADO}</p>
      {demanda.envio_motivo && <p className="normal-case font-mono text-xs">{demanda.envio_motivo}</p>}
      {erro && <p role="alert">{erro}</p>}
      <button
        type="button"
        onClick={designarDeNovo}
        disabled={designando}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60"
      >
        {designando && <Loader2 className="w-4 h-4 animate-spin" />}
        {DESIGNAR_DE_NOVO}
      </button>
    </section>
  );
}

/**
 * O "Apagar" da Demanda (issue #1549, ADR 0084, decisão 2). Só aparece com o
 * `pode_apagar` do servidor, e pede confirmação antes. A recusa do servidor
 * (o GitHub que não fechou o card, a Etapa que andou) aparece embaixo do botão.
 */
function ApagarADemanda({
  demanda,
  token,
  onApagada,
}: {
  demanda: Demanda;
  token: string | null;
  onApagada: () => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function apagar() {
    if (!token) return;
    setErro(null);
    try {
      const resposta = await fetch(urlDaConversa(demanda.id), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onApagada();
    } catch (e) {
      console.error("[admin/tecnologia] falha ao apagar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => setConfirmando(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-red-200 text-red-700 text-xs font-semibold hover:bg-red-50"
      >
        <Trash2 className="w-3.5 h-3.5" />
        {APAGAR}
      </button>
      {erro && (
        <p role="alert" className="text-sm text-red-700">
          {erro}
        </p>
      )}
      <ConfirmDialog
        open={confirmando}
        onClose={() => setConfirmando(false)}
        onConfirm={apagar}
        title={APAGAR_TITULO}
        description={demanda.tem_vinculo ? APAGAR_O_CARD_EXPLICADO : APAGAR_A_CONVERSA_EXPLICADO}
        confirmLabel={APAGAR}
        confirmVariant="danger"
      />
    </div>
  );
}

/**
 * O "Revisar com o código de hoje" (issue #1557, ADR 0084, decisão 3). O
 * clique pede ao servidor a estimativa, que não chama a IA, e abre a
 * confirmação com a faixa em dólar. Só o Revisar do diálogo começa a revisão
 * (ADR 0082). A recusa do servidor aparece embaixo do botão.
 */
function RevisarComOCodigoDeHoje({
  demanda,
  token,
  onRevisada,
}: {
  demanda: Demanda;
  token: string | null;
  onRevisada: (demandaId: string) => void;
}) {
  const [estimativa, setEstimativa] = useState<EstimativaDaRevisao | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function estimar() {
    if (!token) return;
    setCalculando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDaRevisao(demanda.id), { headers: { Authorization: `Bearer ${token}` } });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      setEstimativa((await resposta.json()) as EstimativaDaRevisao);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao estimar a revisão", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setCalculando(false);
    }
  }

  async function revisar() {
    if (!token) return;
    setErro(null);
    try {
      const resposta = await fetch(urlDaRevisao(demanda.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ confirmado: true }),
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onRevisada(demanda.id);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao começar a revisão", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={estimar}
        disabled={calculando}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-primary/30 text-primary text-xs font-semibold hover:bg-primary/5 disabled:opacity-60"
      >
        {calculando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        {REVISAR_COM_O_CODIGO_DE_HOJE}
      </button>
      {erro && (
        <p role="alert" className="text-sm text-red-700">
          {erro}
        </p>
      )}
      <ConfirmDialog
        open={estimativa !== null}
        onClose={() => setEstimativa(null)}
        onConfirm={revisar}
        title={REVISAR_TITULO}
        description={
          estimativa
            ? `${textoDaEstimativa(estimativa)} A IA lê o que o sistema já faz hoje e pergunta só o que falta. Cada resposta depois do retrato custa como as do planejamento.`
            : undefined
        }
        confirmLabel={REVISAR}
      />
    </div>
  );
}

/** Os Anexos da Demanda, que só o Desenvolvedor recebe do servidor. */
function AnexosDaDemanda({ anexos }: { anexos: AnexoDaDemanda[] }) {
  const comLink = anexos.filter((anexo) => anexo.url);
  if (comLink.length === 0) return null;
  return (
    <div className="border-t border-slate-100 pt-4 space-y-1">
      <h3 className="text-xs font-semibold text-text-secondary">Anexos</h3>
      <ul className="space-y-1 text-sm">
        {comLink.map((anexo, i) => (
          <li key={i}>
            <a
              href={anexo.url ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="normal-case text-primary underline"
            >
              {anexo.nome}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A conversa só para leitura: a que já virou card, ou a de outro autor que o
 * Desenvolvedor abriu (ADR 0083), com a Etapa e o Documento do card. O card
 * da Vitta não tem conversa com o agente (issue #1554): nem a pede.
 */
function Acompanhamento({ demanda, token }: { demanda: Demanda; token: string | null }) {
  const [falas, setFalas] = useState<FalaDoChat[]>([]);
  const [anexos, setAnexos] = useState<AnexoDaDemanda[]>([]);

  // A conversa é complemento: sem ela (a melhoria planejada, ou a rede fora),
  // o Documento do card continua à vista.
  const semChat = demanda.origem === "vitta";
  useEffect(() => {
    if (!token || semChat) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(urlDaConversa(demanda.id), { headers: { Authorization: `Bearer ${token}` } });
        if (!resposta.ok) return;
        const corpo: unknown = await resposta.json();
        if (viva && conversaValida(corpo)) {
          setFalas(corpo.mensagens);
          setAnexos(Array.isArray(corpo.anexos_da_demanda) ? corpo.anexos_da_demanda : []);
        }
      } catch (e) {
        console.error("[admin/tecnologia] falha ao abrir a conversa", e);
      }
    })();
    return () => {
      viva = false;
    };
  }, [demanda.id, token, semChat]);

  return (
    <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <h2 className="normal-case text-base font-bold text-slate-900">{demanda.titulo}</h2>
        <SeloDeEtapa demanda={demanda} />
        <OrigemNaLista demanda={demanda} />
        {demanda.autor && <span className="normal-case text-text-secondary">{demanda.autor}</span>}
      </div>
      <DocumentoDoCard demanda={demanda} />
      {falas.length > 0 && (
        <div role="log" className="space-y-3 border-t border-slate-100 pt-4">
          {falas.map((fala, i) => (
            <Fala key={i} fala={fala} />
          ))}
        </div>
      )}
      <AnexosDaDemanda anexos={anexos} />
    </section>
  );
}

export function ConversasDaTecnologia({
  token,
  demandaInicial = null,
}: {
  token: string | null;
  /** A Demanda que o aviso do sino pediu para abrir. */
  demandaInicial?: string | null;
}) {
  const [demandas, setDemandas] = useState<Demanda[] | null>(null);
  const [erroDaLista, setErroDaLista] = useState<string | null>(null);
  /** A Demanda clicada; `null` é a conversa nova. */
  const [aberta, setAberta] = useState<Demanda | null>(null);
  /** A que a lista destaca: a clicada, ou a que acabou de nascer no chat. */
  const [destacada, setDestacada] = useState<string | null>(null);
  /** Muda a cada clique, para o chat recomeçar do estado da conversa escolhida. */
  const [chave, setChave] = useState(0);
  const [naTela, setNaTela] = useState<"lista" | "conversa">("lista");
  /** A Demanda abriu pelo "Conversar" do card: a caixa da Conversa da Demanda vem em foco. */
  const [focarConversa, setFocarConversa] = useState(false);
  /** O pedido aberto na largura toda, com a lista recolhida: só o Ampliar liga (issue #1593). */
  const [ampliada, setAmpliada] = useState(false);
  const [desenvolvedor, setDesenvolvedor] = useState(false);
  /** Nulo até o servidor dizer quem está logado: o Desenvolvedor abre em Para mim. */
  const [filtro, setFiltro] = useState<Filtro | null>(null);
  const [textoDaBusca, setTextoDaBusca] = useState("");
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState<Classificacao | null>(null);
  const [etapa, setEtapa] = useState<EtapaDemanda | null>(null);
  const [origem, setOrigem] = useState<Origem | null>(null);
  const [responsavel, setResponsavel] = useState<string | null>(null);
  const [envioFalhou, setEnvioFalhou] = useState(false);
  const [desenvolvedores, setDesenvolvedores] = useState<Desenvolvedor[]>([]);
  /** O último pedido da lista: a resposta de um pedido mais velho não sobrescreve a do novo. */
  const ultimoPedido = useRef(0);
  /** A Demanda do sino que já foi aberta: abre uma vez, e não a cada recarga da lista. */
  const abertaPeloSino = useRef<string | null>(null);

  // Sem resposta, a tela fica como a do diretor: o filtro só aparece com o
  // sim do servidor.
  useEffect(() => {
    if (!token) return;
    let viva = true;
    (async () => {
      let sim = false;
      try {
        const resposta = await fetch(URL_QUEM_SOU, { headers: { Authorization: `Bearer ${token}` } });
        if (resposta.ok) {
          const corpo: unknown = await resposta.json();
          sim = (corpo as { desenvolvedor?: unknown })?.desenvolvedor === true;
        }
      } catch (e) {
        console.error("[admin/tecnologia] falha ao saber quem está logado", e);
      }
      if (!viva) return;
      setDesenvolvedor(sim);
      setFiltro(sim ? (demandaInicial ? "todas" : "para_mim") : "minhas");
    })();
    return () => {
      viva = false;
    };
  }, [token, demandaInicial]);

  // Os nomes do chip Responsável, só para o Desenvolvedor.
  useEffect(() => {
    if (!token || !desenvolvedor) return;
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
  }, [token, desenvolvedor]);

  useEffect(() => {
    const espera = setTimeout(() => setBusca(textoDaBusca.trim()), ESPERA_DA_BUSCA_MS);
    return () => clearTimeout(espera);
  }, [textoDaBusca]);

  /** Relê a lista e devolve o que veio; nulo quando não deu. */
  const carregar = useCallback(async (): Promise<Demanda[] | null> => {
    if (!token || filtro === null) return null;
    const url = urlDaLista({ recorte: filtro, busca, tipo, etapa, origem, responsavel, envioFalhou });
    const pedido = ++ultimoPedido.current;
    try {
      const resposta = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (pedido !== ultimoPedido.current) return null;
      if (!resposta.ok) {
        setErroDaLista(LISTA_FALHOU);
        return null;
      }
      const corpo: unknown = await resposta.json();
      if (pedido !== ultimoPedido.current) return null;
      if (!Array.isArray(corpo)) {
        setErroDaLista(LISTA_FALHOU);
        return null;
      }
      const lidas = corpo.filter(itemValido);
      setDemandas(lidas);
      setErroDaLista(null);
      return lidas;
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as conversas", e);
      setErroDaLista(FALHA_DE_CONEXAO);
      return null;
    }
  }, [token, filtro, busca, tipo, etapa, origem, responsavel, envioFalhou]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const aoMudar = useCallback(
    (demandaId: string) => {
      setDestacada(demandaId);
      carregar();
    },
    [carregar],
  );

  const abrir = useCallback((demanda: Demanda | null, conversar = false, ampliar = false) => {
    setAberta(demanda);
    setDestacada(demanda?.id ?? null);
    setFocarConversa(conversar);
    setAmpliada(ampliar);
    setChave((atual) => atual + 1);
    setNaTela("conversa");
  }, []);

  const filtroAtivo = Boolean(textoDaBusca.trim() || tipo || etapa || origem || responsavel || envioFalhou);

  /** Volta a barra ao padrão. O recorte fica: ele é a vista do Desenvolvedor, não um filtro. */
  function limparFiltros() {
    setTextoDaBusca("");
    setBusca("");
    setTipo(null);
    setEtapa(null);
    setOrigem(null);
    setResponsavel(null);
    setEnvioFalhou(false);
  }

  /** O card nasceu pelo Reenviar: a lista relê e a Demanda abre como está agora. */
  async function aoReenviar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, envio_falhou: false, envio_motivo: null, tem_vinculo: true } : null));
  }

  /** A Demanda foi apagada: some da lista, e a tela volta à lista com a conversa nova pronta. */
  function aoApagar() {
    setAberta(null);
    setDestacada(null);
    setChave((atual) => atual + 1);
    setNaTela("lista");
    carregar();
  }

  /** A revisão começou: a lista relê e o card abre na conversa, para responder. */
  async function aoRevisar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, pode_revisar: false, em_revisao: true } : null));
  }

  /** A designação pegou: a lista relê e a Demanda abre como está agora. */
  async function aoDesignar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, designacao_falhou: false, envio_motivo: null } : null));
  }

  useEffect(() => {
    if (!demandaInicial || abertaPeloSino.current === demandaInicial || !demandas) return;
    const pedida = demandas.find((d) => d.id === demandaInicial);
    if (!pedida) return;
    abertaPeloSino.current = demandaInicial;
    abrir(pedida);
  }, [demandaInicial, demandas, abrir]);

  /** A lista recolhe na tela larga só com o pedido ampliado (issue #1593, que reverteu a #1551). */
  const recolhida = naTela === "conversa" && aberta !== null && ampliada;

  return (
    <div className="space-y-4">
      <section
        role="region"
        aria-label="Filtros da lista"
        className={`${naTela === "lista" ? "" : "hidden"} ${recolhida ? "md:hidden" : "md:block"} rounded-2xl border border-border bg-white shadow-sm p-4 space-y-4`}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 min-w-0">
            <Search aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="search"
              aria-label="Buscar pelo título"
              placeholder="Buscar pelo título"
              value={textoDaBusca}
              onChange={(e) => setTextoDaBusca(e.target.value)}
              className="w-full min-h-[38px] pl-9 pr-3 py-2 rounded-lg border border-slate-200 text-sm normal-case bg-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          {desenvolvedor && <RecorteDaLista valor={filtro} onMudar={setFiltro} />}
          <button
            type="button"
            onClick={() => abrir(null)}
            className="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2 min-h-[38px] rounded-xl bg-primary text-white text-sm font-semibold transition-opacity hover:opacity-90"
          >
            <Plus className="w-4 h-4" />
            {NOVA_CONVERSA}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Select
            label="Tipo"
            value={tipo ?? ""}
            options={OPCOES_DE_TIPO}
            onChange={(valor) => setTipo((valor || null) as Classificacao | null)}
          />
          <Select
            label="Etapa"
            value={etapa ?? ""}
            options={OPCOES_DE_ETAPA}
            onChange={(valor) => setEtapa((valor || null) as EtapaDemanda | null)}
          />
          <Select
            label="Origem"
            value={origem ?? ""}
            options={OPCOES_DE_ORIGEM}
            onChange={(valor) => setOrigem((valor || null) as Origem | null)}
          />
          {desenvolvedor && desenvolvedores.length > 0 && (
            <Select
              label="Responsável"
              value={responsavel ?? ""}
              options={[{ value: "", label: "Todos" }, ...desenvolvedores.map((d) => ({ value: d.id, label: d.nome }))]}
              onChange={(valor) => setResponsavel(valor || null)}
            />
          )}
        </div>
        {(desenvolvedor || filtroAtivo) && (
          <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3">
            {desenvolvedor && <InterruptorDoEnvioFalhou ligado={envioFalhou} onMudar={setEnvioFalhou} />}
            {filtroAtivo && (
              <button
                type="button"
                onClick={limparFiltros}
                className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
              >
                <X aria-hidden="true" className="w-3.5 h-3.5" />
                {LIMPAR_FILTROS}
              </button>
            )}
          </div>
        )}
      </section>

      <div
        className={`md:grid ${recolhida ? "md:grid-cols-1" : "md:grid-cols-[24rem_minmax(0,1fr)]"} md:gap-6 md:items-start`}
      >
        <div className={`${naTela === "lista" ? "" : "hidden"} ${recolhida ? "md:hidden" : "md:block"}`}>
          <nav aria-label="Suas conversas" className="md:max-h-[calc(100vh-18rem)] md:overflow-y-auto p-1 -m-1">
            {erroDaLista && (
              <p role="alert" className="px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
                {erroDaLista}
              </p>
            )}
            {demandas === null && !erroDaLista && (
              <p role="status" className="flex items-center gap-2 px-1 text-xs text-text-secondary">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Carregando as conversas...
              </p>
            )}
            {demandas !== null && demandas.length === 0 && (
              <p className="px-1 text-sm text-text-secondary">{LISTA_VAZIA}</p>
            )}
            {demandas !== null && demandas.length > 0 && (
              <ul className="space-y-3">
                {demandas.map((demanda) => (
                  <li key={demanda.id}>
                    <CardDaConversa
                      demanda={demanda}
                      destacada={destacada === demanda.id}
                      onAbrir={() => abrir(demanda)}
                      onConversar={() => abrir(demanda, true)}
                      onAmpliar={() => abrir(demanda, false, true)}
                    />
                  </li>
                ))}
              </ul>
            )}
          </nav>
        </div>

        <div
          role="region"
          aria-label="Conversa aberta"
          className={`${naTela === "conversa" ? "" : "hidden"} md:block min-w-0 space-y-3`}
        >
          <button
            type="button"
            onClick={() => setNaTela("lista")}
            className={`${recolhida ? "" : "md:hidden"} inline-flex items-center gap-1.5 text-sm font-semibold text-primary`}
          >
            <ArrowLeft className="w-4 h-4" />
            {VOLTAR_PARA_A_LISTA}
          </button>
          {aberta && !recolhida && (
            <button
              type="button"
              onClick={() => {
                setAmpliada(true);
                setNaTela("conversa");
              }}
              title={AMPLIAR_EXPLICADO}
              className="hidden md:inline-flex items-center gap-1.5 text-sm font-semibold text-primary"
            >
              <Maximize2 className="w-4 h-4" />
              {AMPLIAR}
            </button>
          )}
          {aberta?.pode_apagar && (
            <ApagarADemanda key={`apagar-${chave}`} demanda={aberta} token={token} onApagada={aoApagar} />
          )}
          {aberta?.pode_revisar && (
            <RevisarComOCodigoDeHoje key={`revisar-${chave}`} demanda={aberta} token={token} onRevisada={aoRevisar} />
          )}
          {aberta?.envio_falhou && (
            <AvisoDoEnvioFalhou key={`envio-${chave}`} demanda={aberta} token={token} onReenviado={aoReenviar} />
          )}
          {desenvolvedor && aberta?.designacao_falhou && (
            <AvisoDaDesignacaoFalhou
              key={`designacao-${chave}`}
              demanda={aberta}
              token={token}
              onDesignado={aoDesignar}
            />
          )}
          {/* Ao lado da lista, a Conversa da Demanda desce para baixo do documento;
              ampliado, ela ganha a coluna à direita (issue #1593). */}
          <div
            className={
              !aberta
                ? ""
                : recolhida
                  ? "space-y-3 xl:space-y-0 xl:grid xl:grid-cols-[minmax(0,1fr)_24rem] xl:gap-6 xl:items-start"
                  : "space-y-3"
            }
          >
            <div className="min-w-0">
              {(aberta?.tem_vinculo || aberta?.minha === false) && !aberta?.em_revisao ? (
                <Acompanhamento key={chave} demanda={aberta} token={token} />
              ) : (
                <ChatDaTecnologia key={chave} token={token} demandaId={aberta?.id ?? null} onMudou={aoMudar} />
              )}
            </div>
            {aberta && (
              <div className={recolhida ? "xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto" : ""}>
                <ConversaDaDemanda
                  key={`conversa-${chave}`}
                  demandaId={aberta.id}
                  token={token}
                  focar={focarConversa}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
