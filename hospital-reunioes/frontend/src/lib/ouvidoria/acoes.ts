/**
 * O que fazer com cada caso da fila (issue #495, PRD #471, RN-74).
 *
 * A linha da fila tem UMA ação sempre visível, e ela é ditada pelo estado do
 * caso: validar e acionar, cobrar, encerrar ou abrir. O resto vai para o menu.
 *
 * A regra vive aqui, e não no JSX, por dois motivos. O primeiro é que a mesma
 * linha é desenhada em dois lugares (o bloco de destaque e os grupos de
 * estado), e regra copiada é regra que diverge. O segundo é que "qual botão o
 * ouvidor vê" é decisão de domínio: com ela espalhada em `if` de render,
 * ninguém consegue afirmar que o caso com a área oferece cobrança em toda tela
 * em que ele aparece.
 */

import type { StatusManifestacao } from "./prazo";
import { podeEncerrar, podeValidar } from "./validacao";

export type ChaveDeAcao = "validar" | "cobrar" | "encerrar" | "abrir";

export const ROTULO_ACAO: Record<ChaveDeAcao, string> = {
  validar: "Validar e acionar",
  cobrar: "Cobrar",
  encerrar: "Encerrar",
  abrir: "Abrir manifestação",
};

/**
 * Cobrar é reenviar o acionamento (ADR 0034, decisão 7). Só o caso que está
 * com a área tem acionamento em aberto para reenviar: antes de validar não há
 * o que reenviar, e depois da resposta a cobrança pediria o que já chegou.
 */
export function podeCobrar(status: StatusManifestacao): boolean {
  return status === "aguardando_area";
}

/**
 * Toda ação que cabe no estado, na ordem em que a tela as oferece. Abrir fecha
 * a lista porque existe sempre, para qualquer estado, inclusive um que esta
 * tela ainda não conheça (issue #375).
 */
const CABIMENTO: { chave: ChaveDeAcao; cabe: (status: StatusManifestacao) => boolean }[] = [
  { chave: "validar", cabe: podeValidar },
  { chave: "cobrar", cabe: podeCobrar },
  { chave: "encerrar", cabe: podeEncerrar },
  { chave: "abrir", cabe: () => true },
];

/**
 * O próximo passo de cada estado, escrito estado a estado (RN-74). É mapa, e
 * não a primeira ação que couber, por causa da pausa: o caso que espera o
 * manifestante também aceita encerramento (por abandono), mas o que o ouvidor
 * tem a fazer ali é tentar contato, e isso acontece dentro do Dossiê. Deixar a
 * precedência decidir sozinha poria "Encerrar" como botão único de um caso que
 * ninguém tentou alcançar ainda.
 *
 * Estado ausente cai em abrir: a linha do estado desconhecido continua
 * acionável em vez de terminar sem saída.
 */
const PRIMARIA_POR_STATUS: Partial<Record<StatusManifestacao, ChaveDeAcao>> = {
  em_classificacao: "validar",
  aguardando_area: "cobrar",
  respondido: "encerrar",
};

function acoesPossiveis(status: StatusManifestacao): ChaveDeAcao[] {
  return CABIMENTO.filter(({ cabe }) => cabe(status)).map(({ chave }) => chave);
}

/** A ação que fica à direita da linha, sempre visível. */
export function acaoPrimariaDoStatus(status: StatusManifestacao): ChaveDeAcao {
  return PRIMARIA_POR_STATUS[status] ?? "abrir";
}

/** O que sobra, na mesma ordem, dentro do menu de ações secundárias. */
export function acoesSecundariasDoStatus(status: StatusManifestacao): ChaveDeAcao[] {
  const primaria = acaoPrimariaDoStatus(status);
  return acoesPossiveis(status).filter((chave) => chave !== primaria);
}
