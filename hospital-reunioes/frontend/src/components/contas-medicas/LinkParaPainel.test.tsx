/**
 * @vitest-environment jsdom
 */

/**
 * O caminho até o Painel (issue #1137): aparece na tela de contas para quem
 * tem o Painel completo e para quem envia e corrige contas, que no Painel vê
 * só a própria linha de produção. O credenciamento, que só vê contratos, não
 * recebe um link para um Painel vazio.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkParaPainel } from "./LinkParaPainel";

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

describe("o link para o Painel", () => {
  it("aparece para quem tem o Painel completo", async () => {
    moduloResponde(["painel_completo"]);

    render(<LinkParaPainel />);

    const link = await screen.findByRole("link", { name: /Painel/ });
    expect(link.getAttribute("href")).toBe("/contas-medicas/painel");
  });

  it("aparece para a faturista, que vê a própria produção", async () => {
    moduloResponde(["enviar_corrigir_contas"]);

    render(<LinkParaPainel />);

    expect(await screen.findByRole("link", { name: /Painel/ })).toBeTruthy();
  });

  it("não aparece para o credenciamento", async () => {
    const fetch = moduloResponde(["contratos_avisos"]);

    render(<LinkParaPainel />);

    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/contas-medicas/me", expect.anything()));
    expect(screen.queryByRole("link", { name: /Painel/ })).toBeNull();
  });
});
