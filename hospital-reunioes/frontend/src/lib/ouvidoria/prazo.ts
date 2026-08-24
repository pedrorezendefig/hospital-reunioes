/**
 * Classificação do prazo de uma manifestação de ouvidoria para o destaque
 * visual do painel (issues #292 e #320). Datas em ISO (YYYY-MM-DD),
 * comparadas como data civil: sem fuso, sem hora.
 */

export type StatusManifestacao =
  | "novo"
  | "em_classificacao"
  | "aguardando_area"
  | "respondido"
  | "encerrado";

export type ClassePrazo = "estourado" | "perto" | "normal" | "respondido";

/**
 * Estados em que o relógio ainda corre. A partir de "respondido" o caso saiu
 * das mãos da ouvidoria e o prazo de resposta deixa de valer.
 */
export const EM_ANDAMENTO = new Set<StatusManifestacao>([
  "novo",
  "em_classificacao",
  "aguardando_area",
]);

const MS_POR_DIA = 1000 * 60 * 60 * 24;

export function classificarPrazo(
  prazo: string,
  status: StatusManifestacao,
  hoje: string
): ClassePrazo {
  if (!EM_ANDAMENTO.has(status)) return "respondido";
  const diffDias = Math.round(
    (Date.parse(`${prazo}T12:00:00`) - Date.parse(`${hoje}T12:00:00`)) / MS_POR_DIA
  );
  if (diffDias < 0) return "estourado";
  if (diffDias <= 2) return "perto";
  return "normal";
}

/**
 * O que o painel precisa saber do prazo de uma manifestação (issue #322).
 * Tudo vem calculado do motor no servidor: o navegador não recalcula
 * calendário útil, para painel e email do setor nunca dizerem prazos
 * diferentes.
 */
export interface PrazoDaManifestacao {
  status: StatusManifestacao;
  prazo_resposta: string;
  prazo_area_em: string | null;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  /** Folga em minutos de expediente. Zero quando estourado, nulo sem prazo. */
  minutos_uteis_restantes: number | null;
}

/** Expediente de 08h às 17h: a mesma régua que o motor usa no servidor. */
const MINUTOS_POR_DIA_UTIL = 9 * 60;
/** A partir de 2 dias úteis de folga a linha ganha destaque de "vence logo". */
const FOLGA_DE_ALERTA = 2 * MINUTOS_POR_DIA_UTIL;

/**
 * Destaque visual da linha. Caso já classificado usa o veredito do motor;
 * caso ainda sem gravidade cai no prazo de 7 dias corridos da fundação, que
 * é o que existe antes de o ouvidor validar.
 *
 * A proximidade é medida em tempo útil, e não em dias corridos: um vencimento
 * de segunda visto na sexta está a 3 dias no calendário e a 1 dia de trabalho,
 * e é o segundo número que decide se alguém precisa correr.
 */
export function classificarPrazoDaManifestacao(
  m: PrazoDaManifestacao,
  hoje: string
): ClassePrazo {
  if (!EM_ANDAMENTO.has(m.status)) return "respondido";
  if (!m.prazo_area_em) return classificarPrazo(m.prazo_resposta, m.status, hoje);
  if (m.prazo_estourado) return "estourado";
  if (m.minutos_uteis_restantes === null) return "normal";
  return m.minutos_uteis_restantes <= FOLGA_DE_ALERTA ? "perto" : "normal";
}

/**
 * Quem define os parâmetros do prazo (RN-21). Mais estreito que o perfil da
 * Ouvidoria de propósito: o ouvidor trabalha com o prazo, quem o define é a
 * Diretoria Executiva. Quem não passa aqui não vê a tela de edição.
 */
export function podeEditarPrazos(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "diretoria_executiva";
}
