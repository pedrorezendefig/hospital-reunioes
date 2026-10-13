/**
 * @vitest-environment jsdom
 */

/**
 * O cartão "R$ incluído pela coordenação" no Painel (issue #1143). O servidor
 * só manda a chave `coordenacao` para quem tem a Conferência da coordenação:
 * sem ela, o cartão não aparece.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Painel } from "@/lib/contas-medicas/painel";

import { TelaDoPainel } from "./TelaDoPainel";

vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
      cloneElement(children, { width: 600, height: 240 }),
  };
});

const BASE: Painel = {
  semana: { inicio: "2026-10-05", fim: "2026-10-11" },
  filtros: { operadoras: [] },
  nota_media: { semana: 70, anterior: 72 },
  contas_concluidas: { total: 3 },
  valor_apontado: { total: 315, ja_incluido: 250 },
  nao_procede: { linhas: 2, de: 10, taxa: 0.2 },
  producao: [],
};

afterEach(cleanup);

describe("o cartão da coordenação no Painel", () => {
  it("aparece com o R$ incluído quando o servidor manda a chave", () => {
    render(<TelaDoPainel painel={{ ...BASE, coordenacao: { valor_incluido: 1250.5, lembretes_incluidos: 4 } }} />);

    const cartao = screen.getByRole("region", { name: "R$ incluído pela coordenação" });
    expect(cartao.textContent).toContain("R$ 1.250,50");
    expect(cartao.textContent).toContain("4 lembretes incluídos");
    // Fora do R$ apontado: o cartão dele continua com os números do servidor.
    expect(screen.getByRole("region", { name: "R$ apontado" }).textContent).toContain("Já incluídos: R$ 250,00");
  });

  it("não aparece sem a chave, nem para quem vê só a produção", () => {
    render(<TelaDoPainel painel={BASE} />);
    expect(screen.queryByRole("region", { name: "R$ incluído pela coordenação" })).toBeNull();
    cleanup();

    render(<TelaDoPainel painel={{ semana: BASE.semana, filtros: BASE.filtros, producao: [] }} />);
    expect(screen.queryByRole("region", { name: "R$ incluído pela coordenação" })).toBeNull();
  });
});
