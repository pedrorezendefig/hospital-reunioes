// Imports relativos, e não pelo alias `@/`: o vitest do projeto roda sem
// config, e é por eles que este gate consegue ter teste.
import { redirect } from "next/navigation";
import { createClient } from "../supabase/server";

/**
 * Gate server-side da área /contas-medicas (issue #1114, ADR 0070).
 *
 * Mesmo desenho do gate da área /pops (`lib/pops/guard.ts`), com uma diferença:
 * a pergunta vai ao `/api/contas-medicas/me`, e não ao `/participantes/me`.
 * É a rota do próprio módulo que sabe quem entra (o eixo, a matriz e o super
 * admin, que passa em todos os módulos); repetir a regra aqui seria ter duas.
 *
 * Quem o módulo recusa (403) volta ao início, sem receber a página.
 */
export async function requireContasMedicasAccess() {
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
  const res = await fetch(`${apiBase}/contas-medicas/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  // Falha de leitura também fecha a porta: sem saber quem é, ninguém entra.
  if (!res.ok) redirect("/dashboard");

  return { user };
}
