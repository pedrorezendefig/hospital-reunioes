/**
 * @vitest-environment jsdom
 */

/**
 * O Painel de Contas médicas (issue #1137, PRD #1128).
 *
 * A tela não soma nada: o servidor manda cada cartão e cada bloco pronto, e a
 * faturista recebe só a própria linha de produção. O que se trava aqui é o
 * que aparece (os 4 cartões e os 6 blocos, com os números do payload), o que
 * some para a faturista e o que cada filtro pede ao servidor.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Painel } from "@/lib/contas-medicas/painel";

import PainelPage from "./page";

// O jsdom não mede layout nem tem `ResizeObserver`: o `ResponsiveContainer`
// vira um de tamanho fixo e o resto do `recharts` roda de verdade (molde do
// teste do gráfico de Visitantes da Central de Comando).
vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
      cloneElement(children, { width: 600, height: 240 }),
  };
});

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ASSIM = "aaaaaaaa-0000-0000-0000-000000000001";

function semana(inicio: string, campos: Partial<Record<string, number>> = {}) {
  return { semana: inicio, REGISTRADO: 0, PRESCRITO: 0, PRESCRITO_SN: 0, POR_REGRA: 0, ...campos };
}

const PRODUCAO_DA_ANA = {
  faturista_id: "F1",
  nome: "Ana Faturista",
  contas: 2,
  com_pendencia: 1,
  valor_incluido: 200,
  valor_retirado: 30,
  taxa_nao_procede: 0.1429,
};

const PAINEL: Painel = {
  semana: { inicio: "2026-10-05", fim: "2026-10-11" },
  filtros: {
    operadoras: [
      { id: ASSIM, sigla: "ASSIM", nome: "ASSIM Saúde" },
      { id: "unimed", sigla: "UNIMED", nome: "Unimed" },
    ],
  },
  nota_media: { semana: 70, anterior: 72 },
  contas_concluidas: { total: 3 },
  valor_apontado: { total: 315, ja_incluido: 250 },
  nao_procede: { linhas: 2, de: 10, taxa: 0.2 },
  nota_por_semana: [
    { semana: "2026-09-28", nota_media: 72, contas: 2 },
    { semana: "2026-10-05", nota_media: 70, contas: 3 },
  ],
  causa_raiz: [
    { causa: "DISPENSACAO", valor: 200, percentual: 63.5 },
    { causa: "REGRA_AUTOMATICA", valor: 50, percentual: 15.9 },
    { causa: "CADASTRO_PRECO", valor: 15, percentual: 4.8 },
    { causa: "REGISTRO_ASSISTENCIAL", valor: 0, percentual: 0 },
    { causa: "LANCAMENTO_MANUAL", valor: 50, percentual: 15.9 },
  ],
  itens_que_faltam: [
    { codigo: "M100", descricao: "Luva", contas: 3, valor: 210 },
    { codigo: "M200", descricao: "Lanceta", contas: 1, valor: 40 },
  ],
  producao: [
    PRODUCAO_DA_ANA,
    {
      faturista_id: "F2",
      nome: "Bia Faturista",
      contas: 1,
      com_pendencia: 0,
      valor_incluido: 50,
      valor_retirado: 20,
      taxa_nao_procede: 0.3333,
    },
  ],
  nivel_evidencia: [
    semana("2026-09-28", { REGISTRADO: 70, PRESCRITO: 30 }),
    semana("2026-10-05", { REGISTRADO: 100, PRESCRITO: 40, PRESCRITO_SN: 60, POR_REGRA: 50 }),
  ],
  custo_ia: { total_usd: 1.2, medio_por_conta_usd: 0.4, contas: 3 },
};

const DA_FATURISTA: Painel = {
  semana: PAINEL.semana,
  filtros: PAINEL.filtros,
  producao: [PRODUCAO_DA_ANA],
};

function servidorResponde(painel: Painel) {
  const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => painel }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function pedidos(fetch: ReturnType<typeof vi.fn>): string[] {
  return fetch.mock.calls.map(([url]) => String(url));
}

beforeEach(() => {
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao
  // abrir a lista de opções.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CARTOES = ["Nota média de entrada", "Contas concluídas", "R$ apontado", "Não procede"];
const BLOCOS = [
  "Nota média por semana",
  "R$ apontado por causa-raiz",
  "Os dez itens que mais faltam",
  "Produção por faturista",
  "R$ incluído por nível de evidência",
  "Custo de IA",
];

describe("o Painel", () => {
  it("mostra os 4 cartões e os 6 blocos com os números do servidor", async () => {
    servidorResponde(PAINEL);

    render(<PainelPage />);

    await screen.findByRole("region", { name: "Nota média de entrada" });
    for (const nome of [...CARTOES, ...BLOCOS]) {
      expect(screen.getByRole("region", { name: nome }), nome).toBeTruthy();
    }
    const nota = screen.getByRole("region", { name: "Nota média de entrada" });
    expect(nota.textContent).toContain("70");
    expect(nota.textContent).toContain("Semana anterior: 72");
    expect(screen.getByRole("region", { name: "Contas concluídas" }).textContent).toContain("3");
    const apontado = screen.getByRole("region", { name: "R$ apontado" });
    expect(apontado.textContent).toContain("R$ 315,00");
    expect(apontado.textContent).toContain("Já incluídos: R$ 250,00");
    const naoProcede = screen.getByRole("region", { name: "Não procede" });
    expect(naoProcede.textContent).toContain("20%");
    expect(naoProcede.textContent).toContain("2 de 10 linhas");

    const causa = screen.getByRole("region", { name: "R$ apontado por causa-raiz" });
    expect(within(causa).getByText("Dispensação").closest("li")?.textContent).toContain("63,5%");
    expect(within(causa).getByText("Dispensação").closest("li")?.textContent).toContain("R$ 200,00");

    const itens = within(screen.getByRole("region", { name: "Os dez itens que mais faltam" })).getAllByRole("row");
    expect(itens[1].textContent).toContain("M100");
    expect(itens[1].textContent).toContain("Luva");
    expect(itens[1].textContent).toContain("3");
    expect(itens[1].textContent).toContain("R$ 210,00");

    const producao = within(screen.getByRole("region", { name: "Produção por faturista" })).getAllByRole("row");
    expect(producao[1].textContent).toContain("Ana Faturista");
    expect(producao[1].textContent).toContain("R$ 200,00");
    expect(producao[1].textContent).toContain("14,3%");
    expect(producao[1].textContent).toContain("R$ 30,00");

    const custo = screen.getByRole("region", { name: "Custo de IA" });
    expect(custo.textContent).toContain("US$ 1,20");
    expect(custo.textContent).toContain("US$ 0,40 por conta");

    expect(screen.getByText(/05\/10 a 11\/10\/2026/)).toBeTruthy();
  });

  it("a faturista vê só a própria linha de produção", async () => {
    servidorResponde(DA_FATURISTA);

    render(<PainelPage />);

    const producao = await screen.findByRole("region", { name: "Produção por faturista" });
    expect(within(producao).getAllByRole("row")).toHaveLength(2);
    for (const nome of [...CARTOES, ...BLOCOS.filter((b) => b !== "Produção por faturista")]) {
      expect(screen.queryByRole("region", { name: nome }), nome).toBeNull();
    }
  });

  it("cada filtro pede o Painel de novo ao servidor", async () => {
    const fetch = servidorResponde(PAINEL);

    render(<PainelPage />);
    await screen.findByRole("region", { name: "Nota média de entrada" });
    expect(pedidos(fetch)[0]).toMatch(/^\/api\/contas-medicas\/painel\?semana=\d{4}-\d{2}-\d{2}$/);

    fireEvent.change(screen.getByLabelText("Semana"), { target: { value: "2026-09-28" } });
    await waitFor(() => expect(pedidos(fetch).at(-1)).toBe("/api/contas-medicas/painel?semana=2026-09-28"));

    fireEvent.click(screen.getByRole("combobox", { name: "Operadora" }));
    fireEvent.click(screen.getByRole("option", { name: "ASSIM" }));
    await waitFor(() =>
      expect(pedidos(fetch).at(-1)).toBe(`/api/contas-medicas/painel?semana=2026-09-28&operadora_id=${ASSIM}`),
    );

    fireEvent.click(screen.getByRole("combobox", { name: "Tipo de conta" }));
    fireEvent.click(screen.getByRole("option", { name: "Parcial" }));
    await waitFor(() =>
      expect(pedidos(fetch).at(-1)).toBe(
        `/api/contas-medicas/painel?semana=2026-09-28&operadora_id=${ASSIM}&tipo=parcial`,
      ),
    );
  });
});
