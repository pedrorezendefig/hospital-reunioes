/**
 * Classificação do prazo de um protocolo de ouvidoria para o destaque visual
 * do painel (issue #292). Datas em ISO (YYYY-MM-DD), comparadas como data
 * civil: sem fuso, sem hora.
 */

export type StatusProtocolo = "aberto" | "respondido" | "encerrado";

export type ClassePrazo = "estourado" | "perto" | "normal" | "respondido";

const MS_POR_DIA = 1000 * 60 * 60 * 24;

export function classificarPrazo(
  prazo: string,
  status: StatusProtocolo,
  hoje: string
): ClassePrazo {
  if (status !== "aberto") return "respondido";
  const diffDias = Math.round(
    (Date.parse(`${prazo}T12:00:00`) - Date.parse(`${hoje}T12:00:00`)) / MS_POR_DIA
  );
  if (diffDias < 0) return "estourado";
  if (diffDias <= 2) return "perto";
  return "normal";
}
