/**
 * @vitest-environment jsdom
 */

/**
 * A tela das Rotinas (issue #1874, ADR 0098, decisão 9): cada ciclo em aberto
 * com Realizada em um clique e Não realizada com anotação; o Facilitador
 * encerra a Rotina com anotação.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListaDeRotinas } from "./ListaDeRotinas";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ROTINA = {
  id: "RT1",
  id_reuniao: "R1",
  reuniao_titulo: "Reunião da Enfermagem",
  descricao: "Reunir a equipe",
  responsavel_id: "P2",
  responsavel_nome: "Ana Lima",
  frequencia: "SEMANAL",
  comeca_em: "2026-11-23",
  status: "ATIVA",
  encerrada_em: null,
  anotacao_encerramento: null,
  ciclos_em_aberto: [
    { inicio: "2026-11-30", fim: "2026-12-06", atrasado: true },
    { inicio: "2026-12-07", fim: "2026-12-13", atrasado: false },
  ],
  verificacoes: [
    {
      ciclo_inicio: "2026-11-23",
      ciclo_fim: "2026-11-29",
      resultado: "NAO_REALIZADA",
      anotacao: "Equipe de plantão",
      atrasada: true,
      marcada_por_nome: "Ana Lima",
    },
  ],
  pode_marcar: true,
  pode_encerrar: true,
};

let chamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      if (init?.method === "POST") return new Response("{}", { status: 201 });
      return new Response(JSON.stringify([ROTINA]), { status: 200 });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => chamadas.filter((c) => c.init?.method === "POST");

describe("a tela das Rotinas", () => {
  it("mostra cada ciclo em aberto com o período e o atraso", async () => {
    render(<ListaDeRotinas />);

    const ciclos = await screen.findByRole("list", { name: "Ciclos em aberto de Reunir a equipe" });
    const itens = within(ciclos).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0].textContent).toContain("30/11 a 06/12");
    expect(itens[0].textContent).toContain("Atrasado");
    expect(itens[1].textContent).not.toContain("Atrasado");
    expect(screen.getByText(/Rotina semanal/).textContent).toContain("Ana Lima");
  });

  it("Realizada é um clique, sem anotação", async () => {
    render(<ListaDeRotinas />);
    const ciclos = await screen.findByRole("list", { name: "Ciclos em aberto de Reunir a equipe" });

    fireEvent.click(within(ciclos).getAllByRole("button", { name: "Realizada" })[0]);

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe("/api/rotinas/RT1/ciclos/2026-11-30/realizada");
    expect(posts()[0].init?.body).toBeUndefined();
  });

  it("Não realizada só confirma com anotação", async () => {
    render(<ListaDeRotinas />);
    const ciclos = await screen.findByRole("list", { name: "Ciclos em aberto de Reunir a equipe" });

    fireEvent.click(within(ciclos).getAllByRole("button", { name: "Não realizada" })[1]);
    const confirmar = screen.getByRole("button", { name: "Confirmar" });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "  Faltou sala  " } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe("/api/rotinas/RT1/ciclos/2026-12-07/nao-realizada");
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({ anotacao: "Faltou sala" });
  });

  it("encerrar pede anotação", async () => {
    render(<ListaDeRotinas />);

    fireEvent.click(await screen.findByRole("button", { name: "Encerrar a Rotina" }));
    const confirmar = screen.getByRole("button", { name: "Confirmar" });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Virou processo" } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe("/api/rotinas/RT1/encerrar");
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({ anotacao: "Virou processo" });
  });

  it("quem não pode encerrar não vê o botão, e a marcação passada mostra o atraso", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([{ ...ROTINA, pode_encerrar: false }]), { status: 200 }))
    );
    render(<ListaDeRotinas />);

    const marcadas = await screen.findByRole("list", { name: "Verificações de Reunir a equipe" });
    expect(marcadas.textContent).toContain("Não realizada");
    expect(marcadas.textContent).toContain("marcada com atraso");
    expect(marcadas.textContent).toContain("Equipe de plantão");
    expect(screen.queryByRole("button", { name: "Encerrar a Rotina" })).toBeNull();
  });

  it("o link do Início (#rotina-<id>) leva até a Rotina, depois que a lista chega", async () => {
    const rolou: Element[] = [];
    Element.prototype.scrollIntoView = function (this: Element) {
      rolou.push(this);
    };
    window.location.hash = "#rotina-RT1";
    try {
      render(<ListaDeRotinas />);
      const ciclos = await screen.findByRole("list", { name: "Ciclos em aberto de Reunir a equipe" });

      const rotina = ciclos.closest("section") as HTMLElement;
      expect(rotina.id).toBe("rotina-RT1");
      await waitFor(() => expect(rolou).toEqual([rotina]));
    } finally {
      window.location.hash = "";
    }
  });
});

// O fluxo contínuo antigo virou Rotina sem frequência (issue #1877).
const SEM_FREQUENCIA = {
  ...ROTINA,
  frequencia: null,
  comeca_em: null,
  ciclos_em_aberto: [],
  verificacoes: [],
  pode_escolher_frequencia: true,
};

describe("a Rotina sem frequência", () => {
  beforeEach(() => {
    // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao abrir.
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url, init });
        if (init?.method === "POST") return new Response("{}", { status: 200 });
        return new Response(JSON.stringify([SEM_FREQUENCIA]), { status: 200 });
      })
    );
  });

  it("o Facilitador escolhe a frequência e salva", async () => {
    render(<ListaDeRotinas />);

    const escolha = await screen.findByRole("group", { name: "Frequência de Reunir a equipe" });
    const salvar = within(escolha).getByRole("button", { name: "Salvar a frequência" });
    expect((salvar as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(escolha).getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Quinzenal" }));
    fireEvent.click(salvar);

    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe("/api/rotinas/RT1/frequencia");
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({ frequencia: "QUINZENAL" });
  });

  it("quem não escolhe vê que a Rotina espera a frequência, sem o campo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify([{ ...SEM_FREQUENCIA, pode_escolher_frequencia: false }]), { status: 200 })
      )
    );
    render(<ListaDeRotinas />);

    expect((await screen.findByText(/Rotina sem frequência/)).textContent).toContain("Ana Lima");
    expect(screen.getByText(/o facilitador da reunião escolhe a frequência/)).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Frequência de Reunir a equipe" })).toBeNull();
  });
});
