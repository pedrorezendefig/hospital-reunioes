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

import { cleanup, render, screen } from "@testing-library/react";
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
    expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/google-reputacao"]);
  });

  it("mostra a nota, as avaliações novas do mês e a tendência", async () => {
    servidor(medida());

    render(<NotaNoGoogle />);

    expect(await screen.findByText("2,6 de 5")).toBeTruthy();
    expect(screen.getByText("1.641 avaliações no total")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText(/diferença do total de avaliações entre a primeira e a última leitura do mês/i)).toBeTruthy();
    expect(screen.getByText("Melhorou")).toBeTruthy();
    expect(screen.getByText(/2,4 de 5 no fim do mês anterior/)).toBeTruthy();
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
      },
    });

    render(<NotaNoGoogle />);

    expect(await screen.findByText(/a nota do google não está sendo medida/i)).toBeTruthy();
    expect(screen.queryByText(/de 5/)).toBeNull();
  });
});
