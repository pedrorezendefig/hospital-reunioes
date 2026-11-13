import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";

/** O manual mora atrás do login (ADR 0094, decisão 1), na casca do app. */
export default async function ManualLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

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
