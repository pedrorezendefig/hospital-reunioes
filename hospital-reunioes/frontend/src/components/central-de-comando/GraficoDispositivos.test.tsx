/**
 * @vitest-environment jsdom
 */

/**
 * A rosca de dispositivos da tela Dados do Google (issue #817).
 *
 * Porte de `components/analytics/DeviceDonut.test.tsx` do repositório antigo,
 * agora em `recharts`. A rosca tem tamanho fixo (cabe no celular), então o
 * `recharts` roda de verdade aqui, sem `ResponsiveContainer` para dublar. Os
 * percentuais chegam prontos do backend, somando 100: a tela só escreve.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GraficoDispositivos, type DispositivoDoPayload } from "./GraficoDispositivos";

afterEach(cleanup);

const DISPOSITIVOS: DispositivoDoPayload[] = [
  { chave: "celular", rotulo: "Celular", visitas: 7100, percentual: 71 },
  { chave: "computador", rotulo: "Computador", visitas: 2300, percentual: 23 },
  { chave: "tablet", rotulo: "Tablet", visitas: 600, percentual: 6 },
];

describe("GraficoDispositivos", () => {
  it("destaca o mais usado no centro da rosca, com a fatia e o nome", () => {
    render(<GraficoDispositivos dispositivos={DISPOSITIVOS} />);

    const centro = screen.getByTestId("centro-da-rosca");
    expect(centro.textContent).toBe("71%celular");
  });

  it("lista cada dispositivo com o rótulo em português, a fatia e as Visitas", () => {
    render(<GraficoDispositivos dispositivos={DISPOSITIVOS} />);

    const itens = within(screen.getByRole("list", { name: "Visitas por dispositivo" })).getAllByRole("listitem");
    expect(itens.map((item) => item.textContent)).toEqual([
      "Celular71%7.100 visitas",
      "Computador23%2.300 visitas",
      "Tablet6%600 visitas",
    ]);
  });

  it("desenha uma fatia por dispositivo, com as cores dos tokens do app", () => {
    const { container } = render(<GraficoDispositivos dispositivos={DISPOSITIVOS} />);

    const fatias = [...container.querySelectorAll("path.recharts-sector")];
    expect(fatias.map((fatia) => fatia.getAttribute("fill"))).toEqual([
      "var(--color-primary)",
      "var(--color-primary-light)",
      "var(--color-info)",
    ]);
  });

  it("a cor de cada dispositivo é a mesma na rosca e na legenda, mesmo com outro na frente", () => {
    const computadorNaFrente: DispositivoDoPayload[] = [
      { chave: "computador", rotulo: "Computador", visitas: 12000, percentual: 50 },
      { chave: "celular", rotulo: "Celular", visitas: 11000, percentual: 46 },
      { chave: "tablet", rotulo: "Tablet", visitas: 1000, percentual: 4 },
    ];

    const { container } = render(<GraficoDispositivos dispositivos={computadorNaFrente} />);

    const fatias = [...container.querySelectorAll("path.recharts-sector")].map((f) => f.getAttribute("fill"));
    const marcas = [...container.querySelectorAll("[data-cor]")].map((m) => m.getAttribute("data-cor"));
    expect(fatias).toEqual(["var(--color-primary-light)", "var(--color-primary)", "var(--color-info)"]);
    expect(marcas).toEqual(fatias);
    expect(screen.getByTestId("centro-da-rosca").textContent).toBe("50%computador");
  });

  it("fatia com menos de 1% aparece como '<1%', e não zero", () => {
    render(
      <GraficoDispositivos
        dispositivos={[
          { chave: "celular", rotulo: "Celular", visitas: 995, percentual: 100 },
          { chave: "tablet", rotulo: "Tablet", visitas: 5, percentual: 0 },
        ]}
      />,
    );

    expect(screen.getByText("<1%")).toBeTruthy();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("uma Visita só, no singular", () => {
    render(<GraficoDispositivos dispositivos={[{ chave: "tablet", rotulo: "Tablet", visitas: 1, percentual: 100 }]} />);

    expect(screen.getByText("1 visita")).toBeTruthy();
  });

  it("a rosca é enfeite para o leitor de tela: quem lê a fatia é a lista", () => {
    render(<GraficoDispositivos dispositivos={DISPOSITIVOS} />);

    expect(screen.getByTestId("rosca").getAttribute("aria-hidden")).toBe("true");
  });

  it("mostra o estado vazio quando não há dispositivo com Visita no período", () => {
    const { container } = render(<GraficoDispositivos dispositivos={[]} />);

    expect(screen.getByText("Sem dados de dispositivo para este período.")).toBeTruthy();
    expect(container.querySelector("path.recharts-sector")).toBeNull();
  });
});
