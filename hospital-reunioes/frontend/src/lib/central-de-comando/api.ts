/**
 * A conversa das telas da Central de Comando com o backend (ADR 0058).
 *
 * Cada tela pede o payload inteiro dela a um caminho relativo (`/api/...`),
 * com o token da sessão, e guarda a resposta em estado local: sem biblioteca
 * de cache (PRD #809). O que mora aqui é o que toda tela da Central repete.
 */

export const BASE_CENTRAL = "/api/admin/central-de-comando";

/**
 * As telas que passam pelo cache com frescor do backend (issue #815): a
 * leitura é `GET {BASE_CENTRAL}/{tela}?periodo=` e o Atualizar agora é
 * `POST {BASE_CENTRAL}/atualizar-agora?tela=&periodo=`. Tela nova entra aqui
 * e no registro de telas do backend, como Dados do Google na #817.
 *
 * A lente de um Objetivo é `objetivos/{id}` (issue #861): o mesmo caminho da
 * leitura dela, que o Atualizar agora do backend também reconhece.
 */
export type TelaDaCentral = "visao-geral" | "dados-do-google" | "instagram" | `objetivos/${string}`;

/**
 * O Atualizar agora tem limite de taxa no backend. O 429 do `slowapi` chega
 * sem `detail` (`{"error": ...}`, em inglês): a frase é da tela.
 */
export const MUITAS_ATUALIZACOES = "Muitas atualizações em pouco tempo. Espere um minuto e tente de novo.";

/**
 * O bloco `frescor` que todo payload de tela traz (issue #815): de quando são
 * os números (ISO 8601, com fuso) e se a última tentativa de renová-los
 * falhou, com a frase do porquê. Quando falhou, os números são o último valor
 * bom, e `atualizado_em` é a hora dele. Nulo quando o backend não tem hora
 * nenhuma registrada (o contrato admite; a leitura de uma tela sempre tem).
 */
export type Frescor = {
  atualizado_em: string | null;
  atualizacao_falhou: boolean;
  motivo: string | null;
};

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
 * - `nao-configurado`: 503 COM a frase do backend no `detail`, que é como o
 *   router da Central diz que falta configurar a fonte;
 * - `falhou`: todo o resto, inclusive o 503 cru de um proxy no meio de um
 *   deploy, que não é falta de configuração nenhuma.
 *
 * A frase mostrada é a do servidor, que sabe o que houve. A tela não inventa
 * causa, e nunca troca o erro por um zero.
 */
export type Recusa = { tipo: "nao-configurado" | "falhou"; mensagem: string };

export async function lerRecusa(resposta: Response): Promise<Recusa> {
  let frase: string | null = null;
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") frase = corpo.detail;
  } catch {
    // Resposta sem corpo JSON: sobra o status.
  }
  if (resposta.status === 503 && frase) return { tipo: "nao-configurado", mensagem: frase };
  return { tipo: "falhou", mensagem: frase ?? `O servidor respondeu ${resposta.status}.` };
}
