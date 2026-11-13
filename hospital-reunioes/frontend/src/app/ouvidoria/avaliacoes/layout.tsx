import { requirePainelOuvidoriaAccess } from "@/lib/ouvidoria/guard";

/**
 * O enforcement da aba Avaliações, no servidor (issue #1626, ADR 0086 decisão
 * 8): os mesmos dois perfis do painel. Quem digita a URL sem perfil na
 * Ouvidoria, inclusive o super admin, volta para a fila.
 */
export default async function AvaliacoesOuvidoriaLayout({ children }: { children: React.ReactNode }) {
  await requirePainelOuvidoriaAccess();
  return <>{children}</>;
}
