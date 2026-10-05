/**
 * @vitest-environment jsdom
 */

/**
 * A página da lente lê o identificador e o período do endereço (issue #820).
 * Quais períodos cada lente tem é o backend quem diz, no payload (issue #847):
 * a página só descarta o que não é período nenhum. O período que a lente não
 * tem (90 dias no Instagram) cai no padrão dentro da `LenteDoObjetivo`.
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

  it("não decide os períodos pelo nome do Objetivo: quem diz é o backend (issue #847)", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("instagram-seguidores"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/instagram-seguidores?periodo=90d"]),
    );
  });

  it("período que não existe no endereço vira o padrão de 28", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("site-visitantes"), searchParams: sp("365d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/site-visitantes?periodo=28d"]),
    );
  });
});
