/**
 * @vitest-environment jsdom
 */

/**
 * A tela de Nota externa depois da issue #1619 (ADR 0089): a nota do Google é
 * lida sozinha toda semana e aparece só para leitura, sem campo nem botão. O
 * Reclame Aqui continua digitado pelo ouvidor.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import NotaExternaPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "p1", nome_completo: "Marta Ouvidora", perfil_ouvidoria: "ouvidor" },
    loading: false,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const NOTAS = {
  notas: [
    {
      fonte: "google",
      nota: 2.5,
      escala: 5,
      registrada_em: "2026-11-16T09:45:00+00:00",
      registrada_por_nome: "",
      origem: "automatica",
      total_avaliacoes: 1629,
    },
    {
      fonte: "reclame_aqui",
      nota: 7.8,
      escala: 10,
      registrada_em: "2026-11-03T12:00:00+00:00",
      registrada_por_nome: "Marta Ouvidora",
      origem: "manual",
      total_avaliacoes: null,
    },
  ],
};

const envios: { url: string; corpo: unknown }[] = [];

function servidor() {
  envios.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        envios.push({ url, corpo: JSON.parse(String(init.body)) });
        return new Response(JSON.stringify({}), { status: 201 });
      }
      return new Response(JSON.stringify(NOTAS), { status: 200 });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a tela de Nota externa", () => {
  it("mostra a nota do Google só para leitura, com o total e a leitura automática", async () => {
    servidor();

    render(<NotaExternaPage />);

    expect(await screen.findByText("2,5 de 5")).toBeTruthy();
    expect(screen.getByText(/1\.629 avaliações/)).toBeTruthy();
    expect(screen.getByText(/lida sozinha no Google em 16\/11\/2026/i)).toBeTruthy();
    expect(screen.queryByLabelText(/nova nota do google/i)).toBeNull();
  });

  it("o Reclame Aqui continua aceitando registro manual", async () => {
    servidor();

    render(<NotaExternaPage />);

    const campo = await screen.findByLabelText(/nova nota do reclame aqui/i);
    fireEvent.change(campo, { target: { value: "8,1" } });
    const botoes = screen.getAllByRole("button", { name: /registrar/i });
    expect(botoes).toHaveLength(1);
    fireEvent.click(botoes[0]);

    await waitFor(() => expect(envios).toHaveLength(1));
    expect(envios[0].corpo).toEqual({ fonte: "reclame_aqui", nota: 8.1 });
  });

  it("sem nota ainda, cada fonte diz por que está vazia (issue #1629, regra T7)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ notas: [] }), { status: 200 })),
    );

    render(<NotaExternaPage />);

    expect(
      await screen.findByText("Nenhuma leitura ainda. A nota do Google é buscada sozinha uma vez por semana.")
    ).toBeTruthy();
    expect(
      screen.getByText("Nenhum registro ainda. A nota aparece aqui quando alguém registrar a primeira.")
    ).toBeTruthy();
  });
});
