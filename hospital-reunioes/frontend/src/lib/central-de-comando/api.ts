/**
 * A conversa das telas da Central de Comando com o backend (ADR 0058).
 *
 * Cada tela pede o payload inteiro dela a um caminho relativo (`/api/...`),
 * com o token da sessão, e guarda a resposta em estado local: sem biblioteca
 * de cache (PRD #809). O que mora aqui é o que toda tela da Central repete.
 */

export const BASE_CENTRAL = "/api/admin/central-de-comando";

/** A rede caiu antes de o backend responder. */
export const FALHA_DE_CONEXAO =
  "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";

/**
 * O `useAuth` devolve token nulo quando a sessão acabou E quando o servidor de
 * login não respondeu, sem distinguir os dois: a frase nomeia as duas causas e
 * sugere o que resolve ambas (molde da aba Tecnologia).
 */
export const SEM_SESSAO =
  "Não foi possível carregar os números: a sessão não está ativa ou o servidor não respondeu. Tente recarregar a página.";

/**
 * Como a resposta do backend chega à tela:
 *
 * - `nao-configurado`: 503, falta configurar a fonte no backend;
 * - `falhou`: a fonte (ou o backend) respondeu erro.
 *
 * Nos dois casos a frase é a do servidor, que sabe o que houve. A tela não
 * inventa causa, e nunca troca o erro por um zero.
 */
export type Recusa = { tipo: "nao-configurado" | "falhou"; mensagem: string };

export async function lerRecusa(resposta: Response): Promise<Recusa> {
  const tipo = resposta.status === 503 ? "nao-configurado" : "falhou";
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return { tipo, mensagem: corpo.detail };
  } catch {
    // Resposta sem corpo JSON: sobra o status.
  }
  return { tipo, mensagem: `O servidor respondeu ${resposta.status}.` };
}
