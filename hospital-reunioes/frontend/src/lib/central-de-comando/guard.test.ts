/**
 * O guard server-side da seção Central de Comando (issue #814, ADR 0058).
 *
 * Secretária e facilitador entram em `/admin` (o Dados do Atendimento é deles),
 * então esconder a seção do menu não basta: quem digita o endereço de uma tela
 * da Central tem de ser levado de volta ao início antes de a página existir.
 * Mesmo desenho do guard do painel da Ouvidoria (`lib/ouvidoria/guard.ts`).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

/** O `redirect` do Next interrompe o fluxo lançando; o dublê faz o mesmo. */
class RedirecionouError extends Error {}

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => {
    throw new RedirecionouError(destino);
  },
}));

let usuario: { id: string } | null = { id: "u1" };
let token: string | null = "jwt-de-teste";

vi.mock("../supabase/server", () => ({
  createClient: async () => ({
    auth: {
      getUser: async () => ({ data: { user: usuario } }),
      getSession: async () => ({
        data: { session: token ? { access_token: token } : null },
      }),
    },
  }),
}));

import { requireSuperAdminNaCentral } from "./guard";

/** O `/api/participantes/me`, fonte única do papel de quem está logado. */
function respondeMe(corpo: Record<string, unknown>, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => corpo })),
  );
}

async function tentarEntrar(): Promise<"entrou" | string> {
  try {
    await requireSuperAdminNaCentral();
    return "entrou";
  } catch (e) {
    if (e instanceof RedirecionouError) return e.message;
    throw e;
  }
}

beforeEach(() => {
  usuario = { id: "u1" };
  token = "jwt-de-teste";
});

describe("quem o servidor deixa entrar na Central de Comando", () => {
  it("deixa passar o Super admin", async () => {
    respondeMe({ access_profile: "super_admin", is_super_admin: true });
    expect(await tentarEntrar()).toBe("entrou");
  });

  it("deixa passar o Super admin do cadastro antigo, só com a flag", async () => {
    // Fase 1 da migração 035: sem `access_profile`, vale a flag legada.
    respondeMe({ is_super_admin: true });
    expect(await tentarEntrar()).toBe("entrou");
  });

  it("devolve ao início a secretária que digitou o endereço", async () => {
    respondeMe({ access_profile: "secretaria", is_super_admin: false });
    expect(await tentarEntrar()).toBe("/dashboard");
  });

  it("devolve ao início o facilitador que digitou o endereço", async () => {
    respondeMe({ access_profile: "regular", is_super_admin: false });
    expect(await tentarEntrar()).toBe("/dashboard");
  });

  it("o papel de hoje vale mais que a flag antiga", async () => {
    respondeMe({ access_profile: "secretaria", is_super_admin: true });
    expect(await tentarEntrar()).toBe("/dashboard");
  });

  it("não abre a porta quando o papel não pôde ser lido", async () => {
    // Falha de leitura não é permissão: sem saber quem é, a resposta é o início.
    respondeMe({ access_profile: "super_admin" }, false);
    expect(await tentarEntrar()).toBe("/dashboard");
  });

  it("manda para o login quem não tem sessão", async () => {
    respondeMe({ access_profile: "super_admin" });

    usuario = null;
    expect(await tentarEntrar()).toBe("/login");

    usuario = { id: "u1" };
    token = null;
    expect(await tentarEntrar()).toBe("/login");
  });
});
