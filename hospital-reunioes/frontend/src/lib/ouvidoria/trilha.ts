/**
 * A linha do tempo do caso (issue #485, PRD #470, RN-63 a RN-65).
 *
 * A trilha de movimentos existe desde o primeiro dia do módulo e nunca teve
 * tela: o caso guardava a história inteira e não a mostrava (diagnóstico da
 * Diretoria, D-08).
 *
 * Tudo o que é conta vem pronto do servidor, como no bloco dos marcos: o tempo
 * entre marcos chega em minutos de EXPEDIENTE, já contado no calendário útil do
 * hospital. O navegador não recalcula calendário útil, porque o número que ele
 * inventasse divergiria do prazo que o email do setor cobra.
 *
 * O que mora aqui é só a régua do que a tela diz de cada evento, que é onde
 * seria fácil mentir: evento que não fecha marco, tempo sem calendário
 * confirmado e o texto que a Retenção já apagou.
 */

import { SEM_CONFIRMACAO_DO_CALENDARIO } from "@/lib/ouvidoria/marcos";
import { formatarEsperaUtil } from "@/lib/ouvidoria/prazo";

/** Um evento da trilha, do jeito que o servidor o entrega. */
export interface EventoDaTrilha {
  ocorrido_em: string;
  /** Quem agiu, com o nome que valia no dia do ato. */
  autor: string;
  /** Ato de job, da Retenção ou do canal aberto: ninguém logado por trás. */
  sistema: boolean;
  /** T0 a T3 quando o evento fecha um dos quatro marcos do caso. */
  marco: string | null;
  marco_rotulo: string | null;
  /** O que aconteceu, em uma linha (RN-63). */
  descricao: string;
  /** O conteúdo integral das trocas de texto (RN-64), ou nulo. */
  texto: string | null;
  desde_marco: string | null;
  desde_marco_rotulo: string | null;
  /** Minutos de expediente desde o marco anterior. Nulo fora dos marcos. */
  minutos_uteis: number | null;
}

/**
 * A mesma marca do bloco dos marcos e do painel, palavra por palavra: as duas
 * superfícies da mesma página não podem nomear a mesma falha de dois jeitos.
 */
export { SEM_CONFIRMACAO_DO_CALENDARIO };

/**
 * O tempo desde o marco anterior, em linguagem de gente, ou nulo quando este
 * evento não fecha marco nenhum.
 *
 * A frase NOMEIA de onde a contagem parte ("desde a Validação"). Sem isso, o
 * caso que voltou à área depois de uma devolução mostraria um número medido de
 * um ponto que o ouvidor não tem como adivinhar, e ele o leria como o tempo do
 * trecho errado.
 *
 * `calendarioConfiavel` é obrigatório de propósito: sem calendário o número sai
 * da tela em vez de sair errado, a mesma régua do bloco dos marcos. Feriado que
 * não pôde ser lido conta como dia trabalhado, e a conta erra sem denunciar a
 * si mesma.
 */
export function descreverTempoDesdeOMarco(
  evento: EventoDaTrilha,
  calendarioConfiavel: boolean
): string | null {
  if (evento.minutos_uteis === null || evento.desde_marco_rotulo === null) return null;
  if (!calendarioConfiavel) return SEM_CONFIRMACAO_DO_CALENDARIO;
  return `${formatarEsperaUtil(evento.minutos_uteis)} desde a etapa ${evento.desde_marco_rotulo}`;
}
