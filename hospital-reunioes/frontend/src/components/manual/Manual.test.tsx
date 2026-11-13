/**
 * @vitest-environment jsdom
 */

/**
 * A tela do manual (issue #1718, ADR 0094, decisões 1, 2 e 4).
 *
 * Teste de ausência sem irmão de presença é vazio: uma tela que não mostrasse
 * nada passaria em "não vê a página de POPs". Por isso todo caso que afirma
 * ausência confere, no mesmo render, o que a pessoa VÊ.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import type { PaginaDoManual } from "@/lib/manual/paginas";
import { Manual } from "./Manual";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: sessao.participante,
    loading: false,
    error: null,
  }),
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/manual" }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

afterEach(() => {
  cleanup();
  sessao.participante = null;
  vi.unstubAllGlobals();
});

/**
 * A rota do Retrato no backend: com `status` 200 entrega uma página mínima do
 * Retrato e os dados; com outro status, recusa tudo. Devolve os pedidos feitos.
 */
function retratoNoBackend(status: number): { url: string; autorizacao: string | null }[] {
  const pedidos: { url: string; autorizacao: string | null }[] = [];
  const arquivos: Record<string, string> = {
    "/api/admin/manual/ana/retrato/index.html": "<!doctype html><html><head></head><body>Retrato</body></html>",
    "/api/admin/manual/ana/retrato/dados/retrato.json": "{}",
  };
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    pedidos.push({ url, autorizacao: new Headers(init?.headers).get("Authorization") });
    if (status !== 200 || !(url in arquivos)) {
      return new Response(JSON.stringify({ detail: "O Retrato da Ana ainda não está ligado" }), { status });
    }
    return new Response(arquivos[url], { status: 200 });
  });
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:retrato-de-teste", revokeObjectURL: () => {} }));
  return pedidos;
}

function pessoa(papeis: Partial<CurrentParticipante>): CurrentParticipante {
  return { id: "p1", nome_completo: "Fulana de Tal", email: "fulana@hsm", ...papeis };
}

const REUNIOES: PaginaDoManual = {
  pasta: "reunioes-e-pendencias",
  modulo: "reunioes-e-pendencias",
  titulo: "Reuniões e Pendências",
  corpo: "Texto de Reuniões.\n\n## Ver as reuniões do mês\n\n1. Clique em **Calendário**.\n\n![O calendário](calendario.png)",
};

const POPS: PaginaDoManual = {
  pasta: "pops",
  modulo: "pops",
  titulo: "POPs",
  corpo: "Texto dos POPs.\n\n```fluxograma\ninicio abrir 1,1: Abrir o POP\n```",
};

const PAGINAS = [POPS, REUNIOES];

/** Os títulos da lista de páginas, na ordem. */
function paginasDaLista(): string[] {
  const lista = screen.getByRole("navigation", { name: "Páginas do manual" });
  return within(lista)
    .getAllByRole("button")
    .map((botao) => botao.textContent?.trim() ?? "");
}

describe("quem vê cada página", () => {
  it("o Facilitador vê Reuniões e Pendências, e não vê a página de POPs", () => {
    sessao.participante = pessoa({ access_profile: "regular" });

    render(<Manual paginas={PAGINAS} />);

    expect(paginasDaLista()).toEqual(["Reuniões e Pendências"]);
    expect(screen.getByText("Texto de Reuniões.")).toBeTruthy();
    expect(screen.queryByText("Texto dos POPs.")).toBeNull();
  });

  it("quem só é dos POPs vê a página de POPs, e não vê Reuniões e Pendências", () => {
    sessao.participante = pessoa({ access_profile: null, perfil_pop: "coordenador" });

    render(<Manual paginas={PAGINAS} />);

    expect(paginasDaLista()).toEqual(["POPs"]);
    expect(screen.getByText("Texto dos POPs.")).toBeTruthy();
    expect(screen.queryByText("Texto de Reuniões.")).toBeNull();
  });

  it("quem tem os dois módulos vê as duas páginas, e troca de uma para a outra", () => {
    sessao.participante = pessoa({ access_profile: "regular", perfil_pop: "coordenador" });

    render(<Manual paginas={PAGINAS} />);

    expect(paginasDaLista()).toEqual(["Reuniões e Pendências", "POPs"]);
    fireEvent.click(screen.getByRole("button", { name: "POPs" }));
    expect(screen.getByText("Texto dos POPs.")).toBeTruthy();
    expect(screen.queryByText("Texto de Reuniões.")).toBeNull();
  });
});

