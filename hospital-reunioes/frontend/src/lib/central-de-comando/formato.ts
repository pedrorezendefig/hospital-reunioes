/**
 * Como a Central de Comando escreve os números na tela (ADR 0058).
 *
 * Porte de `src/lib/format.ts` do repositório antigo. Só escreve: a conta
 * (variação, período anterior) já vem pronta do backend.
 */

const INTEIRO = new Intl.NumberFormat("pt-BR");

const PERCENTUAL = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Inteiro no formato pt-BR: 38412 vira "38.412". */
export function formatarInteiro(n: number): string {
  return INTEIRO.format(n);
}

/**
 * Fração como porcentagem pt-BR com uma casa: 0,124 vira "12,4%".
 *
 * Não põe sinal nem seta: quem chama decide o sentido e passa o módulo.
 */
export function formatarPercentual(fracao: number): string {
  return PERCENTUAL.format(fracao);
}

/**
 * Data ISO do backend (`2026-08-21`) como o hospital lê: "21/08/2026".
 *
 * Sai do texto, e não de um `Date`: meia-noite em UTC ainda é o dia anterior
 * no Brasil, e a data que o backend mandou é a data que a tela tem de dizer.
 */
export function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}
