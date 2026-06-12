import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";

/**
 * Layout da área /pops (contexto POPs, ADR 0007).
 *
 * Proteção:
 * - Sem user -> /login.
 * - User autenticado sem perfil_pop -> /dashboard (403 silencioso) —
 *   Facilitador sem perfil POP não vê /pops.
 *
 * O perfil é lido via backend (/api/participantes/me), fonte única de
 * verdade dos dois eixos de permissão (access_profile e perfil_pop).
 */
export default async function PopsLayout({
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
  const me = (await res.json()) as { perfil_pop?: string | null };
  if (!me.perfil_pop) redirect("/dashboard");

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
