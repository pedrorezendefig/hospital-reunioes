/**
 * Nota externa manual: Google e Reclame Aqui (issue #347, PRD #319).
 *
 * O retrato que o hospital tem fora dele. Ninguém aqui calcula a estrela do
 * Google: quem sabe é o ouvidor, que abre as duas páginas e digita o que leu.
 *
 * As duas escalas NÃO são a mesma, e é isso que este módulo existe para
 * proteger. O Google vai de 0 a 5, o Reclame Aqui de 0 a 10. Uma tela que
 * mostra "4,3" e "7,8" lado a lado faz o leitor concluir que o hospital vai
 * melhor no Reclame Aqui, quando 4,3 de 5 é 86% e 7,8 de 10 é 78%. Por isso a
 * escala viaja colada no número, aqui e no PDF.
 *
 * A régua também está no backend (`ouvidoria_nota_externa.py`) e no banco
 * (migration 082): esta é a que dá o aviso antes do envio, não a que decide.
 */

export type FonteExterna = "google" | "reclame_aqui";

/** A fonte e o teto da régua dela. */
export const ESCALA: Record<FonteExterna, number> = {
  google: 5,
  reclame_aqui: 10,
};

export const ROTULO_FONTE: Record<FonteExterna, string> = {
  google: "Google",
  reclame_aqui: "Reclame Aqui",
};

export const FONTES: FonteExterna[] = ["google", "reclame_aqui"];

const PERFIS_DA_OUVIDORIA = ["ouvidor", "diretoria_executiva"];

export function podeRegistrarNotaExterna(
  perfilOuvidoria: string | null | undefined
): boolean {
  return PERFIS_DA_OUVIDORIA.includes(String(perfilOuvidoria));
}

export type NotaValidada =
  | { ok: true; valor: number }
  | { ok: false; erro: string };

/**
 * O que o ouvidor digitou, virado número, ou o motivo de não servir.
 *
 * Aceita vírgula: é assim que se escreve 4,3 em português, e recusar o teclado
 * de quem usa a tela seria recusar por formatação.
 */
export function validarNota(fonte: FonteExterna, digitado: string): NotaValidada {
  const teto = ESCALA[fonte];
  const limpo = digitado.trim().replace(",", ".");
  if (limpo === "") {
    return { ok: false, erro: `Digite a nota do ${ROTULO_FONTE[fonte]}, de 0 a ${teto}.` };
  }
  const valor = Number(limpo);
  if (!Number.isFinite(valor)) {
    return { ok: false, erro: `A nota do ${ROTULO_FONTE[fonte]} é um número de 0 a ${teto}.` };
  }
  if (valor < 0 || valor > teto) {
    return { ok: false, erro: `A nota do ${ROTULO_FONTE[fonte]} vai de 0 a ${teto}.` };
  }
  return { ok: true, valor };
}

/**
 * O número com a régua colada. Ausência de registro diz que não há, e nunca
 * vira "0,0", que leria como a pior nota possível.
 */
export function formatarNota(nota: number | null | undefined, escala: number): string {
  if (nota === null || nota === undefined) return "sem registro";
  return `${nota.toFixed(1).replace(".", ",")} de ${escala}`;
}
