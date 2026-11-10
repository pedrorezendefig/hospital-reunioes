/**
 * @vitest-environment jsdom
 */

/**
 * A tela da aba Tecnologia (issue #636, PRD #634; ADR 0077).
 *
 * Desde a issue #1386 a aba é uma tela só: o chat do Assistente, com a lista
 * das conversas ao lado. O Quadro, o Painel, a tela de Produtos, o formulário à
 * mão e a tela antiga do Planejamento saíram do código, e com eles as abas e o
 * que a aba carregava para elas (Produtos, pessoas, o "eu" do Vínculo).
 */

import { readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import { ABERTURA } from "./ChatDaTecnologia";
import { TecnologiaModulo } from "./TecnologiaModulo";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "token-de-teste", userId: "auth-1", userEmail: "p1@hsm", loading: false }),
}));

let pedidos: string[] = [];

function montar() {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      return { ok: true, status: 200, json: async () => [] } as unknown as Response;
    }),
  );
  render(
    <ToastProvider>
      <TecnologiaModulo />
    </ToastProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** As páginas da área `/admin/tecnologia`, lidas do disco: no Next, a pasta com `page.tsx` é a rota. */
function paginasDaAba(): string[] {
  const raiz = resolve(process.cwd(), "src/app/admin/tecnologia");
  const achadas: string[] = [];
  const visitar = (pasta: string) => {
    for (const entrada of readdirSync(pasta, { withFileTypes: true })) {
      const caminho = join(pasta, entrada.name);
      if (entrada.isDirectory()) visitar(caminho);
      else if (entrada.name === "page.tsx") achadas.push(relative(raiz, caminho));
    }
  };
  visitar(raiz);
  return achadas.sort();
}

describe("A aba é o chat do agente, e só (issue #1386, ADR 0077)", () => {
  it("abre no chat, sem abas de Quadro nem de Painel", async () => {
    montar();

    expect(await screen.findByText(ABERTURA)).toBeTruthy();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByText("Quadro")).toBeNull();
    expect(screen.queryByText("Painel")).toBeNull();
  });

  it("só pede ao servidor a lista das conversas e quem está logado: nada de Produtos, pessoas ou Vínculo", async () => {
    montar();

    // `eu` diz se quem está logado é Desenvolvedor (issue #1531, ADR 0083).
    await waitFor(() => expect(pedidos.length).toBe(2));
    expect([...pedidos].sort()).toEqual(["/api/admin/tecnologia/chat", "/api/admin/tecnologia/eu"]);
  });

  it("a área da Tecnologia só tem a página da aba", () => {
    const paginas = paginasDaAba();

    // O piso: a varredura enxerga a página que fica. Sem ele, uma pasta lida
    // errado passaria vazia por "não tem as páginas antigas".
    expect(paginas).toContain("page.tsx");
    expect(paginas).toEqual(["page.tsx"]);
  });
});
