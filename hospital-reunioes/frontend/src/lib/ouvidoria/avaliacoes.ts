/**
 * A aba Avaliações da Ouvidoria (issue #1626, PRD #1527, ADR 0086 decisões 4 e 8).
 *
 * As notas do QR, os comentários e os números por ponto, turno, dia da semana
 * e semana. Só os dois perfis da Ouvidoria: o comentário não é classificado e
 * pode trazer coisa séria. O enforcement é do servidor (o gate das rotas e o
 * layout da página); aqui a tela só não oferece o caminho que daria 403.
 *
 * As contas (média, porcentagem, turno pela hora do hospital) são todas do
 * servidor. Esta camada formata e monta o endereço da lista.
 */

import { MOTIVOS_DA_AVALIACAO } from "./avaliacao";
import { PERFIS_DO_PAINEL } from "./painel";

export function podeVerAvaliacoes(perfilOuvidoria: string | null | undefined): boolean {
  return PERFIS_DO_PAINEL.includes(String(perfilOuvidoria));
}

export type PeriodoDaAba = "7d" | "30d" | "90d" | "365d" | "tudo";

/** Os períodos do filtro, na ordem do seletor. O padrão é o de 30 dias. */
export const PERIODOS_DA_ABA: { valor: PeriodoDaAba; rotulo: string }[] = [
  { valor: "7d", rotulo: "Últimos 7 dias" },
  { valor: "30d", rotulo: "Últimos 30 dias" },
  { valor: "90d", rotulo: "Últimos 90 dias" },
  { valor: "365d", rotulo: "Últimos 12 meses" },
  { valor: "tudo", rotulo: "Todo o histórico" },
];

export const PERIODO_PADRAO: PeriodoDaAba = "30d";

/** O teto do motivo de arquivar a revisão (o mesmo do servidor). */
export const TAMANHO_DO_MOTIVO = 200;

export interface Indicadores {
  volume: number;
  nota_media: number | null;
  pct_4_e_5: number | null;
  pct_pediu_retorno: number | null;
}

export interface Barra {
  nota_media: number | null;
  volume: number;
}

export interface NumerosDaAba {
  periodo: PeriodoDaAba;
  intervalo: { inicio: string | null; fim: string };
  indicadores: Indicadores;
  por_ponto: (Barra & { ponto_id: string | null; nome: string })[];
  por_turno: (Barra & { turno: string; rotulo: string })[];
  por_dia_da_semana: (Barra & { dia: string; rotulo: string })[];
  por_semana: (Barra & { semana: string })[];
}

export interface AvaliacaoDaLista {
  id: string;
  ponto_id: string | null;
  ponto_nome: string;
  nota: number;
  motivos: string[];
  comentario: string | null;
  criada_em: string;
  pediu_retorno: boolean;
  revisar: boolean;
  revisar_motivo: string | null;
  revisao_desfecho: "convertida" | "arquivada" | null;
  revisao_motivo: string | null;
  revisada_em: string | null;
  para_revisar: boolean;
  caso: { id: string; protocolo: string | null } | null;
}

export interface PaginaDaLista {
  itens: AvaliacaoDaLista[];
  total: number;
  pagina: number;
  por_pagina: number;
  para_revisar_total: number;
}

export interface FiltrosDaLista {
  periodo: PeriodoDaAba;
  pontoId: string;
  nota: string;
  comComentario: boolean;
  paraRevisar: boolean;
  pagina: number;
}

/**
 * Os filtros com que a aba abre. O contador Para revisar do Painel traz
 * `?revisar=1`: aí a lista abre só nas marcadas e sem limite de data, porque
 * a marca antiga sem desfecho continua esperando alguém.
 */
export function filtrosIniciais(revisar: string | null): FiltrosDaLista {
  const paraRevisar = revisar === "1";
  return {
    periodo: paraRevisar ? "tudo" : PERIODO_PADRAO,
    pontoId: "",
    nota: "",
    comComentario: false,
    paraRevisar,
    pagina: 1,
  };
}

/** O endereço da lista com os filtros. Filtro vazio não vai. */
export function caminhoDaLista(filtros: FiltrosDaLista): string {
  const params = new URLSearchParams({ periodo: filtros.periodo });
  if (filtros.pontoId) params.set("ponto_id", filtros.pontoId);
  if (filtros.nota) params.set("nota", filtros.nota);
  if (filtros.comComentario) params.set("com_comentario", "true");
  if (filtros.paraRevisar) params.set("para_revisar", "true");
  if (filtros.pagina > 1) params.set("pagina", String(filtros.pagina));
  return `/api/ouvidoria/avaliacoes?${params.toString()}`;
}

/** A média com uma casa e vírgula ("4,3"); sem nota, um traço curto. */
export function formatarMedia(media: number | null): string {
  if (media === null) return "-";
  return media.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/** A fração como porcentagem inteira ("40%"). */
export function formatarPorcentagem(fracao: number | null): string {
  if (fracao === null) return "-";
  return `${Math.round(fracao * 100)}%`;
}

const ROTULO_DO_MOTIVO = Object.fromEntries(MOTIVOS_DA_AVALIACAO.map((m) => [m.valor, m.rotulo]));

export function rotuloDoMotivo(valor: string): string {
  return ROTULO_DO_MOTIVO[valor] ?? valor;
}

/** O motivo do arquivo vale quando tem alguma letra ou número. */
export function motivoValido(motivo: string): boolean {
  return /[\p{L}\p{N}]/u.test(motivo) && motivo.trim().length <= TAMANHO_DO_MOTIVO;
}

/** O início da semana ("2026-11-09") como o gráfico mostra ("09/11"). */
export function rotuloDaSemana(semana: string): string {
  const [, mes, dia] = semana.split("-");
  return `${dia}/${mes}`;
}

/** A data e a hora da avaliação no relógio do hospital. */
export function formatarDataHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
