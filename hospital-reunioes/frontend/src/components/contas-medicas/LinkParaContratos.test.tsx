/**
 * @vitest-environment jsdom
 */

/**
 * O caminho até a tela Contratos (issue #1144): aparece na tela de contas só
 * para quem tem a permissão de contratos e avisos, inclusive o credenciamento,
 * que não tem nenhuma outra. A faturista não vê um link que daria numa recusa.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkParaContratos } from "./LinkParaContratos";

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

describe("o link para a tela Contratos", () => {
  it("aparece para o credenciamento, que só tem contratos e avisos", async () => {
    moduloResponde(["contratos_avisos"]);

    render(<LinkParaContratos />);

    const link = await screen.findByRole("link", { name: /Contratos/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/contratos");
  });

  it("não aparece para a faturista", async () => {
    const fetch = moduloResponde(["enviar_corrigir_contas", "regra_contratual_tabelas"]);

    render(<LinkParaContratos />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Contratos/ })).toBeNull();
  });
});
