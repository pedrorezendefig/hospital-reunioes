/**
 * @vitest-environment jsdom
 */

/**
 * O item Habilitação no menu do módulo (issue #1139): aparece na tela de
 * contas só para quem tem a permissão de habilitar pessoas. A coordenadora
 * não vê um link que daria numa recusa.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ContasMedicasPage from "@/app/contas-medicas/page";

import { LinkParaHabilitacao } from "./LinkParaHabilitacao";

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
    json: async () => {
      if (url === "/api/contas-medicas/me") return { perfil: "x", permissoes };
      if (url === "/api/contas-medicas/fila") return { fila: [], concluidas: [] };
      return {};
    },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o link para a tela de Habilitação", () => {
  it("aparece para quem tem habilitar pessoas", async () => {
    moduloResponde(["enviar_corrigir_contas", "habilitar_pessoas"]);

    render(<LinkParaHabilitacao />);

    const link = await screen.findByRole("link", { name: /Habilitação/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/habilitacao");
  });

  it("não aparece para a coordenadora, que tem o painel mas não habilita", async () => {
    const fetch = moduloResponde(["enviar_corrigir_contas", "painel_completo", "conferencia_coordenacao"]);

    render(<LinkParaHabilitacao />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Habilitação/ })).toBeNull();
  });

  it("fica no cabeçalho da tela de contas, depois de Operadoras", async () => {
    moduloResponde(["regra_contratual_tabelas", "habilitar_pessoas"]);

    render(<ContasMedicasPage />);

    await screen.findByRole("link", { name: /Habilitação/ });
    const links = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(links.indexOf("/contas-medicas/habilitacao")).toBe(links.indexOf("/contas-medicas/operadoras") + 1);
  });
});
