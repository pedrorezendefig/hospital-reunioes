/**
 * O envio ao Núcleo de Segurança do Paciente (issue #1621, ADR 0088).
 *
 * As frases e a regra que a validação, o Dossiê e a tela do link dividem. A
 * régua de verdade é do backend (`ouvidoria_nucleo.py`); aqui mora só o que a
 * tela precisa para não oferecer um caminho que o servidor recusa.
 */

export const ALERTA_DO_NUCLEO = "Possível evento de segurança do paciente";
export const SELO_DO_NUCLEO = "Em análise pelo NSP";

export type DecisaoDoNucleo = "confirmado" | "descartado";

export interface CamposDoNucleo {
  nsp_sugerido?: boolean | null;
  nsp_justificativa_simples?: string | null;
  nsp_decisao?: DecisaoDoNucleo | string | null;
  nsp_decisao_motivo?: string | null;
  nsp_decidido_em?: string | null;
}

/**
 * Se a validação deste caso precisa da decisão sobre o Núcleo: o agente
 * apontou o caso e ninguém decidiu ainda. O caso já decidido (o devolvido que
 * volta à validação) não pergunta de novo.
 */
export function pedeDecisaoDoNucleo(caso: CamposDoNucleo | null | undefined): boolean {
  return Boolean(caso?.nsp_sugerido) && !caso?.nsp_decisao;
}

/** Se a decisão escolhida na tela já basta para validar. */
export function decisaoCompleta(decisao: DecisaoDoNucleo | "", motivo: string): boolean {
  if (decisao === "confirmado") return true;
  return decisao === "descartado" && motivo.trim().length > 0;
}

/** Se o caso já está com o Núcleo (o selo Em análise pelo NSP). */
export function estaComONucleo(caso: CamposDoNucleo | null | undefined): boolean {
  return caso?.nsp_decisao === "confirmado";
}
