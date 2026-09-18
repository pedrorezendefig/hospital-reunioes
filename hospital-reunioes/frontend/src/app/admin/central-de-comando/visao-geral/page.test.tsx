/**
 * @vitest-environment jsdom
 */

/**
 * A página da Visão Geral lê o período do endereço (issue #814).
 *
 * Porte de "troca os números e o rótulo ao mudar o período (?periodo=7d)" do
 * `page.test.tsx` do repositório antigo: o período vem do `?periodo=`, e o que
 * se digita errado vira o padrão de 28 dias, sem tela de erro.
 */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "token-de-teste", userId: "auth-1", userEmail: "diretor@hsm", loading: false }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import VisaoGeralPage from "./page";

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

const sp = (periodo?: string) => Promise.resolve(periodo === undefined ? {} : { periodo });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a página da Visão Geral", () => {
  it("pede o período que está no endereço", async () => {
    servidor();

    render(await VisaoGeralPage({ searchParams: sp("90d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/visao-geral?periodo=90d"]));
  });

  it("sem período no endereço, pede o de 28 dias", async () => {
    servidor();

    render(await VisaoGeralPage({ searchParams: sp() }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/visao-geral?periodo=28d"]));
  });

  it("com um período que não existe, pede o de 28 dias em vez de mostrar erro", async () => {
    servidor();

    render(await VisaoGeralPage({ searchParams: sp("30d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/visao-geral?periodo=28d"]));
  });
});
