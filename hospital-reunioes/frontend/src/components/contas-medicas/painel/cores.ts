import type { NivelDeEvidencia } from "@/lib/contas-medicas/painel";

/**
 * As cores dos gráficos do Painel (issue #1137): os tokens do app
 * (`globals.css`), no molde dos gráficos da Central de Comando. Nenhuma cor
 * diz se o número é bom ou ruim: é a cor primária nos números e nas barras.
 */

export const COR_PRIMARIA = "var(--color-primary)";

export const COR_DA_GRADE = "var(--color-border)";

export const COR_DO_EIXO = "var(--color-text-secondary)";

export const COR_DO_TRILHO = "var(--color-border)";

/** Uma faixa por nível de evidência, dos azuis da marca para o cinza. */
export const COR_DO_NIVEL: Record<NivelDeEvidencia, string> = {
  REGISTRADO: "var(--color-primary)",
  PRESCRITO: "var(--color-primary-light)",
  PRESCRITO_SN: "var(--color-info)",
  POR_REGRA: "var(--color-text-secondary)",
};
