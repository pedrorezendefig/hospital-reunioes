/**
 * O gate server-side da área /contas-medicas (issue #1114, ADR 0070).
 *
 * Esconder o item do menu não basta: quem digita o endereço sem perfil no
 * módulo não pode receber a página. A decisão é do servidor e tem uma fonte só,
 * o `/api/contas-medicas/me`, que já sabe do eixo, da matriz e do super admin.
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
      getSession: async () => ({ data: { session: token ? { access_token: token } : null } }),
    },
  }),
}));

import { requireContasMedicasAccess } from "./guard";

/**
 * O backend: só a rota do módulo responde pelo eixo. Qualquer outra URL
 * devolve 200 de propósito, para um gate que perguntasse a outra rota entrar
 * com quem o módulo recusa e o teste ficar vermelho.
 */
function backendResponde(statusDoModulo: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const doModulo = String(url).endsWith("/contas-medicas/me");
      const status = doModulo ? statusDoModulo : 200;
      return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => (doModulo ? { perfil: "faturista", permissoes: ["enviar_corrigir_contas"] } : {}),
      };
    }),
  );
}

async function tentarEntrar(): Promise<"entrou" | string> {
  try {
    await requireContasMedicasAccess();
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

describe("quem o servidor deixa entrar em Contas médicas", () => {
  it("deixa entrar quem o módulo reconhece", async () => {
    backendResponde(200);

    expect(await tentarEntrar()).toBe("entrou");
  });

  it("devolve ao início quem o módulo recusa com 403", async () => {
    backendResponde(403);

    expect(await tentarEntrar()).toBe("/dashboard");
  });

  it("sem sessão, manda para o login", async () => {
    backendResponde(200);
    usuario = null;

    expect(await tentarEntrar()).toBe("/login");
  });
});
