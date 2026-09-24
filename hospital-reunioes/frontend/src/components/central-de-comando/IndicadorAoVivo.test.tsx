/**
 * @vitest-environment jsdom
 */

/**
 * O indicador Ao vivo da Visão Geral (issue #816, ADR 0058, ADR 0050 decisão 9).
 *
 * O Ao vivo é o único número em tempo real da Central (glossário, "Ao vivo"):
 * quantas pessoas estão no Site agora, lido direto da fonte, sem cache. O
 * indicador consulta a cada 30 segundos e ao voltar o foco, para quando a tela
 * sai, e degrada em silêncio: se a consulta falha, ele mantém o último número
 * ou some, nunca mostra zero nem derruba a tela.
 *
 * O servidor é falso; as asserções olham o que a pessoa vê (o número e o
 * rótulo) e as consultas que o indicador dispara (endereço, token e o ritmo).
 * O relógio é falso, no molde do Quadro de Demandas (a outra tela da consulta
 * periódica), para medir o ritmo sem esperar 30 segundos de verdade.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndicadorAoVivo } from "./IndicadorAoVivo";

const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null }));

// A sessão é lida a cada consulta (a tela fica aberta por horas, e o token da
// abertura vence em 1 hora), como no `useTelaDaCentral`.
vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: () => Promise.resolve(sessao.token ?? undefined),
}));

const CAMINHO_AO_VIVO = "/api/admin/central-de-comando/ao-vivo";

type Chamada = { url: string; autorizacao: string | null };
let chamadas: Chamada[] = [];
type Resposta = { status: number; corpo: unknown } | "erro-de-rede";
let resposta: Resposta = { status: 200, corpo: { pessoas: 0 } };

function responderCom(nova: Resposta) {
  resposta = nova;
}

/** Deixa o relógio andar `ms` com o React acompanhando (molde do Quadro). */
async function passar(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

/** Espera as consultas em voo (getAuthToken e fetch) assentarem. */
async function assentar() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function esconderAba(escondida: boolean) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => (escondida ? "hidden" : "visible"),
  });
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  sessao.token = "token-de-teste";
  chamadas = [];
  resposta = { status: 200, corpo: { pessoas: 0 } };
  // A aba começa à vista (um teste anterior pode tê-la deixado escondida). Sem
  // `act` aqui: ainda não há componente montado para o evento alcançar.
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, autorizacao: new Headers(init?.headers).get("Authorization") });
      if (resposta === "erro-de-rede") throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify(resposta.corpo), {
        status: resposta.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Indicador Ao vivo: o número de agora", () => {
  it("mostra quantas pessoas estão no Site agora", async () => {
    responderCom({ status: 200, corpo: { pessoas: 12 } });

    render(<IndicadorAoVivo />);

    expect(await screen.findByText("12")).toBeTruthy();
    expect(screen.getByText(/no site agora/i)).toBeTruthy();
  });

  it("consulta o endereço do Ao vivo com o token da sessão", async () => {
    responderCom({ status: 200, corpo: { pessoas: 3 } });

    render(<IndicadorAoVivo />);

    expect(await screen.findByText("3")).toBeTruthy();
    expect(chamadas[0]).toEqual({ url: CAMINHO_AO_VIVO, autorizacao: "Bearer token-de-teste" });
  });

  it("o leitor de tela acompanha só o número, e não o bloco inteiro", async () => {
    responderCom({ status: 200, corpo: { pessoas: 12 } });

    const { container } = render(<IndicadorAoVivo />);
    const numero = await screen.findByText("12");

    // A região viva é o número: o rótulo "no site agora" não é reanunciado a
    // cada consulta de 30 segundos.
    const regioesVivas = container.querySelectorAll("[aria-live]");
    expect(regioesVivas).toHaveLength(1);
    expect(regioesVivas[0]).toBe(numero);
    expect(numero.getAttribute("aria-live")).toBe("polite");
  });

  it("o ponto que pulsa para quando a pessoa pede menos movimento", async () => {
    responderCom({ status: 200, corpo: { pessoas: 12 } });

    const { container } = render(<IndicadorAoVivo />);
    await screen.findByText("12");

    const pulsante = container.querySelector(".animate-ping");
    expect(pulsante).not.toBeNull();
    expect(pulsante?.classList.contains("motion-reduce:animate-none")).toBe(true);
  });

  it("sem sessão, não consulta e não mostra nada", async () => {
    sessao.token = null;
    responderCom({ status: 200, corpo: { pessoas: 3 } });

    render(<IndicadorAoVivo />);
    await assentar();

    expect(chamadas).toEqual([]);
    expect(screen.queryByText(/no site agora/i)).toBeNull();
  });
});

