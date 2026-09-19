/**
 * @vitest-environment jsdom
 */

/**
 * A página da galeria dos Objetivos (issue #820): monta a galeria, que pede a
 * lista ao backend sem período (o número de hoje é de 28 dias, no backend).
 */

import { cleanup, render, waitFor } from "@testing-library/react";
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

import ObjetivosPage from "./page";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a página da galeria dos Objetivos", () => {
  it("pede a galeria ao backend", async () => {
    servidor();

    render(<ObjetivosPage />);

    await waitFor(() => expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos"]));
  });
});
