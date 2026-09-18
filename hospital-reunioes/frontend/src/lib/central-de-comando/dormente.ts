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

/**
 * Os ambientes em que a seção já aparece: os que o backend conhece fora de
 * produção (`AMBIENTES_CONHECIDOS` em `app/config.py`). A lista é do que MOSTRA,
 * e não do que esconde, de propósito: qualquer outro valor conta como
 * produção, inclusive a variável ausente, vazia ou digitada de outro jeito no
 * Coolify ("prod", "Production"). É o padrão mais restrito do backend (issue
 * #450) aplicado aqui: um erro de digitação não mostra a Central antes da hora.
 */
const FORA_DE_PRODUCAO = ["development", "ci", "staging"];

export function centralDeComandoNoMenu(): boolean {
  // A leitura é `process.env.NEXT_PUBLIC_*` literal de propósito: é esse o
  // formato que o Next grava no bundle na hora do build.
  return FORA_DE_PRODUCAO.includes(process.env.NEXT_PUBLIC_ENVIRONMENT ?? "");
}