describe("Indicador Ao vivo: o ritmo da consulta", () => {
  it("consulta sozinho a cada 30 segundos", async () => {
    responderCom({ status: 200, corpo: { pessoas: 5 } });

    render(<IndicadorAoVivo />);
    await screen.findByText("5");
    expect(chamadas).toHaveLength(1);

    // 30_000 à mão: medir contra a própria constante ficaria verde com ela
    // trocada para uma hora, que é o mesmo que não ter Ao vivo.
    await passar(30_000);
    expect(chamadas).toHaveLength(2);

    await passar(30_000);
    expect(chamadas).toHaveLength(3);
  });

  it("consulta na hora ao voltar o foco para a janela", async () => {
    responderCom({ status: 200, corpo: { pessoas: 5 } });

    render(<IndicadorAoVivo />);
    await screen.findByText("5");
    expect(chamadas).toHaveLength(1);

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });

    expect(chamadas).toHaveLength(2);
  });

  it("não consulta a aba escondida, e volta a consultar quando ela reaparece", async () => {
    responderCom({ status: 200, corpo: { pessoas: 5 } });

    render(<IndicadorAoVivo />);
    await screen.findByText("5");
    expect(chamadas).toHaveLength(1);

    esconderAba(true);
    await passar(30_000);
    expect(chamadas).toHaveLength(1);

    // A irmã de presença: com a aba de volta, o relógio volta a valer.
    esconderAba(false);
    await passar(30_000);
    expect(chamadas).toHaveLength(2);
  });

  it("para de consultar depois que a tela sai", async () => {
    responderCom({ status: 200, corpo: { pessoas: 5 } });

    const { unmount } = render(<IndicadorAoVivo />);
    await screen.findByText("5");
    await passar(30_000);
    expect(chamadas).toHaveLength(2);

    unmount();

    await passar(120_000);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(chamadas).toHaveLength(2);
  });
});

describe("Indicador Ao vivo: degradação silenciosa", () => {
  it("com a fonte fora, mantém o último número em vez de mostrar zero", async () => {
    responderCom({ status: 200, corpo: { pessoas: 8 } });

    render(<IndicadorAoVivo />);
    await screen.findByText("8");

    responderCom({ status: 502, corpo: { detail: "O Google Analytics não respondeu." } });
    await passar(30_000);

    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("com a rede fora, mantém o último número em vez de zerar", async () => {
    responderCom({ status: 200, corpo: { pessoas: 8 } });

    render(<IndicadorAoVivo />);
    await screen.findByText("8");

    responderCom("erro-de-rede");
    await passar(30_000);

    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("sem número ainda e com a consulta falhando, não mostra nada nem zero", async () => {
    responderCom({ status: 502, corpo: { detail: "fora" } });

    render(<IndicadorAoVivo />);
    await assentar();

    expect(screen.queryByText(/no site agora/i)).toBeNull();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("uma resposta sem o número não vira zero", async () => {
    // Um 200 com corpo inesperado (proxy, deploy no meio) não é "ninguém".
    responderCom({ status: 200, corpo: { outro: "campo" } });

    render(<IndicadorAoVivo />);
    await assentar();

    expect(screen.queryByText(/no site agora/i)).toBeNull();
    expect(screen.queryByText("0")).toBeNull();
  });
});
