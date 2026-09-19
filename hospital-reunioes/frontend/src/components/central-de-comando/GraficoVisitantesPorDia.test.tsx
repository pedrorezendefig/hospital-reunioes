/**
 * @vitest-environment jsdom
 */

/**
 * O gráfico de Visitantes por dia da tela Dados do Google (issue #817).
 *
 * Porte de `components/analytics/VisitorsChart.test.tsx` do repositório
 * antigo, agora em `recharts`. O jsdom não mede layout nem tem
 * `ResizeObserver`, e é por isso que o `ResponsiveContainer` não desenha nada
 * aqui (o teste de leitura direta do dashboard desliga os gráficos pelo mesmo
 * motivo). Em vez de desligar, este teste troca só o `ResponsiveContainer` por
 * um de tamanho fixo, a largura de um celular (360 px): o resto do `recharts`
 * roda de verdade, e dá para ver o que o celular mostra.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DicaDoDia, GraficoVisitantesPorDia, type PontoDoMovimento } from "./GraficoVisitantesPorDia";

vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
      cloneElement(children, { width: 360, height: 240 }),
  };
});

afterEach(cleanup);

function ponto(
  data: string,
  visitantes: number,
  data_anterior: string,
  visitantes_anterior: number,
  variacao: number | null = null,
): PontoDoMovimento {
  return { data, visitantes, data_anterior, visitantes_anterior, variacao };
}

const TRES_DIAS: PontoDoMovimento[] = [
  ponto("2026-09-14", 1000, "2026-09-11", 900, 0.1111),
  ponto("2026-09-15", 1500, "2026-09-12", 1100, 0.3636),
  ponto("2026-09-16", 1200, "2026-09-13", 1000, 0.2),
];

/** 28 dias, de 21/08 a 17/09, como o backend manda para o período de 28 dias. */
function vinteEOitoDias(): PontoDoMovimento[] {
  return Array.from({ length: 28 }, (_, i) => {
    const dia = new Date(Date.UTC(2026, 7, 21 + i)).toISOString().slice(0, 10);
    const anterior = new Date(Date.UTC(2026, 6, 24 + i)).toISOString().slice(0, 10);
    return ponto(dia, 300 + i, anterior, 250, 0.2);
  });
}

const curvas = (container: HTMLElement) => [...container.querySelectorAll("path.recharts-line-curve")];

describe("GraficoVisitantesPorDia", () => {
  it("desenha o gráfico com rótulo acessível", () => {
    render(<GraficoVisitantesPorDia pontos={TRES_DIAS} />);

    expect(
      screen.getByRole("img", {
        name: "Visitantes por dia nos últimos 3 dias. Período anterior mostrado para comparação.",
      }),
    ).toBeTruthy();
  });

  it("desenha as duas linhas com as cores dos tokens: o período em azul, o anterior em cinza tracejado", () => {
    const { container } = render(<GraficoVisitantesPorDia pontos={TRES_DIAS} />);

    const linhas = curvas(container);
    expect(linhas).toHaveLength(2);
    const [anterior, atual] = linhas;
    expect(atual.getAttribute("stroke")).toBe("var(--color-primary)");
    expect(anterior.getAttribute("stroke")).toBe("var(--color-text-secondary)");
    expect(anterior.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(atual.getAttribute("stroke-dasharray")).toBeNull();
  });

  it("diz na legenda qual linha é qual", () => {
    render(<GraficoVisitantesPorDia pontos={TRES_DIAS} />);

    const legenda = screen.getByRole("list", { name: "Legenda" });
    expect(within(legenda).getByText("Período escolhido")).toBeTruthy();
    expect(within(legenda).getByText("Período anterior")).toBeTruthy();
  });

  it("mostra o estado vazio quando não há dias", () => {
    render(<GraficoVisitantesPorDia pontos={[]} />);

    expect(screen.getByText("Sem dados de visitantes para este período.")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("sem visita no período anterior, desenha só a linha do período e não anuncia comparação", () => {
    const semAnterior = TRES_DIAS.map((p) => ({ ...p, visitantes_anterior: 0, variacao: null }));

    const { container } = render(<GraficoVisitantesPorDia pontos={semAnterior} />);

    expect(curvas(container)).toHaveLength(1);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Visitantes por dia nos últimos 3 dias.");
    expect(screen.queryByText("Período anterior")).toBeNull();
  });

  it("no celular, o eixo dos dias tem no máximo 4 rótulos curtos, e o último dia é 'ontem'", () => {
    const { container } = render(<GraficoVisitantesPorDia pontos={vinteEOitoDias()} />);

    const rotulos = [...container.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick-value")].map(
      (rotulo) => rotulo.textContent,
    );
    expect(rotulos).toEqual(["21 ago", "30 ago", "8 set", "ontem"]);
  });

  it("ao passar o dedo ou o mouse, mostra os Visitantes do dia e a comparação com o anterior", () => {
    const { container } = render(<GraficoVisitantesPorDia pontos={TRES_DIAS} />);

    // 360 px de largura: o eixo dos Visitantes ocupa os primeiros 48 e a
    // margem os últimos 12, então 340 cai sobre o último dia.
    fireEvent.mouseMove(container.querySelector(".recharts-wrapper")!, { clientX: 340, clientY: 100 });

    expect(screen.getByText("ontem · qua, 16 set")).toBeTruthy();
    expect(screen.getByText("1.200 visitantes")).toBeTruthy();
    expect(screen.getByText("Anterior: 1.000")).toBeTruthy();
    expect(screen.getByText(/↑\s*20,0%/)).toBeTruthy();
  });
});

describe("DicaDoDia", () => {
  const dica = (p: PontoDoMovimento, comAnterior = true) =>
    render(
      <DicaDoDia
        active
        payload={[{ payload: p, value: p.visitantes, dataKey: "visitantes" }]}
        ultimoDia="2026-09-17"
        comAnterior={comAnterior}
      />,
    );

  it("diz o dia, os Visitantes e a comparação com o dia correspondente do anterior", () => {
    dica(ponto("2026-09-15", 1500, "2026-09-08", 1000, 0.5));

    expect(screen.getByText("ter, 15 set")).toBeTruthy();
    expect(screen.getByText("1.500 visitantes")).toBeTruthy();
    expect(screen.getByText("Anterior: 1.000")).toBeTruthy();
    expect(screen.getByText(/↑\s*50,0%/)).toBeTruthy();
  });

  it("queda aparece com a seta para baixo, sem sinal de menos", () => {
    dica(ponto("2026-09-15", 750, "2026-09-08", 1000, -0.25));

    expect(screen.getByText(/↓\s*25,0%/)).toBeTruthy();
    expect(screen.queryByText(/-25,0%/)).toBeNull();
  });

  it("no dia em que o anterior é 0, mostra 'Anterior: 0' sem porcentagem", () => {
    dica(ponto("2026-09-15", 1500, "2026-09-08", 0, null));

    expect(screen.getByText("Anterior: 0")).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("um Visitante só, no singular", () => {
    dica(ponto("2026-09-15", 1, "2026-09-08", 0, null));

    expect(screen.getByText("1 visitante")).toBeTruthy();
  });

  it("sem período anterior no gráfico, não fala dele", () => {
    dica(ponto("2026-09-15", 1500, "2026-09-08", 0, null), false);

    expect(screen.queryByText(/Anterior/)).toBeNull();
  });

  it("fora do dedo e do mouse, não mostra nada", () => {
    const { container } = render(<DicaDoDia active={false} payload={[]} ultimoDia="2026-09-17" comAnterior />);

    expect(container.textContent).toBe("");
  });
});
