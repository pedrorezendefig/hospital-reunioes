/**
 * A cobrança do setor pela fila (issues #495 e #536, PRD #471).
 *
 * Cobrar não é um email novo: é o acionamento saindo de novo, com a regra
 * vigente de reenvio (ADR 0034, decisão 7), que nasce como registro próprio e
 * deixa intacta a data do primeiro envio. Elevar a cobrança a botão de primeira
 * classe é dar ao ouvidor, na linha da fila, o que antes exigia abrir o caso e
 * caçar o registro certo na lista de notificações.
 *
 * **Para quem a cobrança vai é decisão do servidor** (issue #536). A rota
 * `POST /manifestacoes/{id}/cobrar-setor` resolve o responsável vigente do
 * setor na cadeia do acionamento (titular, senão gestor) e recusa o setor que
 * não tem ninguém. A tela cobrou, a tela exibe: escolher o destinatário aqui
 * faria do relato do manifestante e de um token do portal um parâmetro de
 * requisição, e deixaria a mesma regra escrita em dois lugares para divergir
 * no primeiro dia em que a cadeia mudasse.
 *
 * Sobra para este módulo o que a linha ESCREVE, que é o que a tela sabe de
 * verdade: a fase da cobrança e o que a resposta afirmou.
 */

/**
 * O que a tela sabe da cobrança de uma linha.
 *
 * `entregue` guarda o que a rota devolve: o provedor pode recusar o email na
 * hora e a notificação fica na fila, e afirmar entrega nesse caso é mentir para
 * o ouvidor que acabou de clicar.
 *
 * `explicacao` da recusa vem do servidor, e não de um mapa de motivos daqui: é
 * ele que sabe se o setor está sem responsável vigente ou se quem responde está
 * sem email no cadastro, e essas duas frases mandam o ouvidor a lugares
 * diferentes.
 */
export type ResultadoDaCobranca =
  | { fase: "enviando" }
  | { fase: "reenviada"; destinatario: string; entregue: boolean }
  | { fase: "recusada"; explicacao: string }
  | { fase: "falha" };

/** Recusa sem frase do servidor não pode sair em branco na linha. */
export const RECUSA_SEM_EXPLICACAO = "A cobrança não pôde sair. Confira o cadastro de responsáveis do setor.";

/** A frase que a linha mostra. Afirma só o que a resposta confirma. */
export function textoDaCobranca(resultado: ResultadoDaCobranca): string {
  switch (resultado.fase) {
    case "enviando":
      return "Reenviando o acionamento...";
    case "reenviada":
      return resultado.entregue
        ? `Acionamento reenviado a ${resultado.destinatario}`
        : `O reenvio a ${resultado.destinatario} ficou na fila: o provedor recusou agora e o sistema tenta de novo.`;
    case "recusada":
      return resultado.explicacao || RECUSA_SEM_EXPLICACAO;
    case "falha":
      return "Não foi possível cobrar agora. Tente de novo em instantes.";
  }
}

/** Verde só para o que chegou; o resto pede atenção. */
export function tomDaCobranca(resultado: ResultadoDaCobranca): "ok" | "alerta" | "neutro" {
  if (resultado.fase === "reenviada") return resultado.entregue ? "ok" : "alerta";
  if (resultado.fase === "recusada" || resultado.fase === "falha") return "alerta";
  return "neutro";
}
