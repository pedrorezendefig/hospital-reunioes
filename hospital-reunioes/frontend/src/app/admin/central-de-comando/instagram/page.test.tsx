/**
 * @vitest-environment jsdom
 */

/**
 * A página do Instagram lê o período do endereço, só 7 e 28 dias (issue #819).
 *
 * No molde do `page.test.tsx` de Dados do Google: o período vem do `?periodo=`,
 * e o que se digita fora de 7 e 28 (90 dias, por exemplo) vira o padrão de 28,
 * sem tela de erro, porque a fonte do Instagram entrega no máximo 30 dias.
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

import InstagramPage from "./page";

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

describe("a página do Instagram", () => {
  it("pede o período de 7 dias que está no endereço e o marca no seletor", async () => {
    servidor();

    render(await InstagramPage({ searchParams: sp("7d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/instagram?periodo=7d"]));
    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("aria-current")).toBe("page");
  });

  it("sem período no endereço, pede o de 28 dias", async () => {
    servidor();

    render(await InstagramPage({ searchParams: sp() }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/instagram?periodo=28d"]));
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("aria-current")).toBe("page");
  });

  it("com 90 dias no endereço, cai no padrão de 28 e não oferece 90 dias", async () => {
    servidor();

    render(await InstagramPage({ searchParams: sp("90d") }));

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/instagram?periodo=28d"]));
    expect(screen.queryByRole("link", { name: "90 dias" })).toBeNull();
  });

  it("não mostra mais o aviso de tela em construção", async () => {
    servidor();

    render(await InstagramPage({ searchParams: sp() }));

    expect(screen.getByRole("heading", { level: 1, name: "Instagram" })).toBeTruthy();
    expect(screen.queryByText(/em construção/i)).toBeNull();
    await waitFor(() => expect(pedidos).toHaveLength(1));
  });
});
