/**
 * O chat da aba Tecnologia, do lado da tela (issue #1381, PRD #1380, ADR 0077).
 *
 * A conversa vive no servidor, guardada na Demanda que nasce no primeiro
 * turno: a tela manda a fala e mostra a conversa que volta. Quem decide o
 * roteiro, o teto de perguntas e o resumo é o backend.
 */

import { BASE_TECNOLOGIA } from "./demandas";

export const URL_DO_CHAT_DA_ABA = `${BASE_TECNOLOGIA}/chat`;

export function urlDaConversa(demandaId: string): string {
  return `${URL_DO_CHAT_DA_ABA}/${encodeURIComponent(demandaId)}`;
}

export function urlDoNaoBateu(demandaId: string): string {
  return `${urlDaConversa(demandaId)}/nao-bateu`;
}

export function urlDoCriarOCard(demandaId: string): string {
  return `${urlDaConversa(demandaId)}/criar-card`;
}

/** O "Fechar e resumir" da melhoria (issue #1383). */
export function urlDoResumoDaMelhoria(demandaId: string): string {
  return `${urlDaConversa(demandaId)}/resumo`;
}

export type LetraDaOpcao = "A" | "B";

/**
 * `recomendada` só vem na pergunta do planejamento da melhoria: as `opcoes`
 * chegam na ordem A e B, e o clique manda a letra.
 */
export type FalaDoChat = {
  autor: "ia" | "diretor";
  texto: string;
  fonte: string | null;
  opcoes: string[];
  recomendada?: LetraDaOpcao | null;
  nao_bateu: boolean;
  /** Os documentos que a fala do diretor trouxe (issue #1520): o nome e o tamanho, nunca o texto. */
  documentos?: DocumentoDaFala[];
};

export type DocumentoDaFala = { nome: string; tamanho_bytes: number };

/** Um Anexo da Demanda, como o Desenvolvedor o abre: a URL assinada vale por pouco tempo. */
export type AnexoDaDemanda = { nome: string; tipo: string; url: string | null };

export const LETRAS: LetraDaOpcao[] = ["A", "B"];

/** O resumo do planejamento da melhoria: as decisões e o que ficou em aberto. */
export type ResumoDaMelhoria = {
  decisoes: { pergunta: string; escolha: string; porque: string }[];
  em_aberto: string[];
};

export type ResumoDoBug = {
  titulo: string;
  onde: string;
  o_que_aconteceu: string;
  o_que_esperava: string;
  como_repetir: string;
  criterios: string[];
};

/**
 * O modelo da chamada mais recente, no nome de exibição ("Opus 5.5"), e o que
 * a conversa já custou em dólar (issue #1439, ADR 0079, decisão 6).
 * `custo_usd` nulo é custo não medido: o modelo estava sem preço.
 */
export type CustoDaConversa = {
  modelo: string;
  custo_usd: number | null;
};

const DOLAR = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "Opus 5.5 · US$ 1,84 até agora", ou "Opus 5.5 · custo não medido". */
export function textoDoCusto(custo: CustoDaConversa): string {
  if (custo.custo_usd === null) return `${custo.modelo} · custo não medido`;
  return `${custo.modelo} · US$ ${DOLAR.format(custo.custo_usd)} até agora`;
}

/**
 * `estado`: `em_andamento`, `encerrado` (as perguntas da melhoria acabaram e o
 * resumo vem a seguir), `resumido` (o resumo esperando o clique) e `enviado`
 * (o card nasceu). `planejamento` é a melhoria confirmada, que segue no próprio
 * chat pelo Planejamento da Demanda (issue #1383), com o resumo em
 * `resumo_da_melhoria`. `custo` é nulo enquanto não houve chamada à IA.
 */
export type ConversaDoChat = {
  demanda_id: string;
  estado: string | null;
  mensagens: FalaDoChat[];
  resumo: ResumoDoBug | null;
  resumo_da_melhoria?: ResumoDaMelhoria | null;
  anexos: number;
  planejamento: boolean;
  aviso_dos_anexos: string | null;
  custo?: CustoDaConversa | null;
  /** Os Anexos, só para o Desenvolvedor (ADR 0083, decisão 3); vazio para o diretor. */
  anexos_da_demanda?: AnexoDaDemanda[];
};

