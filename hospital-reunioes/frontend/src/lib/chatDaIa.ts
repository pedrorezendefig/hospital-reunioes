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

/**
 * O teto de uma fala, igual ao do backend. O backend confere TODA fala do
 * histórico, e não só a nova: uma fala acima dele que entrasse na conversa
 * voltaria em todo turno, e o chat recusaria tudo até ela sair da janela.
 * Por isso a tela barra a fala do usuário antes do envio, e o histórico enviado
 * deixa de fora qualquer fala acima do teto (uma resposta longa da IA, por exemplo).
 */
export const LIMITE_DA_MENSAGEM = 8000;

const MOTIVO_MENSAGEM_GRANDE =
  "A mensagem passou de 8.000 caracteres, o tamanho que o chat aceita. Encurte o texto e mande de novo.";

/** A frase da recusa quando a fala passa do teto, ou null quando ela pode seguir. */
export function recusaDaFala(content: string): string | null {
  return content.length > LIMITE_DA_MENSAGEM ? MOTIVO_MENSAGEM_GRANDE : null;
}

export const ERRO_DO_TURNO = "Desculpe, houve um erro. Tente novamente.";

export function historicoParaEnvio(messages: ChatMessagePayload[]): ChatMessagePayload[] {
  return messages
    .filter(({ content }) => content.length <= LIMITE_DA_MENSAGEM)
    .slice(-LIMITE_DE_MENSAGENS)
    .map(({ role, content }) => ({ role, content }));
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
