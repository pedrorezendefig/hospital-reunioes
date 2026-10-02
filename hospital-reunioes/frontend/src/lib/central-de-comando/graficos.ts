/**
 * O que os gráficos de Dados do Google decidem antes de desenhar (issue #817,
 * ADR 0058).
 *
 * Os gráficos são `recharts`, no molde dos gráficos do dashboard, e as cores
 * são os tokens do app (`globals.css`), nunca cor escrita à mão: é o mesmo
 * azul do resto do app, e muda junto com ele. Um teste de varredura
 * (`cores-dos-graficos.test.ts`) trava isso.
 */

/** A linha do período escolhido: o azul-marinho da marca. */
export const COR_ATUAL = "var(--color-primary)";

/** A linha do período anterior: cinza e tracejada, para ficar atrás. */
export const COR_ANTERIOR = "var(--color-text-secondary)";

/** As linhas de fundo do gráfico. */
export const COR_DA_GRADE = "var(--color-border)";

/** Os rótulos dos eixos. */
export const COR_DO_EIXO = "var(--color-text-secondary)";

export type Dispositivo = "celular" | "computador" | "tablet";

/** Uma cor por dispositivo, dos azuis da marca. */
export const COR_DO_DISPOSITIVO: Record<Dispositivo, string> = {
  celular: "var(--color-primary)",
  computador: "var(--color-primary-light)",
  tablet: "var(--color-info)",
};

/** No máximo 4 rótulos no eixo dos dias: cabe no celular sem encavalar. */
const MARCAS_NO_EIXO = 4;

/**
 * Quais dias ganham rótulo no eixo: o primeiro, o último e os do meio,
 * espaçados, no máximo 4. Porte de `xTickIndexes` do `VisitorsChart` do
 * repositório antigo. Com 90 dias, rotular todos seria um borrão no celular.
 */
export function marcasDoEixo(dias: number): number[] {
  if (dias <= 0) return [];
  if (dias === 1) return [0];
  const marcas = Math.min(MARCAS_NO_EIXO, dias);
  const indices = new Set<number>();
  for (let k = 0; k < marcas; k++) indices.add(Math.round((k * (dias - 1)) / (marcas - 1)));
  return [...indices].sort((a, b) => a - b);
}

/**
 * A linha do período anterior só entra quando ele teve alguma visita: uma
 * linha no zero pareceria queda de 100%, e não é comparação nenhuma. Porte do
 * `hasPrev` do `VisitorsChart` do repositório antigo.
 */
export function temAnterior(pontos: readonly { visitantes_anterior: number }[]): boolean {
  return pontos.some((ponto) => ponto.visitantes_anterior > 0);
}

// ─── As barras de Dados do Google (issue #818) ─────────────────────────────
//
// O ranking das Áreas do site e a Origem do público são barras em Tailwind
// puro, sem `recharts`: um trilho e, dentro dele, a barra com a largura da
// fatia. As cores continuam sendo os tokens do app, e moram aqui, onde a
// varredura das cores as confere.

/** A barra de uma Área do site ou de uma Origem do público: o azul-marinho da marca. */
export const COR_DA_BARRA = "var(--color-primary)";

/** A barra do resto da Origem do público (Outros e Não identificado): cinza, para ficar atrás. */
export const COR_DA_BARRA_DO_RESTO = "var(--color-text-secondary)";

/** O trilho, o fundo de cada barra. */
export const COR_DO_TRILHO = "var(--color-border)";

/**
 * A largura da barra de um valor ao lado do maior deles, em pontos
 * percentuais do trilho, com duas casas: o maior enche o trilho, e os outros
 * ficam na proporção dele. Porte da barra do ranking da Central antiga. Com
 * tudo zerado, as barras ficam vazias, sem dividir por zero.
 */
export function larguraNaProporcaoDoMaior(valor: number, maior: number): number {
  return Number(((valor / Math.max(1, maior)) * 100).toFixed(2));
}
