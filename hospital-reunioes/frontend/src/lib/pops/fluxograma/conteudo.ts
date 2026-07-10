/**
 * Helpers para o `conteudo` de uma seção de POP, que na seção `tipo=fluxograma`
 * pode ser objeto JSON (gramática do ADR 0024) ou string (Mermaid legado, ou
 * JSON serializado quando o objeto saiu fora da gramática). Espelha o
 * `secao_tem_conteudo` do backend.
 */

import type { SecaoPop } from "@/types";

/** Seção com conteúdo de verdade: string não em branco, ou objeto não vazio. */
export function secaoTemConteudo(conteudo: SecaoPop["conteudo"]): boolean {
  if (typeof conteudo === "string") return conteudo.trim().length > 0;
  return conteudo != null && Object.keys(conteudo).length > 0;
}
