/**
 * O distintivo de novidades no menu (issue #487, PRD #470, RN-69).
 *
 * O servidor conta (rota `/api/ouvidoria/novidades`), e aqui mora só a régua do
 * que o menu desenha com o número que chegou. A régua é curta e existe fora do
 * componente por um motivo: ela decide o que o ouvidor conclui sem abrir nada,
 * e três estados diferentes desenham telas parecidas demais para ficarem
 * espalhados em JSX.
 *
 * Os três estados, e por que nenhum deles pode virar o outro:
 *
 * * sem contagem: nada na tela. É a contagem que ainda não chegou, e também a
 *   de quem não é da Ouvidoria (o item do menu existe para todo mundo, o
 *   número não). Um distintivo que aparece e troca de número um segundo depois
 *   treina o olho a não confiar nele;
 * * contado, e o total é zero: nada na tela. É a única ausência honesta;
 * * não deu para contar: distintivo SEM número. Esconder aqui seria dizer
 *   "nada novo" com uma leitura que falhou, que é o erro que esta fatia mais
 *   precisa evitar (mesmo cuidado do `degradado` da fila, issue #449).
 */

/** O que o menu sabe sobre as novidades neste instante. */
export type ContagemDeNovidades =
  /** Não há número a mostrar: ou ainda não chegou, ou não é da Ouvidoria. */
  | { estado: "sem_contagem" }
  | { estado: "ok"; total: number }
  /** O servidor não conseguiu contar, e isso não é o mesmo que zero. */
  | { estado: "indisponivel" };

export interface Distintivo {
  /** O que aparece dentro do distintivo. */
  texto: string;
  /** O que o leitor de tela anuncia, e o que o mouse parado revela. */
  rotulo: string;
}

/**
 * Acima disto o número deixa de ser lido e passa a ser só largura. O teto não é
 * decorativo: a migration do visto entrou sem backfill de propósito, então todo
 * caso anterior a ela nasce com novidade e a primeira carga pode trazer o
 * histórico inteiro do hospital.
 */
export const TETO_DO_DISTINTIVO = 99;

/** O distintivo que o item de menu deve mostrar, ou `null` para não mostrar nenhum. */
export function distintivoDeNovidades(
  contagem: ContagemDeNovidades
): Distintivo | null {
  if (contagem.estado === "indisponivel") {
    return {
      texto: "?",
      rotulo: "Não foi possível contar as novidades da Ouvidoria",
    };
  }
  if (contagem.estado !== "ok" || contagem.total <= 0) return null;
  return {
    texto:
      contagem.total > TETO_DO_DISTINTIVO
        ? `${TETO_DO_DISTINTIVO}+`
        : String(contagem.total),
    rotulo:
      contagem.total === 1
        ? "1 caso com novidade"
        : `${contagem.total} casos com novidade`,
  };
}
