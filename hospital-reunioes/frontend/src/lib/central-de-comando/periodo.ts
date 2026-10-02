/**
 * Os períodos da Central de Comando, do lado da tela (ADR 0058).
 *
 * Porte de `parsePeriod` e `PERIODS` de `src/lib/analytics/period.ts` do
 * repositório antigo. As datas de cada período são conta do backend, que as
 * devolve no payload; a tela só lê o período do endereço (`?periodo=`) e
 * escreve "7 dias", "28 dias" e "90 dias".
 */

export type Periodo = "7d" | "28d" | "90d";

/** Na ordem do seletor. */
export const PERIODOS: readonly Periodo[] = ["7d", "28d", "90d"];

/**
 * Os períodos do Instagram: só 7 e 28 dias. A fonte entrega no máximo 30 dias
 * de insights por consulta, então 90 dias fica de fora, e quem digita
 * `?periodo=90d` no endereço vê o padrão de 28 (o `lerPeriodo` com estes
 * `permitidos`), sem tela de erro.
 */
export const PERIODOS_DO_INSTAGRAM: readonly Periodo[] = ["7d", "28d"];

/** O de quando ninguém escolheu (e de quando escolheram um que não existe). */
export const PERIODO_PADRAO: Periodo = "28d";

const DIAS: Record<Periodo, number> = { "7d": 7, "28d": 28, "90d": 90 };

export function diasDoPeriodo(periodo: Periodo): number {
  return DIAS[periodo];
}

/**
 * Lê o período do endereço. Ausente, inválido ou fora de `permitidos` vira o
 * padrão, e o parâmetro repetido vale pelo primeiro: o endereço é digitável, e
 * o que se digita errado mostra 28 dias em vez de uma tela de erro.
 */
export function lerPeriodo(
  valor: string | string[] | null | undefined,
  permitidos: readonly Periodo[] = PERIODOS,
): Periodo {
  const primeiro = Array.isArray(valor) ? valor[0] : valor;
  return permitidos.includes(primeiro as Periodo) ? (primeiro as Periodo) : PERIODO_PADRAO;
}
