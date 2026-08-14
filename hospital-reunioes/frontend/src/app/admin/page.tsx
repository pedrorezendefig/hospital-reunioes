import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

/**
 * Raiz do painel admin — redireciona para a tela default do papel:
 * super admin cai em Usuários; secretária e facilitador caem no Dados do
 * Atendimento (único módulo do papel deles, ADR 0031). O gate de acesso é
 * feito pelo layout; aqui só se escolhe o destino.
 */
export default async function AdminRootPage() {
  const supabase = await createClient();
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
  const me = (await res.json()) as { is_super_admin?: boolean };

  if (me.is_super_admin === true) redirect("/admin/usuarios");
  redirect("/admin/dados-atendimento");
}
