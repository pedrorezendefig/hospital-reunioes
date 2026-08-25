/**
 * Classificação do prazo de uma manifestação de ouvidoria para o destaque
 * visual do painel (issues #292 e #320). Datas em ISO (YYYY-MM-DD),
 * comparadas como data civil: sem fuso, sem hora.
 */

export type StatusManifestacao =
  | "novo"
  | "em_classificacao"
  | "aguardando_area"
  | "aguardando_manifestante"
  | "respondido"
  | "encerrado";

export type ClassePrazo = "estourado" | "perto" | "normal" | "respondido";

/**
 * Estados em que o relógio ainda corre. A partir de "respondido" o caso saiu
 * das mãos da ouvidoria e o prazo de resposta deixa de valer.
 *
 * "aguardando_manifestante" fica de fora de propósito (issue #335): é a pausa,
 * e durante ela o relógio da área está parado. Mostrar contagem regressiva ali
 * cobraria o setor por uma espera que não é dele.
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

/**
 * O tempo parado aguardando o manifestante em linguagem de gente (issue #335).
 *
 * O número vem em minutos de EXPEDIENTE, e um dia útil do hospital tem nove
 * horas: dizer "2 dias úteis" para 18 horas é o que o ouvidor entende, e
 * "1080 minutos" não é.
 *
 * O arredondamento acontece PRIMEIRO, em horas, e só então os dias são
 * separados. Arredondar o resto por conta própria deixava as horas alcançarem
 * um dia inteiro: 535 min virava "9 horas úteis" e 1074 min virava "1 dia útil
 * e 9 horas úteis".
 */
export function formatarEsperaUtil(minutos: number): string {
  const HORAS_POR_DIA_UTIL = 9;
  const totalHoras = Math.round(minutos / 60);
  const dias = Math.floor(totalHoras / HORAS_POR_DIA_UTIL);
  const horas = totalHoras % HORAS_POR_DIA_UTIL;
  const partes: string[] = [];
  if (dias > 0) partes.push(dias === 1 ? "1 dia útil" : `${dias} dias úteis`);
  if (horas > 0) partes.push(horas === 1 ? "1 hora útil" : `${horas} horas úteis`);
  return partes.length > 0 ? partes.join(" e ") : "menos de uma hora útil";
}
