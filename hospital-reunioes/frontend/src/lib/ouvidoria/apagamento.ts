/**
 * O caso apagado, na tela do Dossiê (issue #593, ADR 0034).
 *
 * A Retenção anonimiza o caso encerrado há cinco anos e carimba
 * `anonimizada_em` no fim do serviço (migration 079). Até aqui ninguém lia esse
 * carimbo: a página do caso abria o Dossiê vazio, com o relato em branco e o
 * resumo mostrando o marcador interno da anonimização, sem dizer que o caso
 * havia sido apagado nem quando.
 *
 * O que mora aqui é a régua, que é onde seria fácil mentir: QUAL campo decide
 * que o caso está apagado, e de onde sai o nome de quem apagou. A fiação (o
 * bloco na tela, no lugar do relato) fica no componente.
 *
 * O carimbo é um só e ainda vai ser gravado por outra porta (o apagamento pela
 * Diretoria, issue #595). Por isso nada aqui nomeia a retenção: quem assina o
 * ato é o autor do movimento da trilha, e hoje ele é o autor de sistema.
 */

import type { EventoDaTrilha } from "@/lib/ouvidoria/trilha";

/**
 * O título do bloco, e o marcador pelo qual o teste reconhece o aviso. É uma
 * constante, e não uma frase repetida no teste, porque asserir a ausência do
 * relato não prova nada: o relato do caso apagado já vem nulo do servidor, e um
 * teste de omissão ficaria verde com o bloco inteiro removido da tela.
 */
export const TITULO_DO_CASO_APAGADO = "Caso apagado";

/**
 * O caso foi apagado?
 *
 * A resposta sai do carimbo, e de nenhum outro campo. Perguntar pelo
 * encerramento acusaria de apagado todo caso concluído; perguntar pelo relato
 * vazio acusaria o caso que ainda não teve relato registrado.
 */
export function estaApagado(anonimizadaEm: string | null | undefined): boolean {
  return Boolean(anonimizadaEm);
}

/**
 * Quem apagou, segundo a trilha, ou nulo quando a trilha não diz.
 *
 * Nulo é resultado legítimo e não falha: a leitura da trilha é outra
 * requisição, e ela pode não ter voltado. O aviso continua sendo dito, com a
 * data que o próprio caso carrega, e só o crédito fica de fora.
 */
export function autorDoApagamento(movimentos: EventoDaTrilha[]): string | null {
  return movimentos.find((evento) => evento.apagamento)?.autor ?? null;
}

/**
 * A Diretoria pode apagar ESTE caso agora? (issue #595, ADR 0047)
 *
 * As três condições andam juntas e cada uma tem um motivo próprio:
 *
 * - só a `diretoria_executiva`, porque apagar não tem volta e fica com quem
 *   responde pelo hospital (decisão 3). O ouvidor nem vê o botão;
 * - só caso `encerrado`, porque caso em andamento tem prazo correndo e área
 *   esperando, e apagar o relato deixaria a área sem o que responder;
 * - só caso que ainda tem Dossiê: o carimbado já foi apagado, e oferecer de
 *   novo pediria um motivo para um ato que não vai acontecer.
 *
 * Quem recusa de verdade é o servidor (403 e 409). Aqui a tela só não oferece
 * o caminho que terminaria em recusa, como no resto deste módulo.
 */
export function podeApagar(
  perfilOuvidoria: string | null | undefined,
  status: string,
  anonimizadaEm: string | null | undefined
): boolean {
  return perfilOuvidoria === "diretoria_executiva" && status === "encerrado" && !estaApagado(anonimizadaEm);
}