describe("a aba Ana", () => {
  it("quem não é Super admin não vê a aba Ana, e vê a do Aplicativo do Hospital", () => {
    sessao.participante = pessoa({ access_profile: "secretaria" });

    render(<Manual paginas={PAGINAS} />);

    const abas = screen.getAllByRole("tab").map((aba) => aba.textContent?.trim());
    expect(abas).toEqual(["Aplicativo do Hospital"]);
  });

  it("o Super admin abre a aba Ana e vê o Retrato num quadro isolado da página do app", async () => {
    sessao.participante = pessoa({ access_profile: "super_admin" });
    const pedidos = retratoNoBackend(200);

    render(<Manual paginas={PAGINAS} />);

    const abas = screen.getAllByRole("tab").map((aba) => aba.textContent?.trim());
    expect(abas).toEqual(["Aplicativo do Hospital", "Ana"]);
    expect(screen.queryByTitle("Retrato da Ana")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Ana" }));

    const quadro = await screen.findByTitle("Retrato da Ana");
    expect(quadro.tagName).toBe("IFRAME");
    expect(quadro.getAttribute("src")).toBe("blob:retrato-de-teste");
    // Isolado: roda o script do Retrato, mas sem a origem do app, então não
    // lê o login, o armazenamento nem o DOM da página do manual.
    expect(quadro.getAttribute("sandbox")?.split(/\s+/)).toEqual(["allow-scripts"]);
    expect(quadro.className.split(/\s+/)).toContain("w-full");
    expect(screen.queryByText("Texto de Reuniões.")).toBeNull();

    expect(pedidos[0]).toEqual({
      url: "/api/admin/manual/ana/retrato/index.html",
      autorizacao: "Bearer token-de-teste",
    });
    expect(pedidos.map((p) => p.url)).toContain("/api/admin/manual/ana/retrato/dados/retrato.json");
  });

  it("sem o Retrato ligado, a aba Ana diz que ele ainda não está ligado, sem erro técnico", async () => {
    sessao.participante = pessoa({ access_profile: "super_admin" });
    retratoNoBackend(503);

    render(<Manual paginas={PAGINAS} />);
    fireEvent.click(screen.getByRole("tab", { name: "Ana" }));

    expect(await screen.findByText("O Retrato da Ana ainda não está ligado")).toBeTruthy();
    expect(screen.queryByTitle("Retrato da Ana")).toBeNull();
    expect(screen.queryByText(/503/)).toBeNull();
  });
});

describe("o desenho da página", () => {
  it("o print sai do lado do Markdown e cabe na largura da tela", () => {
    sessao.participante = pessoa({ access_profile: "regular" });

    render(<Manual paginas={PAGINAS} />);

    const print = screen.getByRole("img", { name: "O calendário" });
    expect(print.getAttribute("src")).toBe("/manual/reunioes-e-pendencias/calendario.png");
    expect(print.className.split(/\s+/)).toEqual(expect.arrayContaining(["max-w-full", "h-auto"]));
  });

  it("no celular a lista e a página viram uma coluna, e lado a lado a partir do md", () => {
    sessao.participante = pessoa({ access_profile: "regular" });

    const { container } = render(<Manual paginas={PAGINAS} />);

    const colunas = container.querySelector("[data-colunas-do-manual]");
    expect(colunas?.className.split(/\s+/)).toEqual(
      expect.arrayContaining(["flex", "flex-col", "md:flex-row"])
    );
  });

  it("o bloco fluxograma da página vira o desenho do Fluxograma", () => {
    sessao.participante = pessoa({ access_profile: null, perfil_pop: "coordenador" });

    const { container } = render(<Manual paginas={PAGINAS} />);

    const passo = container.querySelector('[data-fluxograma] [data-passo="abrir"]');
    expect(passo?.textContent).toContain("Abrir o POP");
  });

  it("o título da página e os títulos das tarefas saem como títulos", () => {
    sessao.participante = pessoa({ access_profile: "regular" });

    render(<Manual paginas={PAGINAS} />);

    expect(screen.getByRole("heading", { level: 2, name: "Reuniões e Pendências" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "Ver as reuniões do mês" })).toBeTruthy();
  });

  it("quem não tem página nenhuma recebe um aviso, e não uma tela em branco", () => {
    sessao.participante = pessoa({ access_profile: null, perfil_pop: "coordenador" });

    render(<Manual paginas={[REUNIOES]} />);

    expect(screen.getByText(/ainda não tem página/)).toBeTruthy();
  });
});
