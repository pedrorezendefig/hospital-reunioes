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

export type ChaveDeAcao = "validar" | "cobrar" | "encerrar" | "arquivar" | "desarquivar" | "abrir";

export const ROTULO_ACAO: Record<ChaveDeAcao, string> = {
  validar: "Validar e acionar",
  cobrar: "Cobrar",
  encerrar: "Encerrar",
  // O vocabulário do Arquivo (issue #592, ADR 0047, verbete do CONTEXT.md).
  // Nunca "excluir" nem "deletar": arquivar esconde da lista e tem volta, e um
  // verbo que promete sumiço faria o ouvidor hesitar no clique certo.
  arquivar: "Arquivar",
  desarquivar: "Desarquivar",
  abrir: "Abrir manifestação",
};

/**
 * Só caso encerrado arquiva (ADR 0047, decisão 2). Caso em andamento tem prazo
 * correndo e setor esperando, e escondê-lo da lista é esconder atraso.
 *
 * Quem recusa de verdade é o servidor, com 409. Aqui só não se oferece o
 * caminho que terminaria em recusa, como no resto desta tela.
 */
export function podeArquivar(status: StatusManifestacao): boolean {
  return status === "encerrado";
}

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
  { chave: "arquivar", cabe: podeArquivar },
  { chave: "abrir", cabe: () => true },
];

/**
 * O que a lista dos arquivados oferece, na ordem em que ela oferece: a
 * PRIMEIRA é a ação da linha e o resto vai para o menu (issue #592).
 *
 * Não depende do estado do caso: desarquivar não tem pré-condição nenhuma, e
 * nenhuma das outras ações faz sentido sobre um caso que o ouvidor guardou.
 * Uma lista só, e não uma lista mais uma primária escrita à parte: com as
 * duas, mudar a ordem aqui deixaria de mudar o botão da linha.
 */
const ACOES_NO_ARQUIVO: readonly [ChaveDeAcao, ...ChaveDeAcao[]] = ["desarquivar", "abrir"];

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
  // Desde a issue #592: o próximo passo do caso que já acabou é sair da vista.
  // Antes ele caía em "abrir", que não é passo nenhum, e era isso que fazia o
  // grupo Encerrado crescer sem parar.
  encerrado: "arquivar",
};

function acoesPossiveis(status: StatusManifestacao, arquivados: boolean): ChaveDeAcao[] {
  if (arquivados) return [...ACOES_NO_ARQUIVO];
  return CABIMENTO.filter(({ cabe }) => cabe(status)).map(({ chave }) => chave);
}

/**
 * A ação que fica à direita da linha, sempre visível.
 *
 * `arquivados` é o modo da lista, e não um estado do caso (issue #592): a
 * mesma linha oferece Arquivar na lista de trabalho e Desarquivar na lista do
 * arquivo. Ele entra por parâmetro, e não por um campo do caso, porque quem
 * sabe qual das duas listas está na tela é a tela que ligou o filtro.
 */
export function acaoPrimariaDoStatus(status: StatusManifestacao, arquivados = false): ChaveDeAcao {
  if (arquivados) return ACOES_NO_ARQUIVO[0];
  return PRIMARIA_POR_STATUS[status] ?? "abrir";
}

/** O que sobra, na mesma ordem, dentro do menu de ações secundárias. */
export function acoesSecundariasDoStatus(status: StatusManifestacao, arquivados = false): ChaveDeAcao[] {
  const primaria = acaoPrimariaDoStatus(status, arquivados);
  return acoesPossiveis(status, arquivados).filter((chave) => chave !== primaria);
}
