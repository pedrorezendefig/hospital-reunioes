/**
 * A cobrança do setor pela fila (issue #495, PRD #471).
 *
 * Cobrar não é um email novo: é o reenvio do acionamento, com a regra vigente
 * de reenvio (ADR 0034, decisão 7), que nasce como registro próprio e deixa
 * intacta a data do primeiro envio. Elevar a cobrança a botão de primeira
 * classe é dar ao ouvidor, na linha da fila, o que antes exigia abrir o caso e
 * caçar o registro certo na lista de notificações.
 *
 * Este módulo é puro: escolhe QUAL registro reenviar. Quem chama a rota é a
 * tela.
 */

/** O gatilho do email que acorda o setor (`ouvidoria_notificacoes`). */
export const GATILHO_DO_ACIONAMENTO = "nova_demanda";

export interface NotificacaoDoCaso {
  id: string;
  gatilho: string;
  criada_em: string;
}

/**
 * O acionamento que a cobrança reenvia: o mais recente do caso.
 *
 * "Mais recente" é lido do carimbo, e não da posição na lista: a rota devolve
 * em ordem decrescente hoje, e uma linha a mais no `order` do servidor
 * mandaria a cobrança para o acionamento de um mês atrás sem nada quebrar.
 * Caso reaberto por reincidência é acionado de novo, e é do último que a área
 * está sendo cobrada.
 *
 * Sem acionamento registrado devolve nulo: setor sem responsável cadastrado é
 * acionado sem email nenhum, e a tela precisa dizer isso em vez de disparar um
 * POST que termina em 404.
 */
export function acionamentoParaCobrar<T extends NotificacaoDoCaso>(
  notificacoes: T[]
): T | null {
  const acionamentos = notificacoes.filter((n) => n.gatilho === GATILHO_DO_ACIONAMENTO);
  if (acionamentos.length === 0) return null;
  return acionamentos.reduce((maisNova, atual) =>
    Date.parse(atual.criada_em) > Date.parse(maisNova.criada_em) ? atual : maisNova
  );
}
