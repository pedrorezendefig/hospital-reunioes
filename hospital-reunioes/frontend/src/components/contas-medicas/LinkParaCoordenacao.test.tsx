/**
 * @vitest-environment jsdom
 */

/**
 * O caminho até a tela Coordenação (issue #1143): aparece na tela de contas só
 * para quem tem a Conferência da coordenação, com o número de lembretes
 * abertos. A faturista não vê o link, nem pede os lembretes ao servidor.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkParaCoordenacao } from "./LinkParaCoordenacao";

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
    json: async () =>
      url === "/api/contas-medicas/me"
        ? { perfil: "x", permissoes }
        : { numeros: { lembretes_abertos: 3, contas_com_lembrete: 2, valor_a_conferir: 40 }, contas: [] },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o link para a tela Coordenação", () => {
  it("aparece para quem tem a Conferência da coordenação, com os lembretes abertos", async () => {
    moduloResponde(["enviar_corrigir_contas", "conferencia_coordenacao"]);

    render(<LinkParaCoordenacao />);

    const link = await screen.findByRole("link", { name: /Coordenação/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/coordenacao");
    await waitFor(() => expect(link.textContent).toContain("3"));
  });

  it("não aparece para a faturista, que nem pede os lembretes", async () => {
    const fetch = moduloResponde(["enviar_corrigir_contas"]);

    render(<LinkParaCoordenacao />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Coordenação/ })).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
