/**
 * @vitest-environment jsdom
 */

/**
 * A Tabela de prazos com a lista de feriados vazia (issue #1629, PRD #1527,
 * regra T7 da especificação da Diretoria): lista vazia diz por que está vazia
 * e o que isso muda.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TabelaDePrazosPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "p1", perfil_ouvidoria: "diretoria_executiva" },
    loading: false,
  }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a lista de feriados vazia", () => {
  it("diz por que está vazia e o que acontece com o prazo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const corpo = String(url).endsWith("/feriados") ? { feriados: [] } : { prazos: [] };
        return { ok: true, status: 200, json: async () => corpo } as Response;
      })
    );

    render(<TabelaDePrazosPage />);

    expect(
      await screen.findByText(
        "Nenhum feriado cadastrado. Enquanto a lista estiver vazia, todo dia de segunda a sexta conta como útil no prazo."
      )
    ).toBeTruthy();
  });
});
