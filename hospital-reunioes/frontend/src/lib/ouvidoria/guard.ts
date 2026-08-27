// Imports relativos, e não pelo alias `@/`: o vitest do projeto roda sem
// config, e é por eles que este gate consegue ter teste.
import { redirect } from "next/navigation";
import { createClient } from "../supabase/server";
import { PERFIS_DO_PAINEL } from "./painel";

/**
 * Gate server-side do painel em tempo real da Ouvidoria (issue #344, ADR 0034).
 *
 * Mesmo desenho do gate da área /pops (`lib/pops/guard.ts`): o perfil é lido do
 * backend (`/api/participantes/me`), que é a fonte única dos eixos de permissão,
 * e a decisão acontece no servidor, antes de a página existir.
 *
 * Existe porque o critério "demais papéis não veem o painel" não pode ser
 * sustentado por um `if` no navegador. O layout da área da Ouvidoria checa
 * LOGIN, e a listagem que alimenta a tela é aberta ao time de Reuniões inteiro
 * (`require_acesso_painel`): quem tem qualquer `access_profile` passa lá e não
 * passaria aqui. Sem esta guarda, o painel herdaria o gate de outra tela.
 *
 * O gate do `/metricas` no backend continua sendo o que impede o dado agregado
 * de sair (`require_perfil_ouvidoria`, sem bypass de super admin). Esta guarda
 * é a que impede a PÁGINA de existir para quem não é da Ouvidoria.
 */
export async function requirePainelOuvidoriaAccess() {
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
  // Falha de leitura do perfil não pode abrir a porta: sem saber quem é, a
  // resposta é a fila da Ouvidoria, que é onde a pessoa já estava.
  if (!res.ok) redirect("/ouvidoria");
  const me = (await res.json()) as { perfil_ouvidoria?: string | null };
  if (!PERFIS_DO_PAINEL.includes(String(me.perfil_ouvidoria))) redirect("/ouvidoria");

  return { user };
}
