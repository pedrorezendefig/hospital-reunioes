/**
 * @vitest-environment jsdom
 */

/**
 * A fila de triagem do Núcleo (issue #1992).
 *
 * A ordem é a do servidor (da mais antiga para a mais nova). A tela mostra o
 * protocolo, a faixa sugerida, o setor e o assunto, e leva à tela do caso. A
 * notificação sem sugestão aparece como "Classificar manualmente".
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FilaDeTriagem } from "./FilaDeTriagem";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

let corpo: unknown;

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => corpo }) as Response)
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BASE = {
  criado_em: "2026-11-10T13:00:00+00:00",
  data_ocorrencia: "2026-11-09",
  setor: "UTI Adulto",
  grave_ou_morte: null,
  classificar_manualmente: false,
};

describe("a fila de triagem", () => {
  it("mostra cada caso na ordem do servidor, com a faixa sugerida, e leva à tela do caso", async () => {
    corpo = {
      fila: [
        { ...BASE, id: "a", protocolo: "NSP-2026-0002", faixa: "A", assunto: "Queda com óbito" },
        { ...BASE, id: "b", protocolo: "NSP-2026-0005", faixa: "C", assunto: "Erro de dose" },
      ],
    };
    render(<FilaDeTriagem />);

    const itens = await screen.findAllByRole("listitem");
    expect(itens.map((i) => within(i).getByRole("link").textContent)).toEqual([
      expect.stringContaining("NSP-2026-0002"),
      expect.stringContaining("NSP-2026-0005"),
    ]);
    expect(within(itens[0]).getByText("Faixa A")).toBeTruthy();
    expect(within(itens[0]).getByText("Queda com óbito")).toBeTruthy();
    expect(within(itens[0]).getByText(/UTI Adulto/)).toBeTruthy();
    expect(within(itens[0]).getByRole("link").getAttribute("href")).toBe(
      "/seguranca-do-paciente/notificacoes/a/triagem"
    );
  });

  it("a notificação sem sugestão aparece para classificar manualmente", async () => {
    corpo = {
      fila: [{ ...BASE, id: "m", protocolo: "NSP-2026-0003", faixa: null, assunto: null, classificar_manualmente: true }],
    };
    render(<FilaDeTriagem />);

    expect(await screen.findByText("Classificar manualmente")).toBeTruthy();
  });

  it("sem nada esperando, diz que a fila está vazia", async () => {
    corpo = { fila: [] };
    render(<FilaDeTriagem />);

    expect(await screen.findByText("Nenhuma notificação esperando a triagem.")).toBeTruthy();
  });
});
