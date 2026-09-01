import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/layout/AppShell";
import { RedirecionarParaLogin } from "@/components/auth/RedirecionarParaLogin";

export default async function OuvidoriaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Sem sessão, a área não monta: o que volta é o encaminhamento para o login,
  // no LUGAR dos filhos (issue #477, RN-54). Ele leva o endereço pedido junto,
  // para a pessoa cair no caso que tentou abrir em vez de na tela inicial.
  if (!user) return <RedirecionarParaLogin />;

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
