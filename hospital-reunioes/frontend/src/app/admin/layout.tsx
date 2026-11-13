import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";
import { RedirecionarParaLogin } from "@/components/auth/RedirecionarParaLogin";

/**
 * Layout do painel /admin.
 *
 * Protecao:
 * - Sem user -> /login (com retorno so na aba Tecnologia, issue #1587).
 * - User sem papel no contexto Reunioes (access_profile NULL) -> /dashboard.
 *
 * Quem tem papel entra: o modulo Dados do Atendimento (ADR 0031) e lido por
 * facilitadores e editado por secretarias. Os demais modulos seguem restritos
 * a super admin no backend (403) e a sidebar so os mostra a super admins.
 *
 * O participante e lido via backend (/api/participantes/me), que roda
 * com service_role e bypassa RLS. Consulta direta a tabela participantes via
 * anon client seria bloqueada pelo default-deny da migration 009.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  // Sem sessão, o encaminhador vai no LUGAR dos filhos: ele lê o endereço no
  // navegador e deixa o link de um pedido da aba Tecnologia voltar a ele depois
  // do login (issue #1587); o resto do admin vai para o login limpo.
  if (!user) return <RedirecionarParaLogin />;

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) return <RedirecionarParaLogin />;

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const res = await fetch(`${apiBase}/participantes/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) redirect("/dashboard");
  const me = (await res.json()) as {
    is_super_admin?: boolean;
    access_profile?: "regular" | "secretaria" | "super_admin" | null;
  };
  if (!me.access_profile && me.is_super_admin !== true) redirect("/dashboard");

  const nome =
    (user.user_metadata?.nome as string) ||
    user.email?.split("@")[0] ||
    "Usuário";

  return (
    <AppShell userName={nome} userEmail={user.email} variant="admin">
      {children}
    </AppShell>
  );
}
