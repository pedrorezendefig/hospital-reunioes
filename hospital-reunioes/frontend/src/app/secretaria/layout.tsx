import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";

/**
 * Layout da área da secretária.
 *
 * Proteção:
 * - Sem user, redireciona pra /login.
 * - Usuário autenticado que não é secretária, redireciona pra /dashboard.
 *
 * Fonte de verdade: GET /api/participantes/me que retorna access_profile.
 */
export default async function SecretariaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) redirect("/login");

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const res = await fetch(`${apiBase}/participantes/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) redirect("/dashboard");
  const me = (await res.json()) as {
    access_profile?: "regular" | "secretaria" | "super_admin";
    is_super_admin?: boolean;
  };
  if (me.access_profile !== "secretaria") redirect("/dashboard");

  const nome =
    (user.user_metadata?.nome as string) ||
    user.email?.split("@")[0] ||
    "Secretária";

  return (
    <AppShell userName={nome} userEmail={user.email} variant="secretaria">
      {children}
    </AppShell>
  );
}
