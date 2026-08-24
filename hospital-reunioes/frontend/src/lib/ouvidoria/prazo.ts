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
 * `prazo_area_em` e `rotulo_prazo` vêm calculados do motor no servidor: o
 * navegador não recalcula calendário útil, para painel e email do setor nunca
 * dizerem prazos diferentes.
 */
export interface PrazoDaManifestacao {
  status: StatusManifestacao;
  prazo_resposta: string;
  prazo_area_em: string | null;
  prazo_estourado: boolean;
  rotulo_prazo: string;
}

/**
 * Destaque visual da linha. Caso já classificado usa o veredito do motor;
 * caso ainda sem gravidade cai no prazo de 7 dias corridos da fundação, que
 * é o que existe antes de o ouvidor validar.
 */
export function classificarPrazoDaManifestacao(
  m: PrazoDaManifestacao,
  hoje: string
): ClassePrazo {
  if (!EM_ANDAMENTO.has(m.status)) return "respondido";
  if (!m.prazo_area_em) return classificarPrazo(m.prazo_resposta, m.status, hoje);
  if (m.prazo_estourado) return "estourado";
  const diasAteVencer = Math.round(
    (Date.parse(m.prazo_area_em) - Date.parse(`${hoje}T12:00:00`)) / MS_POR_DIA
  );
  return diasAteVencer <= 2 ? "perto" : "normal";
}

/**
 * Quem define os parâmetros do prazo (RN-21). Mais estreito que o perfil da
 * Ouvidoria de propósito: o ouvidor trabalha com o prazo, quem o define é a
 * Diretoria Executiva. Quem não passa aqui não vê a tela de edição.
 */
export function podeEditarPrazos(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "diretoria_executiva";
}
