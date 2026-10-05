/**
 * @vitest-environment jsdom
 */

/**
 * A porta da Triagem de e-mail na fila da Ouvidoria (issue #648, ADR 0051).
 *
 * A tela fica ao lado da fila, e só para o Perfil da Ouvidoria. Quem está fora
 * dela abre a fila (a listagem é do time de Reuniões inteiro) e não pode ver a
 * porta: ela terminaria em 403 no servidor.
 *
 * A porta NÃO entra na barra de atalhos: a barra é uma linha só com orçamento
 * de largura travado em `lib/ouvidoria/atalhos` (RN-77), e a sexta pílula não
 * cabe nele. Ela mora ao lado do interruptor do Arquivo, no topo da fila, que
 * quebra linha quando precisa.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "../page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: "ouvidor" as string | null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      perfil_ouvidoria: sessao.perfilOuvidoria,
    },
    loading: false,
  }),
}));

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/responsaveis")) {
        return { ok: true, status: 200, json: async () => ({ responsaveis: [] }) } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ protocolos: [] }) } as Response;
    })
  );
  render(<OuvidoriaPage />);
}

afterEach(async () => {
  await act(async () => {});
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("a porta da Triagem de e-mail no topo da fila", () => {
  it.each(["ouvidor", "diretoria_executiva"])("o perfil %s vê a porta, que leva à triagem", async (perfil) => {
    sessao.perfilOuvidoria = perfil;
    montar();

    const porta = await screen.findByRole("link", { name: "Triagem de e-mail" });
    expect(porta.getAttribute("href")).toBe("/ouvidoria/triagem-email");
  });

  it("quem está fora da Ouvidoria não vê a porta", async () => {
    sessao.perfilOuvidoria = null;
    montar();

    // A fila carregou: a ausência da porta é decisão, e não tela pela metade.
    await screen.findByText(/em andamento/);
    expect(screen.queryByRole("link", { name: "Triagem de e-mail" })).toBeNull();
  });

  it("a porta não entra na barra de atalhos, cujo orçamento de largura é fechado", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar();

    const nav = await screen.findByRole("navigation", { name: /atalhos da ouvidoria/i });
    const porta = await screen.findByRole("link", { name: "Triagem de e-mail" });
    expect(nav.contains(porta)).toBe(false);
  });
});
