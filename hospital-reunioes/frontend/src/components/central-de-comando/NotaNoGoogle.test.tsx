/**
 * @vitest-environment jsdom
 */

/**
 * A lente de "Melhorar a nota no Google" (issue #1619, ADR 0089).
 *
 * O servidor é falso e a conta é dele: a tela escreve a nota, as avaliações
 * novas do mês (dizendo como se conta) e a tendência. Sem a chave da Places
 * API, a tela diz que a nota não está sendo medida, sem número.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotaNoGoogle, type NotaNoGooglePayload } from "./NotaNoGoogle";

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: async () => "token-de-teste",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

// O jsdom não mede layout: o `ResponsiveContainer` vira um de largura fixa, a
// de um celular de 375 px, e o resto do `recharts` roda de verdade (molde do
// teste de Visitantes por dia).
const LARGURA_DO_CELULAR = 375;

vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
      cloneElement(children, { width: LARGURA_DO_CELULAR, height: 220 }),
  };
});

const pedidos: string[] = [];

function servidor(corpo: NotaNoGooglePayload) {
  pedidos.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      return new Response(JSON.stringify(corpo), { status: 200 });
    }),
  );
}

const OBJETIVO = {
  id: "google-reputacao",
  nome: "Melhorar a nota no Google",
  descricao: "Melhorar a reputação e as avaliações no Google Meu Negócio.",
};

function medida(parcial: Partial<NotaNoGooglePayload["reputacao"]> = {}): NotaNoGooglePayload {
  return {
    objetivo: OBJETIVO,
    reputacao: {
      medida: true,
      nota: 2.6,
      escala: 5,
      total: 1641,
      lida_em: "2026-11-16T09:45:00+00:00",
      avaliacoes_do_mes: 12,
      nota_mes_anterior: 2.4,
      tendencia: "melhorou",
      leituras_do_mes: [
        { lida_em: "2026-11-02T09:45:00+00:00", nota: 2.5, total: 1629 },
        { lida_em: "2026-11-09T09:45:00+00:00", nota: 2.5, total: 1635 },
        { lida_em: "2026-11-16T09:45:00+00:00", nota: 2.6, total: 1641 },
      ],
      leituras_mes_anterior: [
        { lida_em: "2026-10-05T09:45:00+00:00", nota: 2.3, total: 1590 },
        { lida_em: "2026-10-26T09:45:00+00:00", nota: 2.4, total: 1620 },
      ],
      ...parcial,
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a lente da nota no Google", () => {
  it("pede a lente do Google à Central", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    await screen.findByText("2,6 de 5");
    expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/google-reputacao?periodo=28d"]);
  });

  it("mostra a nota, as avaliações novas do mês e a tendência", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    expect(await screen.findByText("2,6 de 5")).toBeTruthy();
    expect(screen.getByText("1.641 avaliações no total")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText(/diferença do total de avaliações entre a primeira e a última leitura do mês/i)).toBeTruthy();
    expect(screen.getByText("Melhorou")).toBeTruthy();
    expect(screen.getByText("2,4 de 5 no fim do mês anterior")).toBeTruthy();
  });

  it("nota abaixo da do mês anterior diz que piorou", async () => {
    servidor(medida({ nota: 2.3, tendencia: "piorou" }));

    render(<NotaNoGoogle />);

    expect(await screen.findByText("Piorou")).toBeTruthy();
  });

  it("uma leitura só no mês não vira zero avaliação", async () => {
    servidor(medida({ avaliacoes_do_mes: null, tendencia: null, nota_mes_anterior: null }));

    render(<NotaNoGoogle />);

    await screen.findByText("2,6 de 5");
    expect(screen.queryByText("0")).toBeNull();
    expect(screen.getByText(/precisa de duas leituras no mês/i)).toBeTruthy();
    expect(screen.getByText(/sem leitura do mês anterior para comparar/i)).toBeTruthy();
  });

  it("sem a chave, diz que a nota não está sendo medida e não mostra número", async () => {
    servidor({
      objetivo: OBJETIVO,
      reputacao: {
        medida: false,
        nota: null,
        escala: 5,
        total: null,
        lida_em: null,
        avaliacoes_do_mes: null,
        nota_mes_anterior: null,
        tendencia: null,
        leituras_do_mes: [],
        leituras_mes_anterior: [],
      },
    });

    render(<NotaNoGoogle />);

    expect(await screen.findByText(/a nota do google não está sendo medida/i)).toBeTruthy();
    expect(screen.queryByText(/de 5/)).toBeNull();
    expect(screen.getByText(/Quando for, a nota e o gráfico do mês aparecem aqui/)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("o gráfico do mês (issue #1699)", () => {
  const curvas = (grafico: HTMLElement) => [...grafico.querySelectorAll("path.recharts-line-curve")];

  it("mostra um gráfico da nota e um das avaliações acumuladas, com as leituras do mês", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    const nota = await screen.findByRole("img", { name: /^Nota no Google em cada leitura do mês/ });
    const acumuladas = screen.getByRole("img", { name: /^Avaliações acumuladas em cada leitura do mês/ });
    // Uma bolinha por leitura do mês, na linha cheia.
    expect(nota.querySelectorAll(".recharts-line-dots")[1].querySelectorAll("circle")).toHaveLength(3);
    expect(acumuladas.querySelectorAll(".recharts-line-dots")[1].querySelectorAll("circle")).toHaveLength(3);
    const rotulosDoTotal = [...acumuladas.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick-value")];
    expect(rotulosDoTotal.map((r) => r.textContent).some((t) => /mil/.test(t ?? ""))).toBe(true);
  });

  it("põe o mês anterior tracejado atrás e diz se a nota melhorou frente a ele", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    const nota = await screen.findByRole("img", { name: /^Nota no Google em cada leitura do mês/ });
    const [anterior, doMes] = curvas(nota);
    expect(anterior.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(doMes.getAttribute("stroke-dasharray")).toBeNull();
    expect(screen.getAllByText("Mês anterior").length).toBeGreaterThan(0);
    expect(nota.getAttribute("aria-label")).toMatch(/A nota melhorou: 2,6 de 5 contra 2,4 de 5 no fim do mês anterior\./);
    expect(screen.getByText("A nota melhorou: 2,6 de 5 contra 2,4 de 5 no fim do mês anterior.")).toBeTruthy();
  });

  it("nota abaixo da do fim do mês anterior, o gráfico diz que piorou", async () => {
    servidor(medida({ nota: 2.3, tendencia: "piorou" }));

    render(<NotaNoGoogle />);

    expect(await screen.findByText("A nota piorou: 2,3 de 5 contra 2,4 de 5 no fim do mês anterior.")).toBeTruthy();
  });

  it("sem leitura no mês, diz por que o gráfico está vazio", async () => {
    servidor(
      medida({ nota: 2.4, leituras_do_mes: [], avaliacoes_do_mes: null, tendencia: null, nota_mes_anterior: 2.4 }),
    );

    render(<NotaNoGoogle />);

    expect(
      await screen.findByText(
        "O gráfico está vazio porque ainda não houve leitura neste mês. A nota é lida uma vez por semana, e o gráfico começa na primeira leitura do mês.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("a 375 px, os dois gráficos ocupam a largura e todo rótulo do eixo cabe dentro deles", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    await screen.findByRole("img", { name: /^Nota no Google/ });
    const graficos = screen.getAllByRole("img");
    expect(graficos).toHaveLength(2);
    for (const grafico of graficos) {
      const largura = Number(grafico.querySelector("svg.recharts-surface")!.getAttribute("width"));
      expect(largura).toBe(LARGURA_DO_CELULAR);
      // 12px de fonte e uns 0,6em por letra: metade do rótulo de cada lado do ponto.
      for (const rotulo of grafico.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick-value")) {
        const metade = ((rotulo.textContent ?? "").length * 12 * 0.6) / 2;
        const x = Number(rotulo.getAttribute("x"));
        expect(x - metade).toBeGreaterThanOrEqual(0);
        expect(largura - x).toBeGreaterThanOrEqual(metade);
      }
    }
  });
});

describe("o teste do convite ao Google (issue #1625)", () => {
  function comConvite(parcial: Partial<NonNullable<NotaNoGooglePayload["convite"]>> = {}): NotaNoGooglePayload {
    return {
      ...medida(),
      convite: {
        periodo: "28d",
        ligado: true,
        ligado_em: "2026-10-20T12:00:00+00:00",
        dias_ligado: 24,
        dias_do_teste: 60,
        reavaliar: false,
        intervalo: { inicio: "2026-10-16", fim: "2026-11-12" },
        pontos: [
          { ponto_id: "p1", nome: "Emergência adulta", ligado: true, convites: 4, cliques: 2, taxa: 0.5 },
          { ponto_id: "p2", nome: "Centro médico", ligado: true, convites: 0, cliques: 0, taxa: null },
        ],
        total: { convites: 4, cliques: 2, taxa: 0.5 },
        ...parcial,
      },
    };
  }

  it("pede os números do convite no período escolhido", async () => {
    servidor(comConvite());

    render(<NotaNoGoogle periodo="90d" />);

    await screen.findByText("2,6 de 5");
    expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/google-reputacao?periodo=90d"]);
  });

  it("mostra convites, cliques e taxa de cada ponto ao lado da nota", async () => {
    servidor(comConvite());

    render(<NotaNoGoogle />);

    const tabela = await screen.findByRole("table", { name: "Convites ao Google por ponto" });
    const linhas = within(tabela).getAllByRole("row").map((linha) => linha.textContent);
    expect(linhas).toContain("Emergência adulta4250%");
    expect(linhas).toContain("Centro médico00Sem convite");
    expect(linhas).toContain("Total4250%");
    expect(screen.queryByText(/Hora de reavaliar/)).toBeNull();
  });

  it("depois de 60 dias avisa para reavaliar e diz que o convite continua", async () => {
    servidor(comConvite({ dias_ligado: 73, reavaliar: true }));

    render(<NotaNoGoogle />);

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toMatch(/Hora de reavaliar/);
    expect(aviso.textContent).toMatch(/continua aparecendo até a diretoria executiva desligar/);
  });

  it("com o teste desligado diz que o convite não aparece", async () => {
    servidor(comConvite({ ligado: false, ligado_em: null, dias_ligado: null, pontos: [], total: { convites: 0, cliques: 0, taxa: null } }));

    render(<NotaNoGoogle />);

    expect(await screen.findByText(/O convite ao Google está desligado/)).toBeTruthy();
  });
});
