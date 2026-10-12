/**
 * @vitest-environment jsdom
 */

/**
 * O caminho até a tela Operadoras (issue #1119): aparece na tela de contas só
 * para quem tem a permissão de regra contratual e tabelas. A faturista não vê
 * um link que daria numa recusa.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkParaOperadoras } from "./LinkParaOperadoras";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

function moduloResponde(permissoes: string[]) {
  const fetch = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () => (url === "/api/contas-medicas/me" ? { perfil: "x", permissoes } : {}),
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o link para a tela Operadoras", () => {
  it("aparece para quem tem regra contratual e tabelas", async () => {
    moduloResponde(["enviar_corrigir_contas", "regra_contratual_tabelas"]);

    render(<LinkParaOperadoras />);

    const link = await screen.findByRole("link", { name: /Operadoras/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/operadoras");
  });

  it("não aparece para a faturista", async () => {
    const fetch = moduloResponde(["enviar_corrigir_contas"]);

    render(<LinkParaOperadoras />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Operadoras/ })).toBeNull();
  });
});
