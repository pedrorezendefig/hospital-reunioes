import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Se for secretária, redireciona pra área dela. Apura o flag dentro do try
  // pra não capturar o NEXT_REDIRECT que o redirect() lança.
  let isSecretariaProfile = false;
  let isPopsOnly = false;
  try {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (token) {
      const apiBase =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
      const res = await fetch(`${apiBase}/participantes/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (res.ok) {
        const me = (await res.json()) as {
          access_profile?: "regular" | "secretaria" | "super_admin" | null;
          perfil_pop?: string | null;
        };
        isSecretariaProfile = me.access_profile === "secretaria";
        // Quem só tem perfil POP (access_profile NULL) vive em /pops (ADR 0007).
        isPopsOnly = me.access_profile == null && Boolean(me.perfil_pop);
      }
    }
  } catch {
    // se falhar (rede, backend offline), segue com /dashboard padrão
  }
  if (isSecretariaProfile) redirect("/secretaria");
  if (isPopsOnly) redirect("/pops");

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
