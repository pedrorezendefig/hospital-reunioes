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

export type FalaDoChat = {
  autor: "ia" | "diretor";
  texto: string;
  fonte: string | null;
  opcoes: string[];
  nao_bateu: boolean;
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
 * `estado`: `em_andamento`, `resumido` (o resumo esperando o clique) e
 * `enviado` (o card nasceu). `planejamento` é a melhoria confirmada, que
 * segue pela tela do Planejamento da Demanda.
 */
export type ConversaDoChat = {
  demanda_id: string;
  estado: string | null;
  mensagens: FalaDoChat[];
  resumo: ResumoDoBug | null;
  anexos: number;
  planejamento: boolean;
  aviso_dos_anexos: string | null;
};

/** O que vai no primeiro POST: o botão da abertura ou o texto livre. */
export type PrimeiroTurno = { escolha: "bug" | "melhoria" } | { texto: string; prints: string[] };

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
    listaDeTextos(f.opcoes)
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

/** O corpo serve para a tela usar? Mesma fronteira dos outros corpos da aba. */
export function conversaValida(corpo: unknown): corpo is ConversaDoChat {
  if (typeof corpo !== "object" || corpo === null) return false;
  const c = corpo as Record<string, unknown>;
  return (
    typeof c.demanda_id === "string" &&
    textoOuNulo(c.estado) &&
    Array.isArray(c.mensagens) &&
    c.mensagens.every(falaValida) &&
    resumoValido(c.resumo)
  );
}

/** A frase do resumo sobre os prints guardados. */
export function frasesDosPrints(quantos: number): string {
  if (quantos <= 0) return "Nenhum print";
  return quantos === 1 ? "1 imagem guardada no aplicativo" : `${quantos} imagens guardadas no aplicativo`;
}
