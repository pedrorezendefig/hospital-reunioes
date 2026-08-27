/**
 * Fila do painel de ouvidoria por estado (issue #320, ADR 0034).
 *
 * A ordem é a do trabalho do ouvidor: primeiro o que espera ação dele,
 * depois o que está com a área, por último o que já fechou.
 */

import type { StatusManifestacao } from "./prazo";

export const ORDEM_DA_FILA: StatusManifestacao[] = [
  "novo",
  "em_classificacao",
  // A pausa fica logo depois do que espera a área: é caso parado esperando o
  // manifestante, e o ouvidor precisa vê-lo para lembrar de tentar contato
  // antes que ele vire abandono (issue #335).
  "aguardando_area",
  "aguardando_manifestante",
  "respondido",
  "encerrado",
];

export const LABEL_STATUS: Record<StatusManifestacao, string> = {
  novo: "Nova",
  em_classificacao: "Em classificação",
  aguardando_area: "Aguardando área",
  aguardando_manifestante: "Aguardando manifestante",
  respondido: "Respondida",
  encerrado: "Encerrada",
};

export interface GrupoDaFila<T> {
  status: StatusManifestacao;
  itens: T[];
}

/**
 * Agrupa na ordem da fila. Estado sem manifestação vira grupo vazio: o painel
 * decide se esconde ou mostra "nenhuma", em vez de sumir a coluna do nada.
 *
 * Estado que esta tela ainda não conhece ganha grupo próprio, no fim (issue
 * #375, item 15). Sem isso o caso sumia em silêncio: backend novo com frontend
 * velho, ou estado criado por migration antes do deploy da tela, e um caso com
 * prazo estourado ficava invisível para o ouvidor. Aparecer num grupo estranho
 * é ruim; sumir é pior, e o painel filtra grupos vazios, então o grupo novo só
 * existe quando há caso nele.
 */
export function agruparPorStatus<T extends { status: StatusManifestacao }>(
  manifestacoes: T[]
): GrupoDaFila<T>[] {
  const conhecidos = ORDEM_DA_FILA.map((status) => ({
    status,
    itens: manifestacoes.filter((m) => m.status === status),
  }));
  const desconhecidos = [
    ...new Set(
      manifestacoes
        .map((m) => m.status)
        .filter((status) => !ORDEM_DA_FILA.includes(status))
    ),
  ].map((status) => ({
    status,
    itens: manifestacoes.filter((m) => m.status === status),
  }));
  return [...conhecidos, ...desconhecidos];
}

/**
 * O nome do estado para a tela. Estado desconhecido devolve o próprio código:
 * a tela lia `LABEL_STATUS[status]` direto, e o cabeçalho do grupo sairia em
 * branco, deixando o ouvidor sem saber o que está olhando (issue #375).
 */
export function rotuloDoStatus(status: StatusManifestacao): string {
  return LABEL_STATUS[status] ?? String(status);
}
