import { AppShell } from "@/components/layout/AppShell";
import { requirePopsAccess } from "@/lib/pops/guard";

/**
 * Layout do miolo da área /pops (contexto POPs, ADR 0007): AppShell + gate
 * de acesso (extraído para lib/pops/guard). Telas dedicadas full-screen
 * (ex.: elaboração, padrão Ata Guiada) vivem fora deste route group e
 * aplicam o mesmo gate sem o shell.
 */
export default async function PopsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = await requirePopsAccess();

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
