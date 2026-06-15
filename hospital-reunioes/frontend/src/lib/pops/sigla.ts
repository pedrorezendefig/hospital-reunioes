/**
 * Palavras sem carga semântica (preposições, artigos, conjunção "e") que não
 * entram na sigla de um Setor. Ex.: o "de" de "Centro de Terapia Intensiva".
 */
const PALAVRAS_IGNORADAS = new Set([
  "de",
  "da",
  "do",
  "das",
  "dos",
  "e",
  "a",
  "o",
  "as",
  "os",
  "em",
  "no",
  "na",
  "nos",
  "nas",
  "para",
  "por",
  "com",
]);

/**
 * Sugere a sigla de um Setor a partir do nome: iniciais das palavras
 * significativas (ignora preposições/artigos), em maiúsculas e sem acento.
 *
 * Ex.: "Centro de Terapia Intensiva" → "CTI"; "Centro Cirúrgico" → "CC".
 *
 * É apenas pré-preenchimento de UX: a sigla permanece editável e segue sendo
 * a base do Código travado do POP (HSM_SIGLA-NNN), de responsabilidade do
 * `pops_setores`. Não normaliza nem alimenta de volta a taxonomia de Reuniões.
 */
export function sugerirSigla(nome: string): string {
  const palavras = nome.trim().split(/\s+/).filter(Boolean);
  const significativas = palavras.filter(
    (palavra) => !PALAVRAS_IGNORADAS.has(palavra.toLowerCase()),
  );
  // Nome formado só por palavras ignoradas é atípico; cai de volta para todas
  // elas em vez de devolver sigla vazia.
  const base = significativas.length > 0 ? significativas : palavras;

  return base
    .map((palavra) => removerAcentos(palavra).charAt(0).toUpperCase())
    .join("");
}

/** Remove os diacríticos de uma string (decompõe em NFD e tira as marcas). */
function removerAcentos(texto: string): string {
  return texto.normalize("NFD").replace(/\p{Mn}/gu, "");
}
