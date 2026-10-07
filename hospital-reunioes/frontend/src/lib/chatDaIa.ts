import type { ChatMessagePayload } from "@/types/chat";

/**
 * O teto de mensagens dos três chats de IA (correção da Ata, Ata Guiada e
 * elaboração de POP), igual ao do backend (`teto_dos_chats`, issue #893).
 *
 * Ele é alcançável pelo canal de verdade: vinte idas e voltas passam das
 * quarenta mensagens, e todo turno reenvia o histórico inteiro. Por isso a
 * tela manda só a janela das últimas; o estado que importa já viaja à parte
 * (rascunho ou plano de correção), e o teto do backend fica para o abuso.
 */
export const LIMITE_DE_MENSAGENS = 40;

export const ERRO_DO_TURNO = "Desculpe, houve um erro. Tente novamente.";

export function historicoParaEnvio(messages: ChatMessagePayload[]): ChatMessagePayload[] {
  return messages.slice(-LIMITE_DE_MENSAGENS).map(({ role, content }) => ({ role, content }));
}

/**
 * A fala que entra na conversa quando o turno falha.
 *
 * A recusa de um teto vem em 422 com frase de gente no `detail`, e chega à
 * conversa como veio. O 422 do pydantic traz `detail` em lista e qualquer
 * outra falha fica com a frase genérica de sempre.
 */
export async function falaDaFalha(res: Response): Promise<string> {
  if (res.status !== 422) return ERRO_DO_TURNO;
  const corpo = await res.json().catch(() => null);
  return typeof corpo?.detail === "string" ? corpo.detail : ERRO_DO_TURNO;
}
