import { requirePainelOuvidoriaAccess } from "@/lib/ouvidoria/guard";

/**
 * O enforcement da Triagem de e-mail, no servidor (issue #648, ADR 0051).
 *
 * O layout da área da Ouvidoria checa login; este checa o perfil antes de a
 * página existir. O gate é o mesmo do painel porque os perfis são os mesmos:
 * `ouvidor` e `diretoria_executiva`, Super admin de fora. Quem digita a URL
 * sem perfil volta para a fila. O backend recusa a lista e o item com 403 de
 * qualquer jeito: esta guarda é a que impede a PÁGINA de existir.
 */
export default async function TriagemDeEmailLayout({ children }: { children: React.ReactNode }) {
  await requirePainelOuvidoriaAccess();
  return <>{children}</>;
}
