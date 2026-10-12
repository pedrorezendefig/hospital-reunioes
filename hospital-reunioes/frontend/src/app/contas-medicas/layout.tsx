import { AppShell } from "@/components/layout/AppShell";
import { requireContasMedicasAccess } from "@/lib/contas-medicas/guard";

/**
 * Layout da área /contas-medicas (ADR 0070): AppShell e o gate do módulo no
 * servidor, antes de a página existir. Quem não tem perfil no módulo (nem é
 * super admin) volta ao início; a API do módulo recusa o mesmo com 403.
 */
export default async function ContasMedicasLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = await requireContasMedicasAccess();

  const nome =
    (user.user_metadata?.nome as string) ||
    user.email?.split("@")[0] ||
    "Usuário";

  return (
    <AppShell userName={nome} userEmail={user.email}>
      {children}
    </AppShell>
  );
}
