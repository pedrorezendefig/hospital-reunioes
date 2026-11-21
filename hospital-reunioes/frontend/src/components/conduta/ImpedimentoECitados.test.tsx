/**
 * @vitest-environment jsdom
 */

/**
 * Impedimento, contestação da participação e Citado na tela do caso (issue
 * #1828). Quem decide o que vale é o servidor; aqui se trava o que a tela
 * mostra e o que ela pede a ele.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CasoAberto } from "@/lib/conduta/comite";

import { ImpedimentoECitados } from "./ImpedimentoECitados";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }) },
  }),
}));

let respostas: Record<string, unknown>;
let chamadas: { url: string; method: string; body: unknown }[];

beforeEach(() => {
  chamadas = [];
  respostas = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      const chave = Object.keys(respostas).find((k) => url.includes(k)) ?? "";
      return { ok: true, status: 200, json: async () => respostas[chave] ?? {} } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Parte = Pick<
  CasoAberto,
  "membros_do_caso" | "pode_contestar_participacao" | "contestacoes_de_participacao" | "citados"
>;

const CASO: Parte = {
  membros_do_caso: [
    { id: "LEITOR", nome: "Bruna Leitora", papel: "segundo_leitor" },
    { id: "MEMB", nome: "Marcos Membro", papel: "membro" },
  ],
  pode_contestar_participacao: true,
  contestacoes_de_participacao: [],
  citados: [],
};

function desenhar(parte: Partial<Parte> = {}, aoMudar = vi.fn(), aoImpedir = vi.fn()) {
  render(<ImpedimentoECitados casoId="c1" caso={{ ...CASO, ...parte }} aoMudar={aoMudar} aoImpedir={aoImpedir} />);
  return { aoMudar, aoImpedir };
}

describe("Declarar impedimento", () => {
  it("pede o motivo e avisa a tela que a pessoa saiu do caso", async () => {
    const { aoImpedir } = desenhar();

    fireEvent.click(screen.getByRole("button", { name: "DECLARAR IMPEDIMENTO" }));
    const form = screen.getByRole("form", { name: "Declarar impedimento" });
    const enviar = within(form).getByRole("button", { name: "CONFIRMAR IMPEDIMENTO" }) as HTMLButtonElement;
    expect(enviar.disabled).toBe(true);
    fireEvent.click(within(form).getByLabelText("Parentesco"));
    fireEvent.click(enviar);

    await waitFor(() => expect(aoImpedir).toHaveBeenCalled());
    expect(chamadas.at(-1)).toEqual({
      url: "/api/comite-de-conduta/casos/c1/impedimento",
      method: "POST",
      body: { motivo: "parentesco" },
    });
  });
});

describe("Contestar a participação", () => {
  it("escolhe o membro e o motivo e envia", async () => {
    respostas = { "/contestacoes-de-participacao": { contestacao: { id: "x1", resultado: null } } };
    const { aoMudar } = desenhar();

    fireEvent.click(screen.getByRole("button", { name: "CONTESTAR PARTICIPAÇÃO" }));
    const form = screen.getByRole("form", { name: "Contestar a participação" });
    fireEvent.change(within(form).getByLabelText("Membro"), { target: { value: "MEMB" } });
    fireEvent.change(within(form).getByLabelText("Motivo"), { target: { value: "interesse" } });
    fireEvent.click(within(form).getByRole("button", { name: "CONTESTAR PARTICIPAÇÃO" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)?.body).toEqual({ contestado_id: "MEMB", motivo: "interesse" });
  });

  it("quem pode decidir vê os dois botões, e o voto vai à contestação certa", async () => {
    const { aoMudar } = desenhar({
      contestacoes_de_participacao: [
        { id: "x1", contestado: "Marcos Membro", motivo: "interesse no resultado", votos: 1, resultado: null, pode_decidir: true },
        { id: "x2", contestado: "Bruna Leitora", motivo: "parentesco", votos: 2, resultado: "rejeitada", pode_decidir: false },
      ],
    });

    const lista = screen.getByRole("list", { name: "Contestações de participação" });
    const [aberta, decidida] = within(lista).getAllByRole("listitem");
    expect(decidida.textContent).toContain("Os demais decidiram: Bruna Leitora segue no caso.");
    expect(within(decidida).queryByRole("button")).toBeNull();
    fireEvent.click(within(aberta).getByRole("button", { name: "CONFIRMAR IMPEDIMENTO" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)).toEqual({
      url: "/api/comite-de-conduta/casos/c1/contestacoes-de-participacao/x1/decisao",
      method: "POST",
      body: { escolha: "confirmar" },
    });
  });

  it("sem outro membro no caso, não oferece contestar", () => {
    desenhar({ pode_contestar_participacao: false });
    expect(screen.queryByRole("button", { name: "CONTESTAR PARTICIPAÇÃO" })).toBeNull();
  });
});

describe("Citado", () => {
  it("mostra os Citados e diz quem está ligado ao cadastro", () => {
    desenhar({
      citados: [
        { id: "k1", nome: "Joana Silva", ligado: true },
        { id: "k2", nome: "Carlos da Portaria", ligado: false },
      ],
    });

    const lista = screen.getByRole("list", { name: "Citados" });
    expect(within(lista).getAllByRole("listitem").map((l) => l.textContent)).toEqual([
      "Joana SilvaNo cadastro",
      "Carlos da PortariaSó o nome",
    ]);
  });

  it("busca no cadastro e liga a marcação à pessoa escolhida", async () => {
    respostas = { "/cadastro": { pessoas: [{ id: "FORA", nome: "Joana Almoxarifado Silva" }] } };
    const { aoMudar } = desenhar();

    fireEvent.change(screen.getByLabelText("Nome do Citado"), { target: { value: "almox" } });
    fireEvent.click(screen.getByRole("button", { name: "BUSCAR NO CADASTRO" }));
    const achados = await screen.findByRole("list", { name: "Achados no cadastro" });
    expect(chamadas.at(-1)?.url).toBe("/api/comite-de-conduta/casos/c1/cadastro?busca=almox");
    respostas = {};
    fireEvent.click(within(achados).getByRole("button", { name: "Marcar Joana Almoxarifado Silva" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)).toEqual({
      url: "/api/comite-de-conduta/casos/c1/citados",
      method: "POST",
      body: { participante_id: "FORA" },
    });
  });

  it("marca só pelo nome quando a pessoa não está no cadastro", async () => {
    const { aoMudar } = desenhar();

    fireEvent.change(screen.getByLabelText("Nome do Citado"), { target: { value: "Carlos da Portaria" } });
    fireEvent.click(screen.getByRole("button", { name: "MARCAR SÓ PELO NOME" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)?.body).toEqual({ nome: "Carlos da Portaria" });
  });
});
