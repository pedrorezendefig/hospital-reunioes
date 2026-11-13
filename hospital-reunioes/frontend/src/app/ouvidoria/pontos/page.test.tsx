/**
 * @vitest-environment jsdom
 */

/**
 * A tela Pontos de escuta com os campos do cartaz A4 (issue #1617, ADR 0086
 * decisão 10).
 *
 * O ouvidor cadastra e edita o nome público, a descrição do local
 * (obrigatória), o título do cartaz, o código de controle e a marca de ala de
 * internação, e baixa o cartaz A4 (o A5 continua disponível). O que se prova
 * aqui é o que a tela manda ao servidor: a validação de verdade é do backend,
 * e tem teste lá.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PontosDeEscutaPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

// O perfil de quem abre a tela: o convite ao Google (issue #1625) só a
// diretoria executiva liga e desliga.
const quem = vi.hoisted(() => ({ perfil: "ouvidor" }));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "p1", perfil_ouvidoria: quem.perfil },
    loading: false,
  }),
}));

const PONTO = {
  id: "pt1",
  codigo: "AB2CD3",
  setor: "Pronto Socorro Adulto",
  ponto: "Recepção do PSA",
  ativo: true,
  criado_em: "2026-08-01T12:00:00+00:00",
  qr_data_uri: "data:image/png;base64,iVBORw0KGgo=",
  nome_publico: "Emergência adulta",
  descricao_local: "Parede ao lado do balcão de triagem",
  titulo_cartaz: "atendimento_hoje",
  codigo_controle: "PSA-01",
  ala_internacao: false,
  google_teste_ativo: false,
};

interface Chamada {
  url: string;
  metodo: string;
  corpo: unknown;
}

let chamadas: Chamada[] = [];

beforeEach(() => {
  chamadas = [];
  quem.perfil = "ouvidor";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (url === "/api/participantes/setores") {
        return { ok: true, status: 200, json: async () => ["Pronto Socorro Adulto", "Recepção"] } as Response;
      }
      if (url.endsWith(".pdf") || url.includes(".pdf?")) {
        return { ok: true, status: 200, blob: async () => new Blob(["%PDF"]) } as Response;
      }
      if (metodo === "PUT") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          pontos: [PONTO],
          convite_google: { global: false, ligado_em: null },
        }),
      } as Response;
    })
  );
  URL.createObjectURL = vi.fn(() => "blob:cartaz");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function preencher(rotulo: string, valor: string, onde: typeof screen | ReturnType<typeof within> = screen) {
  fireEvent.change(onde.getByLabelText(rotulo), { target: { value: valor } });
}

/** O painel de edição aberto: os rótulos repetem os do cartaz novo. */
function painelDeEdicao() {
  return within(screen.getByRole("group", { name: "Editar ponto" }));
}

describe("o cartaz novo com os campos do A4", () => {
  it("cadastra com nome público, descrição do local, título, código de controle e ala", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "Pronto Socorro Adulto" } });
    preencher("Rótulo do ponto", "  Posto 3 ");
    preencher("Nome público", " Internação 3º andar ");
    preencher("Descrição do local", " Corredor, ao lado do posto de enfermagem ");
    fireEvent.change(screen.getByLabelText("Título do cartaz"), { target: { value: "um_minuto" } });
    preencher("Código de controle", "INT-03");
    fireEvent.click(screen.getByLabelText(/ala de internação/i));

    fireEvent.click(screen.getByRole("button", { name: /criar cartaz/i }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST")).toBe(true));
    expect(chamadas.find((c) => c.metodo === "POST")).toEqual({
      url: "/api/ouvidoria/pontos",
      metodo: "POST",
      corpo: {
        setor: "Pronto Socorro Adulto",
        ponto: "Posto 3",
        nome_publico: "Internação 3º andar",
        descricao_local: "Corredor, ao lado do posto de enfermagem",
        titulo_cartaz: "um_minuto",
        codigo_controle: "INT-03",
        ala_internacao: true,
      },
    });
  });

  it("sem a descrição do local o botão não cria o cartaz", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "Pronto Socorro Adulto" } });
    preencher("Rótulo do ponto", "Posto 3");
    preencher("Descrição do local", "   ");

    const botao = screen.getByRole("button", { name: /criar cartaz/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });
});

