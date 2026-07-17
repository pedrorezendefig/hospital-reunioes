/**
 * Arranque da re-elaboração de legado (issue #234, PRD #231): quando há
 * Material de referência anexado e a conversa ainda está vazia, a tela de
 * elaboração oferece um botão que preenche o campo de mensagem com o prompt
 * padrão, editável antes de enviar. Nada é enviado automaticamente.
 */

/** Texto visível ao usuário: sem travessão nem meia-risca (ADR 0013). */
export const PROMPT_ARRANQUE_LEGADO =
  "Elabore a nova versão deste POP a partir do material anexado, mantendo a estrutura e o conteúdo do documento original.";

/**
 * Condição de exibição do botão: ao menos 1 Material de referência anexado e
 * conversa sem mensagens do Elaborador (a mensagem de boas-vindas do
 * assistente não conta como conversa iniciada).
 */
export function exibirArranqueLegado(
  qtdMateriais: number,
  mensagens: { role: string }[]
): boolean {
  return qtdMateriais > 0 && mensagens.every((m) => m.role !== "user");
}
