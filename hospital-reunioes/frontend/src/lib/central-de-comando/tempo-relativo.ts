/**
 * Há quanto tempo, em português de gente (issue #815, ADR 0058).
 *
 * Porte de `src/lib/relative-time.ts` do repositório antigo: "agora mesmo"
 * abaixo de 1 minuto, "há N minutos" abaixo de 1 hora e "há N horas" daí para
 * cima, sempre arredondando para baixo.
 *
 * Pura: recebe o "agora" em vez de ler o relógio, para ser testável e para a
 * barra de frescor decidir quando ele anda.
 */

const MINUTO_MS = 60_000;

/** O tempo entre `desde` e `agora` (epoch em ms). Nunca negativo. */
export function tempoRelativo(desde: number, agora: number): string {
  const minutos = Math.floor(Math.max(0, agora - desde) / MINUTO_MS);
  if (minutos < 1) return "agora mesmo";
  if (minutos < 60) return `há ${minutos} ${minutos === 1 ? "minuto" : "minutos"}`;
  const horas = Math.floor(minutos / 60);
  return `há ${horas} ${horas === 1 ? "hora" : "horas"}`;
}