describe("a edição do ponto", () => {
  it("salva os campos do cartaz, com o opcional em branco virando nulo", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    fireEvent.click(screen.getByRole("button", { name: /editar/i }));
    const painel = painelDeEdicao();
    preencher("Descrição do local", "Parede em frente aos elevadores", painel);
    preencher("Nome público", "  ", painel);
    fireEvent.change(painel.getByLabelText("Título do cartaz"), { target: { value: "um_minuto" } });
    fireEvent.click(painel.getByLabelText(/ala de internação/i));
    fireEvent.click(painel.getByRole("button", { name: /^salvar$/i }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "PATCH")).toBe(true));
    expect(chamadas.find((c) => c.metodo === "PATCH")).toEqual({
      url: "/api/ouvidoria/pontos/pt1",
      metodo: "PATCH",
      corpo: {
        ponto: "Recepção do PSA",
        nome_publico: null,
        descricao_local: "Parede em frente aos elevadores",
        titulo_cartaz: "um_minuto",
        codigo_controle: "PSA-01",
        ala_internacao: true,
      },
    });
  });

  it("descrição do local apagada não salva", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    fireEvent.click(screen.getByRole("button", { name: /editar/i }));
    const painel = painelDeEdicao();
    preencher("Descrição do local", "", painel);

    const salvar = painel.getByRole("button", { name: /^salvar$/i }) as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
  });
});

describe("o download do cartaz", () => {
  it("o cartaz A4 é o padrão, e o A5 continua disponível", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    fireEvent.click(screen.getByRole("button", { name: /cartaz a4/i }));
    fireEvent.click(screen.getByRole("button", { name: /cartaz a5/i }));

    await waitFor(() => expect(chamadas.filter((c) => c.url.includes("cartaz.pdf"))).toHaveLength(2));
    expect(chamadas.filter((c) => c.url.includes("cartaz.pdf")).map((c) => c.url)).toEqual([
      "/api/ouvidoria/pontos/pt1/cartaz.pdf?formato=a4",
      "/api/ouvidoria/pontos/pt1/cartaz.pdf?formato=a5",
    ]);
  });

  it("a linha mostra o nome público e o local, e não só o rótulo interno", async () => {
    render(<PontosDeEscutaPage />);

    expect(await screen.findByText("Emergência adulta")).toBeTruthy();
    expect(screen.getByText("Parede ao lado do balcão de triagem")).toBeTruthy();
  });
});

describe("o teste do convite ao Google (issue #1625)", () => {
  it("a diretoria executiva liga a chave geral", async () => {
    quem.perfil = "diretoria_executiva";
    render(<PontosDeEscutaPage />);

    fireEvent.click(await screen.findByRole("switch", { name: "Convite ao Google em todo o QR" }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "PUT")).toBe(true));
    expect(chamadas.find((c) => c.metodo === "PUT")).toEqual({
      url: "/api/ouvidoria/convite-google",
      metodo: "PUT",
      corpo: { ligado: true },
    });
  });

  it("a diretoria executiva liga a chave de um ponto", async () => {
    quem.perfil = "diretoria_executiva";
    render(<PontosDeEscutaPage />);

    fireEvent.click(await screen.findByRole("switch", { name: "Convite ao Google em Recepção do PSA" }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "PUT")).toBe(true));
    expect(chamadas.find((c) => c.metodo === "PUT")).toEqual({
      url: "/api/ouvidoria/pontos/pt1/convite-google",
      metodo: "PUT",
      corpo: { ligado: true },
    });
  });

  it("o ouvidor vê o estado do teste, sem chave para mudar", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    expect(screen.getByText(/O teste do convite ao Google está desligado/)).toBeTruthy();
    expect(screen.getByText(/Só a diretoria executiva liga e desliga/)).toBeTruthy();
    expect(screen.queryAllByRole("switch")).toEqual([]);
  });
});

describe("a orientação embutida da tela (issue #1629, regra T1)", () => {
  it("abre com a frase do topo da seção 4.14", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    expect(
      screen.getByText("Cada ponto é um cartaz. O local descrito aqui é o que aparece no painel.")
    ).toBeTruthy();
  });

  it("a descrição do local tem o ? com o aviso de cartaz que mudou de lugar (seção 4.13)", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");
    const aviso =
      "Cartaz mudou de lugar? Aposente o ponto antigo e crie um novo. Mover o cartaz sem trocar o ponto faz o painel mostrar dados do lugar errado.";

    // A explicação nasce fechada: aberta, ela empurraria o formulário inteiro.
    expect(screen.queryByText(aviso)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "O que é: Descrição do local" }));
    expect(screen.getByText(aviso)).toBeTruthy();
  });

  it("os campos do cartaz têm o ? com uma linha de explicação", async () => {
    render(<PontosDeEscutaPage />);
    await screen.findByText("Recepção do PSA");

    for (const campo of ["Setor", "Rótulo do ponto", "Título do cartaz", "Código de controle"]) {
      expect(screen.getByRole("button", { name: `O que é: ${campo}` })).toBeTruthy();
    }
  });
});
