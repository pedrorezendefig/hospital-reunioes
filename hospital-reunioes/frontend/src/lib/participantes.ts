/**
 * Busca o roster COMPLETO de participantes ativos, paginando o endpoint
 * `/api/participantes` (que tem teto de 200 por página). Existe porque vários
 * callers precisam de todos os participantes de uma vez (MultiSelects de
 * responsável, filtros, contadores) e não de uma busca por nome. Carregar só a
 * primeira página truncava o roster no `limit` default (50) e sumia com quem
 * ordena na cauda do alfabeto (incidente "não acho a Uliandra no seletor").
 *
 * Para busca incremental por nome (digite e ache), use `useBuscaParticipantes`.
 */
export async function fetchParticipantesAtivos<T = { id: string; nome_completo: string }>(
  token: string,
): Promise<T[]> {
  const PAGINA = 200; // teto por requisição no backend (Query(le=200))
  const todos: T[] = [];
  for (let offset = 0; ; offset += PAGINA) {
    const params = new URLSearchParams({
      ativo: "true",
      limit: String(PAGINA),
      offset: String(offset),
    });
    const res = await fetch(`/api/participantes?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Falha ao listar participantes (${res.status})`);
    const pagina = (await res.json()) as T[];
    if (!Array.isArray(pagina) || pagina.length === 0) break;
    todos.push(...pagina);
    if (pagina.length < PAGINA) break; // última página
  }
  return todos;
}
