import { requirePainelOuvidoriaAccess } from "@/lib/ouvidoria/guard";

/**
 * O enforcement do painel, no servidor (issue #344).
 *
 * O layout da área da Ouvidoria checa login; este checa o perfil, antes de a
 * página do painel existir. Quem digita a URL sem perfil na Ouvidoria volta
 * para a fila, e não recebe a página para o navegador decidir o que mostrar.
 */
export default async function PainelOuvidoriaLayout({ children }: { children: React.ReactNode }) {
  await requirePainelOuvidoriaAccess();
  return <>{children}</>;
}
