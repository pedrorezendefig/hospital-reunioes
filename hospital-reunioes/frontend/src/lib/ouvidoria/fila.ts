/**
 * Fila do painel de ouvidoria por estado (issue #320, ADR 0034).
 *
 * A ordem é a do trabalho do ouvidor: primeiro o que espera ação dele,
 * depois o que está com a área, por último o que já fechou.
 */

import type { TipoManifestacao } from "./taxonomia";
import type { StatusManifestacao } from "./prazo";

/**
 * O índice da manifestação: o que a fila lista para qualquer perfil com acesso
 * ao painel. Relato, nome e contato só existem no Dossiê, atrás do Perfil da
 * Ouvidoria (ADR 0034).
 *
 * Mora aqui, e não na tela, porque a lista da fila e a linha que a desenha são
 * arquivos diferentes desde a issue #495: o contrato da resposta precisa de um
 * dono só, ou as duas pontas divergem no primeiro campo novo.
 */
export interface ManifestacaoIndice {
  id: string;
  numero: number;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusManifestacao;
  // Lista fechada (issue #372). `null` é o caso ainda não classificado, que
  // chega pelo canal aberto e pelo canal da Ana.
  tipo_manifestacao: TipoManifestacao | null;
  // A marca de sigilo do caso (issue #372). Para quem está fora da Ouvidoria é
  // sempre falso: a linha sigilosa nem chega até aqui.
  sigilo_reforcado: boolean;
  categoria: string;
  setor: string;
  resumo: string;
  conversa_id: string;
  // Motor de prazos (issue #322): o vencimento e o rótulo vêm calculados do
  // servidor, em calendário útil.
  gravidade: string | null;
  prazo_area_em: string | null;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  minutos_uteis_restantes: number | null;
  // Movimentação mais nova que a última vez que a Ouvidoria abriu o caso
  // (issue #484, RN-66). Quem está fora da Ouvidoria recebe sempre falso: o
  // ponto diz "a Ouvidoria ainda não viu", e não significa nada para os
  // outros perfis do painel.
  tem_novidade: boolean;
}

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

/**
 * A cor do selo de cada estado. Vive aqui, junto do rótulo e da ordem, porque
 * as duas telas que desenham o selo (a lista do ouvidor e o painel em tempo
 * real) tinham o mesmo mapa copiado, e a cópia é o que deixa uma delas para
 * trás quando um estado novo nasce.
 */
const CLASSE_POR_STATUS: Record<StatusManifestacao, string> = {
  novo: "bg-violet-100 text-violet-700",
  em_classificacao: "bg-sky-100 text-sky-700",
  aguardando_area: "bg-amber-100 text-amber-700",
  // Cinza-azulado de coisa parada: o caso não está atrasado nem andando, está
  // esperando o manifestante (issue #335).
  aguardando_manifestante: "bg-slate-200 text-slate-600",
  respondido: "bg-emerald-100 text-emerald-700",
  encerrado: "bg-slate-100 text-slate-500",
};

/**
 * A cor do selo, tolerante a estado desconhecido. As telas interpolam o valor
 * direto no `className`, e o mapa indexado sem guarda escrevia a string
 * "undefined" ali: o selo do estado novo saía sem fundo nem cor de texto
 * (issue #375, item 15).
 */
export function classeDoStatus(status: StatusManifestacao): string {
  return CLASSE_POR_STATUS[status] ?? "bg-slate-100 text-slate-500";
}

/** O título do bloco de destaque, um só lugar para a tela e para o contador. */
export const TITULO_AGUARDANDO_ENCERRAMENTO = "Aguardando seu encerramento";

/**
 * O trabalho do dia do ouvidor (issue #486, RN-67): o caso que a área já
 * respondeu e que ele ainda não olhou.
 *
 * Respondido sem novidade fica de fora porque ele já passou por ali e decidiu
 * não encerrar ainda; novidade em caso que segue com a área não é encerramento
 * nenhum. O par dos dois sinais é o que faz o bloco esvaziar sozinho conforme o
 * dia anda.
 *
 * Filtra sem consumir: o caso destacado continua no grupo do estado dele, e o
 * bloco é destaque, não filtro novo. Mover a linha para cá faria o caso trocar
 * de lugar na tela assim que fosse aberto.
 */
export function aguardandoSeuEncerramento<
  T extends { status: StatusManifestacao; tem_novidade: boolean },
>(manifestacoes: T[]): T[] {
  return manifestacoes.filter((m) => m.status === "respondido" && m.tem_novidade);
}
