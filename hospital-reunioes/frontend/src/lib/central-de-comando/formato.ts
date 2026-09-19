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

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const DIAS_DA_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

function partesDaData(iso: string): { dia: number; mes: number; semana: number } {
  const [ano, mes, dia] = iso.split("-").map(Number);
  // O dia da semana da própria data, em UTC: o fuso do navegador não entra.
  const semana = new Date(Date.UTC(ano, mes - 1, dia)).getUTCDay();
  return { dia, mes, semana };
}

/**
 * Data ISO do backend como rótulo curto de gráfico: "16 jun", "1 set".
 *
 * Porte de `formatDayShort` do repositório antigo; como o `formatarData`, sai
 * do texto, e não de um `Date` no fuso do navegador.
 */
export function formatarDiaCurto(iso: string): string {
  const { dia, mes } = partesDaData(iso);
  return `${dia} ${MESES[mes - 1]}`;
}

/** Com o dia da semana: "ter, 16 jun". Porte de `formatDayLong`. */
export function formatarDiaLongo(iso: string): string {
  const { dia, mes, semana } = partesDaData(iso);
  return `${DIAS_DA_SEMANA[semana]}, ${dia} ${MESES[mes - 1]}`;
}

/**
 * Uma fatia em pontos percentuais inteiros, como o backend manda (no Por
 * dispositivo as fatias somam 100; na Origem do público, #818, cada uma é
 * arredondada sozinha, como na Central antiga): 71 vira "71%". O backend só
 * manda fatia com visita, então 0 ponto é menos de 1%, e sai "<1%" (o
 * `formatShare` do repositório antigo), nunca um zero que diria "ninguém".
 */
export function formatarFatia(percentual: number): string {
  return percentual <= 0 ? "<1%" : `${percentual}%`;
}

const INTEIRO_COMPACTO = new Intl.NumberFormat("pt-BR", { notation: "compact" });

/** Inteiro curto para o eixo do gráfico no celular: 1200 vira "1,2 mil". */
export function formatarInteiroCompacto(n: number): string {
  return INTEIRO_COMPACTO.format(n);
}
