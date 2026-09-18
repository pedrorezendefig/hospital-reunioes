/**
 * A Central de Comando nasce dormente (ADR 0058, decisão 8).
 *
 * Cada fatia do PRD #809 sobe para a `main` e para produção, mas a seção só
 * entra no menu fora de produção, onde o Pedro confere com dado real. A última
 * fatia (issue #827) liga tudo de uma vez: apaga este arquivo e a marca
 * `dormente` da seção na `AdminSidebar`.
 *
 * Esconder do menu não é proteger: o gate é o `require_super_admin` do router
 * da Central e o guard do `layout.tsx` da seção. Isto decide só se a seção
 * aparece.
 */
export function centralDeComandoNoMenu(): boolean {
  // Sem a variável, vale produção: o padrão é o ambiente mais restrito, como
  // no backend (issue #450). Uma build de produção que perdesse a variável não
  // mostra a Central antes da hora. A leitura é `process.env.NEXT_PUBLIC_*`
  // literal de propósito: é esse o formato que o Next grava no bundle.
  const ambiente = process.env.NEXT_PUBLIC_ENVIRONMENT || "production";
  return ambiente !== "production";
}
