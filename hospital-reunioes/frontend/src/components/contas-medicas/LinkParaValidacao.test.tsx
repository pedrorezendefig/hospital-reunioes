/**
 * @vitest-environment jsdom
 */

/**
 * O caminho até a fila de Validação (issue #1142): aparece na tela de contas
 * só para quem decide na validação. A faturista não vê um link que daria
 * numa recusa.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkParaValidacao } from "./LinkParaValidacao";

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

describe("o link para a fila de Validação", () => {
  it("aparece para quem decide na validação", async () => {
    moduloResponde(["enviar_corrigir_contas", "decidir_validacao"]);

    render(<LinkParaValidacao />);

    const link = await screen.findByRole("link", { name: /Validação/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/validacao");
  });

  it("não aparece para a faturista nem para a coordenadora", async () => {
    const fetch = moduloResponde(["enviar_corrigir_contas", "painel_completo", "conferencia_coordenacao"]);

    render(<LinkParaValidacao />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Validação/ })).toBeNull();
  });
});
