/**
 * @vitest-environment jsdom
 */

/**
 * A tela da aba Tecnologia (issue #636, PRD #634; ADR 0077).
 *
 * Desde a issue #1386 a aba é o chat do Assistente, com a lista das conversas
 * ao lado. O Quadro, o Painel, a tela de Produtos, o formulário à mão e a tela
 * antiga do Planejamento saíram do código, e com eles o que a aba carregava
 * para elas (Produtos, pessoas, o "eu" do Vínculo). Desde a issue #1556 (ADR
 * 0084, decisão 8) ela tem duas abas: Conversas, o chat, e Entregas.
 */

import { readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import { ABERTURA } from "./ChatDaTecnologia";
import { TecnologiaModulo } from "./TecnologiaModulo";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "token-de-teste", userId: "auth-1", userEmail: "p1@hsm", loading: false }),
}));

let pedidos: string[] = [];

function montar({ desenvolvedor = false }: { desenvolvedor?: boolean } = {}) {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      const corpo = url.endsWith("/eu")
        ? { desenvolvedor }
        : url.includes("/entregas")
          ? { agrupar: "semana", periodos: [], entregas: [], responsaveis: [] }
          : [];
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
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

describe("A aba abre no chat, com Conversas e Entregas (issues #1386 e #1556)", () => {
  it("abre no chat, com as abas Conversas e Entregas e sem Quadro nem Painel", async () => {
    montar();

    expect(await screen.findByText(ABERTURA)).toBeTruthy();
    const abas = screen.getAllByRole("tab").map((aba) => aba.textContent);
    expect(abas).toEqual(["Conversas", "Entregas"]);
    expect(screen.getByRole("tab", { name: "Conversas" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByText("Quadro")).toBeNull();
    expect(screen.queryByText("Painel")).toBeNull();
  });

  it.each([
    ["o diretor", false],
    ["o Desenvolvedor", true],
  ])("%s abre as Entregas", async (_quem, desenvolvedor) => {
    montar({ desenvolvedor });
    await screen.findByText(ABERTURA);

    fireEvent.click(screen.getByRole("tab", { name: "Entregas" }));

    expect(screen.getByRole("tab", { name: "Entregas" }).getAttribute("aria-selected")).toBe("true");
    await waitFor(() => expect(pedidos.some((url) => url.startsWith("/api/admin/tecnologia/entregas"))).toBe(true));
    expect(await screen.findByText("Nenhuma entrega com esses filtros.")).toBeTruthy();
    // O chat fica guardado atrás da aba: voltar a Conversas não recomeça a conversa.
    expect(screen.getByText(ABERTURA).closest("[hidden]")).not.toBeNull();
  });

  it("só pede ao servidor a lista das conversas e quem está logado: nada de Produtos, pessoas ou Vínculo", async () => {
    montar();

    // `eu` diz se quem está logado é Desenvolvedor (issue #1531, ADR 0083).
    await waitFor(() => expect(pedidos.length).toBe(2));
    expect([...pedidos].sort()).toEqual(["/api/admin/tecnologia/chat", "/api/admin/tecnologia/eu"]);
  });

  it("na tela larga a aba Conversas se chama Quadro e abre nas colunas (issue #1642, ADR 0090)", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((consulta: string) => ({
        matches: consulta === "(min-width: 1280px)",
        media: consulta,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    montar();

    expect(await screen.findByRole("region", { name: "Quadro" })).toBeTruthy();
    expect(screen.getAllByRole("tab").map((aba) => aba.textContent)).toEqual(["Quadro", "Entregas"]);
    expect(screen.getByRole("tab", { name: "Quadro" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel", { name: "Quadro" })).toBeTruthy();
  });

  it("Ver todos nas Entregas, no pé da coluna Entregue, abre a aba Entregas (issue #1644)", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((consulta: string) => ({
        matches: consulta === "(min-width: 1280px)",
        media: consulta,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    montar();
    const quadro = await screen.findByRole("region", { name: "Quadro" });

    // Sempre à vista, mesmo com a coluna vazia: as Entregas guardam o que passou dos 30 dias.
    const entregue = within(quadro).getByRole("region", { name: "Entregue" });
    fireEvent.click(within(entregue).getByRole("button", { name: "Ver todos nas Entregas" }));

    expect(screen.getByRole("tab", { name: "Entregas" }).getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByText("Nenhuma entrega com esses filtros.")).toBeTruthy();
    // O Quadro fica montado atrás da aba, escondido.
    expect(quadro.closest("[hidden]")).not.toBeNull();
  });

  it("a área da Tecnologia só tem a página da aba", () => {
    const paginas = paginasDaAba();

    // O piso: a varredura enxerga a página que fica. Sem ele, uma pasta lida
    // errado passaria vazia por "não tem as páginas antigas".
    expect(paginas).toContain("page.tsx");
    expect(paginas).toEqual(["page.tsx"]);
  });
});
