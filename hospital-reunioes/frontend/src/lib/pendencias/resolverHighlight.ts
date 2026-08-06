/**
 * Resolve o `?highlight=<id_acao>` vindo do clique numa notificação (issue #270).
 *
 * Primeiro procura nas pendências já carregadas no board; se não estiver lá
 * (board truncado, filtrado ou vazio), busca no backend via `buscar`. Quando o
 * backend nega (excluída ou sem acesso), sinaliza para a UI avisar em vez de
 * falhar em silêncio.
 */
export type ResolucaoHighlight<T> = { acao: "abrir"; pendencia: T } | { acao: "nao-encontrada" };

export async function resolverHighlight<T extends { id_acao: string }>(
  highlightId: string,
  carregadas: T[],
  buscar: (id_acao: string) => Promise<T | null>,
): Promise<ResolucaoHighlight<T>> {
  const local = carregadas.find((p) => p.id_acao === highlightId);
  if (local) {
    return { acao: "abrir", pendencia: local };
  }

  const remota = await buscar(highlightId);
  if (remota) {
    return { acao: "abrir", pendencia: remota };
  }
  return { acao: "nao-encontrada" };
}
