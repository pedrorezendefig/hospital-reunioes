import { AppShell } from "@/components/layout/AppShell";
import { requireConfiguracoesDoCanalAccess } from "@/lib/conduta/guard";

/**
 * Layout da tela Configurações do Canal de Conduta (issue #1826): AppShell e
 * o gate no servidor, antes de a página existir. Quem não é a coordenação
 * vigente do Comitê, o super admin inclusive, volta ao início.
 *
 * Fica fora do grupo `(comite)`, como a tela Membros: o portão dos casos pede
 * a chave de cifra e deixa entrar todo membro, e esta tela é só da coordenação.
 */
export default async function ConfiguracoesDoCanalLayout({ children }: { children: React.ReactNode }) {
  const { user } = await requireConfiguracoesDoCanalAccess();

  const nome = (user.user_metadata?.nome as string) || user.email?.split("@")[0] || "Usuário";

  return (
    <AppShell userName={nome} userEmail={user.email}>
      {children}
    </AppShell>
  );
}
