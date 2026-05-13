/**
 * Extrai uma mensagem legível de qualquer valor capturado em `catch (err: unknown)`.
 *
 * Trata os três casos que aparecem no projeto:
 *   1. `Error` (e subclasses, incluindo TypeError, fetch network errors).
 *   2. string lançada diretamente (raro mas possível).
 *   3. valores arbitrários (objetos JSON da API, números, etc.).
 *
 * Quando o motivo do catch importa, prefira esse helper a `String(err)` ou
 * `(err as Error).message`, que perdem informação ou mascaram bugs de tipo.
 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return "Erro desconhecido";
  }
}
