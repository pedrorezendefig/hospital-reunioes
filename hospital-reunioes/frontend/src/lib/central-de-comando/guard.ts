// Imports relativos, e não pelo alias `@/`, como no guard da Ouvidoria: é o
// jeito de este gate ter teste com o `vi.mock` do cliente do Supabase.
import { redirect } from "next/navigation";
import { isSuperAdmin, type AuthUser } from "../auth";
import { createClient } from "../supabase/server";

/**
 * Gate server-side da seção Central de Comando (ADR 0058, decisão 1).
 *
 * Secretária e facilitador entram em `/admin` (o Dados do Atendimento é
 * deles), e o layout da área admin deixa. A sidebar só esconde a seção, e
 * esconder não é proteger: sem este gate, quem digitasse o endereço de uma
 * tela da Central receberia a página e o navegador decidiria o que mostrar.
 * Aqui a decisão é do servidor, antes de a página existir, e quem não é Super
 * admin volta para o início.
 *
 * O papel é lido do backend (`/api/participantes/me`), fonte única do papel
 * de quem está logado. O gate dos NÚMEROS continua sendo o
 * `require_super_admin` do router da Central: este impede a PÁGINA.
 */
export async function requireSuperAdminNaCentral() {
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
  // Falha de leitura do papel não pode abrir a porta: sem saber quem é, a
  // resposta é o início.
  if (!res.ok) redirect("/dashboard");
  const me = (await res.json()) as AuthUser;
  if (!isSuperAdmin(me)) redirect("/dashboard");

  return { user };
}
