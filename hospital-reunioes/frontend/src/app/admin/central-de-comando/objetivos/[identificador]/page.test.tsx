/**
 * @vitest-environment jsdom
 */

/**
 * A página da lente lê o identificador e o período do endereço (issue #820). Um
 * Objetivo do Instagram não tem 90 dias, então 90 dias no endereço vira o padrão
 * de 28, sem tela de erro.
 */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: async () => "token-de-teste",
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import LenteDoObjetivoPage from "./page";

const pedidos: string[] = [];

function servidor() {
  pedidos.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      return new Response(JSON.stringify({ detail: "fora do teste" }), { status: 503 });
    }),
  );
}

const params = (identificador: string) => Promise.resolve({ identificador });
const sp = (periodo?: string) => Promise.resolve(periodo === undefined ? {} : { periodo });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a página da lente de um Objetivo", () => {
  it("pede a lente do identificador e do período que estão no endereço", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("site-visitantes"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/site-visitantes?periodo=90d"]),
    );
  });

  it("um Objetivo do Instagram não tem 90 dias: cai no padrão de 28", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("instagram-seguidores"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/instagram-seguidores?periodo=28d"]),
    );
  });
});
