/**
 * @vitest-environment jsdom
 */

/**
 * A página de Dados do Google lê o período do endereço (issue #817).
 *
 * Porte de "oferece o seletor de período (padrão 28 dias)" e "declara o
 * período ativo ao trocar (?periodo=90d)" do `page.test.tsx` de Dados do
 * Google do repositório antigo: o período vem do `?periodo=`, e o que se
 * digita errado vira o padrão de 28 dias, sem tela de erro.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

import DadosDoGooglePage from "./page";

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

describe("a página de Dados do Google", () => {
  it("pede o período que está no endereço e o marca no seletor", async () => {
    servidor();

    render(await DadosDoGooglePage({ searchParams: sp("90d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/dados-do-google?periodo=90d"]));
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("aria-current")).toBe("page");
  });

  it("sem período no endereço, pede o de 28 dias", async () => {
    servidor();

    render(await DadosDoGooglePage({ searchParams: sp() }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/dados-do-google?periodo=28d"]));
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("aria-current")).toBe("page");
  });

  it("com um período que não existe, pede o de 28 dias em vez de mostrar erro", async () => {
    servidor();

    render(await DadosDoGooglePage({ searchParams: sp("30d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/dados-do-google?periodo=28d"]));
  });

  it("não mostra mais o aviso de tela em construção", async () => {
    servidor();

    render(await DadosDoGooglePage({ searchParams: sp() }));

    expect(screen.getByRole("heading", { level: 1, name: "Dados do Google" })).toBeTruthy();
    expect(screen.queryByText(/em construção/i)).toBeNull();
    await waitFor(() => expect(pedidos).toHaveLength(1));
  });
});
