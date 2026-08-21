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
