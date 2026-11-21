/**
 * @vitest-environment jsdom
 */

/**
 * A tela das Definições de processo do setor (issue #1875, ADR 0098, decisão
 * 9): os itens agrupados por setor, com o trecho da ata; Tirar da lista pede
 * anotação e só aparece para quem pode.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListaDeDefinicoesDeProcesso } from "./ListaDeDefinicoesDeProcesso";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ITENS = [
  {
    id: "D1",
    id_reuniao: "R1",
    reuniao_titulo: "Enfermagem semanal",
    reuniao_data: "2026-11-10",
    setor_id: "S-ENF",
    setor_nome: "Enfermagem",
    trecho: "Toda alta passa pelo checklist de medicação",
    objetivo: "Evitar erro de dose na alta",
    created_at: "2026-11-14T12:00:00+00:00",
    pode_retirar: true,
  },
  {
    id: "D2",
    id_reuniao: "R2",
    reuniao_titulo: "Enfermagem mensal",
    reuniao_data: "2026-11-12",
    setor_id: "S-ENF",
    setor_nome: "Enfermagem",
    trecho: "Passagem de plantão à beira do leito",
    objetivo: null,
    created_at: "2026-11-15T12:00:00+00:00",
    pode_retirar: false,
  },
  {
    id: "D4",
    id_reuniao: "R4",
    reuniao_titulo: "Reunião antiga",
    reuniao_data: "2026-01-10",
    setor_id: null,
    setor_nome: null,
    trecho: "Escala sai na sexta",
    objetivo: null,
    created_at: "2026-01-10T12:00:00+00:00",
    pode_retirar: true,
  },
];

let chamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      if (init?.method === "POST") return new Response("{}", { status: 200 });
      return new Response(JSON.stringify(ITENS), { status: 200 });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => chamadas.filter((c) => c.init?.method === "POST");

describe("a tela das Definições de processo", () => {
  it("agrupa por setor e mostra o trecho da ata e a reunião de origem", async () => {
    render(<ListaDeDefinicoesDeProcesso />);

    const enfermagem = await screen.findByRole("list", { name: "Definições de processo de Enfermagem" });
    const itens = within(enfermagem).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0].textContent).toContain("Toda alta passa pelo checklist de medicação");
    expect(itens[0].textContent).toContain("Evitar erro de dose na alta");
    expect(itens[0].textContent).toContain("Enfermagem semanal, 10/11/2026");
    const semSetor = screen.getByRole("list", { name: "Definições de processo de Reunião sem setor" });
    expect(within(semSetor).getAllByRole("listitem")[0].textContent).toContain("Escala sai na sexta");
  });

  it("tirar da lista só confirma com anotação", async () => {
    render(<ListaDeDefinicoesDeProcesso />);
    const enfermagem = await screen.findByRole("list", { name: "Definições de processo de Enfermagem" });
    const [primeiro, segundo] = within(enfermagem).getAllByRole("listitem");

    expect(within(segundo).queryByRole("button", { name: "Tirar da lista" })).toBeNull();
    fireEvent.click(within(primeiro).getByRole("button", { name: "Tirar da lista" }));
    const confirmar = screen.getByRole("button", { name: "Confirmar" });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "  Repetido  " } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe("/api/definicoes-processo/D1/retirar");
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({ anotacao: "Repetido" });
  });

  it("lista vazia diz o que fazer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    render(<ListaDeDefinicoesDeProcesso />);

    expect(await screen.findByText(/Nenhuma definição de processo/)).toBeTruthy();
  });
});
