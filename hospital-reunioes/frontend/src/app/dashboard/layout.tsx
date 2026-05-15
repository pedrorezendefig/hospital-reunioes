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
          access_profile?: "regular" | "secretaria" | "super_admin";
        };
        isSecretariaProfile = me.access_profile === "secretaria";
      }
    }
  } catch {
    // se falhar (rede, backend offline), segue com /dashboard padrão
  }
  if (isSecretariaProfile) redirect("/secretaria");

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
