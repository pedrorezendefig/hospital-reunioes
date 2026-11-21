/**
 * @vitest-environment jsdom
 */

/**
 * As Rotinas no Início (issue #1944, PRD #1932).
 *
 * O trilho mostra as Rotinas do ciclo de agora, com quantas já têm
 * Verificação. Na fila, Realizada é o botão de um clique e Não realizada é o
 * caminho para a tela da Rotina, que pede a Anotação. A Rotina a revisar do
 * Facilitador tem Manter (um clique) e Encerrar (a tela da Rotina). Quem vê o
 * quê vem do servidor (`backend/tests/test_inicio_rotinas.py`).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MinhaFila, type InicioDaPessoa, type ItemDoInicio } from "./MinhaFila";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const RT1 = "00000000-0000-0000-0000-0000000000a1";
const RT2 = "00000000-0000-0000-0000-0000000000a2";

function item(campos: Partial<ItemDoInicio>): ItemDoInicio {
  return {
    tipo: "verificacao_da_rotina",
    id: `${RT2}:2026-11-16`,
    titulo: "Conferir o carrinho de parada",
    origem: "Rotina quinzenal da Reunião de Enfermagem.",
    prazo: "2026-11-30",
    chegou_em: "2026-11-16",
    area: "Reuniões",
    acao: "Abrir as Rotinas",
    destino: "/rotinas",
    acao_de_um_clique: { rotulo: "Realizada", endpoint: `/api/rotinas/${RT2}/ciclos/2026-11-16/realizada` },
    acao_secundaria: { rotulo: "Não realizada", destino: `/rotinas#rotina-${RT2}` },
    grupo: "proximos_7_dias",
    dias_de_atraso: null,
    ...campos,
  };
}

const INICIO: InicioDaPessoa = {
  hoje: "2026-11-25",
  frase: { titulo: "Ana, você está em dia.", apoio: "O próximo prazo é domingo." },
  contadores: { passou_do_prazo: 0, ate_48_horas: 0, proximos_7_dias: 2 },
  itens: [
    item({}),
    item({
      tipo: "rotina_a_revisar",
      id: RT1,
      titulo: "Reunir a equipe",
      origem: "Revisão de 90 dias. Rotina semanal da Reunião de Enfermagem.",
      acao: "Revisar a Rotina",
      destino: `/rotinas#rotina-${RT1}`,
      acao_de_um_clique: { rotulo: "Manter", endpoint: `/api/rotinas/${RT1}/manter` },
      acao_secundaria: { rotulo: "Encerrar", destino: `/rotinas#rotina-${RT1}` },
    }),
  ],
  avisos: [],
  trilho: [],
  rotinas_do_ciclo: [
    {
      id: RT1,
      titulo: "Reunir a equipe",
      ciclo_inicio: "2026-11-23",
      ciclo_fim: "2026-11-29",
      verificacao: "REALIZADA",
      destino: `/rotinas#rotina-${RT1}`,
    },
    {
      id: RT2,
      titulo: "Conferir o carrinho de parada",
      ciclo_inicio: "2026-11-16",
      ciclo_fim: "2026-11-30",
      verificacao: null,
      destino: `/rotinas#rotina-${RT2}`,
    },
  ],
  filas_do_papel: [],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function servidor(corpo: InicioDaPessoa) {
  const chamadas: { url: string; metodo: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, metodo: init?.method ?? "GET" });
      return { ok: true, status: 201, json: async () => corpo } as Response;
    })
  );
  return chamadas;
}

async function abrir(corpo: InicioDaPessoa = INICIO) {
  const chamadas = servidor(corpo);
  render(<MinhaFila />);
  await screen.findByText(corpo.frase.titulo);
  return chamadas;
}

function linhaDaFila(titulo: string, tipo: string): HTMLElement {
  const fila = screen.getAllByRole("region").find((r) => r.getAttribute("aria-label") === "Próximos 7 dias");
  const linhas = within(fila as HTMLElement).getAllByRole("listitem");
  const achada = linhas.find(
    (li) => within(li).queryByText(titulo) && (tipo === "rotina_a_revisar") === !!within(li).queryByText(/Revisão de 90 dias/)
  );
  return achada as HTMLElement;
}

describe("o trilho das Rotinas do ciclo", () => {
  it("mostra as Rotinas do ciclo com quantas já têm Verificação", async () => {
    await abrir();

    const trilho = screen.getByRole("complementary", { name: "Rotinas do ciclo" });
    expect(within(trilho).getByText("1 de 2 marcadas")).toBeTruthy();
    const rotinas = within(trilho).getAllByRole("link");
    expect(rotinas.map((a) => a.getAttribute("href"))).toEqual([`/rotinas#rotina-${RT1}`, `/rotinas#rotina-${RT2}`]);
    expect(within(rotinas[0]).getByText("Reunir a equipe")).toBeTruthy();
    expect(within(rotinas[0]).getByText("Até 29/11, Realizada")).toBeTruthy();
    expect(within(rotinas[1]).getByText("Até 30/11, falta marcar")).toBeTruthy();
  });

  it("quem não tem Rotina no ciclo não vê o bloco", async () => {
    await abrir({ ...INICIO, rotinas_do_ciclo: [] });

    expect(screen.queryByRole("complementary", { name: "Rotinas do ciclo" })).toBeNull();
    expect(screen.getByRole("complementary", { name: "Próximas Reuniões" })).toBeTruthy();
  });
});

describe("a Verificação na fila", () => {
  it("Realizada grava sem sair do Início e o Início é pedido de novo", async () => {
    const chamadas = await abrir();

    const linha = linhaDaFila("Conferir o carrinho de parada", "verificacao_da_rotina");
    fireEvent.click(within(linha).getByRole("button", { name: "Realizada" }));

    await waitFor(() =>
      expect(chamadas).toContainEqual({ url: `/api/rotinas/${RT2}/ciclos/2026-11-16/realizada`, metodo: "POST" })
    );
    await waitFor(() => expect(chamadas.filter((c) => c.url === "/api/inicio")).toHaveLength(2));
  });

  it("Não realizada leva à tela da Rotina", async () => {
    await abrir();

    const linha = linhaDaFila("Conferir o carrinho de parada", "verificacao_da_rotina");
    const link = within(linha).getByRole("link", { name: "Não realizada: Conferir o carrinho de parada" });
    expect(link.getAttribute("href")).toBe(`/rotinas#rotina-${RT2}`);
  });
});

describe("a Rotina a revisar", () => {
  it("Manter é um clique e Encerrar leva à tela da Rotina", async () => {
    const chamadas = await abrir();

    const linha = linhaDaFila("Reunir a equipe", "rotina_a_revisar");
    expect(within(linha).getByRole("link", { name: "Encerrar: Reunir a equipe" }).getAttribute("href")).toBe(
      `/rotinas#rotina-${RT1}`
    );
    fireEvent.click(within(linha).getByRole("button", { name: "Manter" }));

    await waitFor(() => expect(chamadas).toContainEqual({ url: `/api/rotinas/${RT1}/manter`, metodo: "POST" }));
  });
});

it("sem travessão nem meia-risca", async () => {
  await abrir();

  expect(document.body.textContent).not.toContain(String.fromCharCode(0x2014));
  expect(document.body.textContent).not.toContain(String.fromCharCode(0x2013));
});