/**
 * A melhoria espera a IA falar: a conversa acabou de passar ao planejamento,
 * ou o "Não bateu" entrou, e ainda não há pergunta esperando resposta. A tela
 * pede o turno seguinte sozinha.
 */
export function esperaAPergunta(conversa: ConversaDoChat): boolean {
  if (!conversa.planejamento || conversa.estado !== "em_andamento") return false;
  const ultima = conversa.mensagens[conversa.mensagens.length - 1];
  return !(ultima?.autor === "ia" && ultima.recomendada);
}

function textoOuNulo(valor: unknown): boolean {
  return valor === undefined || valor === null || typeof valor === "string";
}

function listaDeTextos(valor: unknown): boolean {
  return Array.isArray(valor) && valor.every((t) => typeof t === "string");
}

function falaValida(item: unknown): boolean {
  if (typeof item !== "object" || item === null) return false;
  const f = item as Record<string, unknown>;
  return (
    (f.autor === "ia" || f.autor === "diretor") &&
    typeof f.texto === "string" &&
    textoOuNulo(f.fonte) &&
    listaDeTextos(f.opcoes) &&
    (f.recomendada === undefined || f.recomendada === null || f.recomendada === "A" || f.recomendada === "B") &&
    (f.documentos === undefined || (Array.isArray(f.documentos) && f.documentos.every(documentoValido)))
  );
}

function documentoValido(item: unknown): boolean {
  if (typeof item !== "object" || item === null) return false;
  const d = item as Record<string, unknown>;
  return typeof d.nome === "string" && typeof d.tamanho_bytes === "number";
}

function resumoDaMelhoriaValido(valor: unknown): boolean {
  if (valor === undefined || valor === null) return true;
  if (typeof valor !== "object") return false;
  const r = valor as Record<string, unknown>;
  return (
    Array.isArray(r.decisoes) &&
    r.decisoes.every((d) => {
      if (typeof d !== "object" || d === null) return false;
      const c = d as Record<string, unknown>;
      return typeof c.pergunta === "string" && typeof c.escolha === "string" && typeof c.porque === "string";
    }) &&
    listaDeTextos(r.em_aberto)
  );
}

function resumoValido(valor: unknown): boolean {
  if (valor === undefined || valor === null) return true;
  if (typeof valor !== "object") return false;
  const r = valor as Record<string, unknown>;
  return (
    ["titulo", "onde", "o_que_aconteceu", "o_que_esperava", "como_repetir"].every((c) => typeof r[c] === "string") &&
    listaDeTextos(r.criterios)
  );
}

function custoValido(valor: unknown): boolean {
  if (valor === undefined || valor === null) return true;
  if (typeof valor !== "object") return false;
  const c = valor as Record<string, unknown>;
  return typeof c.modelo === "string" && (c.custo_usd === null || typeof c.custo_usd === "number");
}

/** O corpo serve para a tela usar? Mesma fronteira dos outros corpos da aba. */
export function conversaValida(corpo: unknown): corpo is ConversaDoChat {
  if (typeof corpo !== "object" || corpo === null) return false;
  const c = corpo as Record<string, unknown>;
  return (
    typeof c.demanda_id === "string" &&
    textoOuNulo(c.estado) &&
    Array.isArray(c.mensagens) &&
    c.mensagens.every(falaValida) &&
    resumoValido(c.resumo) &&
    resumoDaMelhoriaValido(c.resumo_da_melhoria) &&
    custoValido(c.custo)
  );
}

/** A frase do resumo sobre os prints guardados. */
export function frasesDosPrints(quantos: number): string {
  if (quantos <= 0) return "Nenhum print";
  return quantos === 1 ? "1 imagem guardada no aplicativo" : `${quantos} imagens guardadas no aplicativo`;
}
