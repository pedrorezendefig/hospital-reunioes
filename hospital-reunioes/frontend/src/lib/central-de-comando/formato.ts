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
 * A hora do relógio do hospital, e não a do navegador: é nela que se lê
 * "Mostrando os números de 13h45" (molde do painel da Ouvidoria).
 */
const HORA_NO_HOSPITAL = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  hour: "numeric",
  minute: "2-digit",
  hourCycle: "h23",
});

/**
 * Um instante (epoch em ms) como hora do hospital: "13h45", "9h05".
 *
 * Porte de `formatClock` do repositório antigo, com o fuso fixo no do hospital.
 */
export function formatarHora(instante: number): string {
  const partes = HORA_NO_HOSPITAL.formatToParts(instante);
  const hora = partes.find((p) => p.type === "hour")?.value ?? "";
  const minuto = partes.find((p) => p.type === "minute")?.value ?? "";
  return `${Number(hora)}h${minuto}`;
}

/** O dia do hospital de um instante, como "17/09/2026". */
const DIA_NO_HOSPITAL = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/**
 * De quando é um número, visto de `agora` (epoch em ms): só a hora quando é do
 * mesmo dia do hospital ("13h45"), o dia e a hora quando não é ("17/09/2026 às
 * 13h45"). É o que o aviso do último valor bom usa: com o Google fora desde
 * ontem, "os números de 13h45" leria como de hoje.
 */
export function formatarQuando(instante: number, agora: number): string {
  const dia = DIA_NO_HOSPITAL.format(instante);
  return dia === DIA_NO_HOSPITAL.format(agora) ? formatarHora(instante) : `${dia} às ${formatarHora(instante)}`;
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
