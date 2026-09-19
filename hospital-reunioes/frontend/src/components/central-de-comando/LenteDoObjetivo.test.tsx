/**
 * @vitest-environment jsdom
 */

/**
 * A lente de um Objetivo da Central de Comando (issue #820, ADR 0058).
 *
 * O servidor é falso e a conta fica com ele. As asserções olham o que o Super
 * admin lê para um dado payload, a chamada que a tela faz (endereço, período e
 * token), e o identificador inexistente, que cai na página de não encontrado.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LenteDoObjetivo, type LentePayload } from "./LenteDoObjetivo";

const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null, carregando: false }));
const nav = vi.hoisted(() => ({ notFound: vi.fn() }));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: () =>
    sessao.carregando ? new Promise<string | undefined>(() => {}) : Promise.resolve(sessao.token ?? undefined),
}));

vi.mock("next/navigation", () => ({ notFound: nav.notFound }));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function lente(parcial: Partial<LentePayload> = {}): LentePayload {
  return {
    objetivo: parcial.objetivo ?? {
      id: "instagram-seguidores",
      nome: "Crescer no Instagram",
      descricao: "Aumentar o número de seguidores da conta.",
    },
    periodo: parcial.periodo ?? { chave: "28d", dias: 28 },
    numeros: parcial.numeros ?? [
      { chave: "followers", rotulo: "Seguidores", valor: 18420, crescimento: 312, crescimento_anterior: 248 },
      { chave: "reach", rotulo: "Alcance", valor: 41280, anterior: 37650, variacao: 0.0964 },
    ],
    sugestoes: parcial.sugestoes ?? [],
    frescor: parcial.frescor ?? { atualizado_em: "2026-09-18T13:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

type Chamada = { url: string; autorizacao: string | null };
let chamadas: Chamada[] = [];

function servidor(status: number, corpo: unknown) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      chamadas.push({ url, autorizacao: cabecalhos.get("Authorization") });
      return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

beforeEach(() => {
  sessao.token = "token-de-teste";
  sessao.carregando = false;
  nav.notFound.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a lente de um Objetivo", () => {
  it("mostra os números do Objetivo, com o período e o frescor", async () => {
    servidor(200, lente());

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("18.420")).toBeTruthy();
    expect(screen.getByText("Seguidores")).toBeTruthy();
    expect(screen.getByText("+312 no período")).toBeTruthy();
    expect(screen.getByText("41.280")).toBeTruthy();
    expect(screen.getByText(/últimos 28 dias/)).toBeTruthy();
    expect(screen.getByText(/números de/)).toBeTruthy();
  });

  it("mostra cada sugestão com o porquê", async () => {
    servidor(
      200,
      lente({
        sugestoes: [
          {
            id: "queda-de-alcance",
            titulo: "Seu alcance caiu",
            detalhe: "Vale revisar os horários de publicação.",
            porque: "Alcance -20% no período (de 37.650 para 30.120).",
            tom: "atencao",
          },
        ],
      }),
    );

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("Seu alcance caiu")).toBeTruthy();
    expect(screen.getByText("Alcance -20% no período (de 37.650 para 30.120).")).toBeTruthy();
  });

  it("pede a lente do Objetivo no período, com o token da sessão", async () => {
    servidor(200, lente());

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);
    await screen.findByText("18.420");

    expect(chamadas).toEqual([
      {
        url: "/api/admin/central-de-comando/objetivos/instagram-seguidores?periodo=28d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("identificador inexistente (404) cai na página de não encontrado", async () => {
    servidor(404, { detail: "A Central não tem esse Objetivo." });

    render(<LenteDoObjetivo identificador="nao-existe" periodo="28d" />);

    await waitFor(() => expect(nav.notFound).toHaveBeenCalled());
  });

  it("sem credencial (503) diz o que falta e não mostra número", async () => {
    servidor(503, { detail: "A Central ainda não está ligada à fonte." });

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("A Central ainda não está ligada à fonte.")).toBeTruthy();
    expect(screen.queryByText("18.420")).toBeNull();
    expect(nav.notFound).not.toHaveBeenCalled();
  });

  it("com a fonte fora (502) avisa e não mostra número", async () => {
    servidor(502, { detail: "A fonte não respondeu no tempo esperado." });

    render(<LenteDoObjetivo identificador="contatos" periodo="28d" />);

    expect(await screen.findByText("A fonte não respondeu no tempo esperado.")).toBeTruthy();
    expect(screen.getByText(/Não foi possível buscar os números/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor(200, lente());
    sessao.token = null;

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });
});
