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

afterEach(() => {
  cleanup();
  sessao.participante = null;
});

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

  it("o Super admin vê a aba Ana, que por ora diz Em preparação", () => {
    sessao.participante = pessoa({ access_profile: "super_admin" });

    render(<Manual paginas={PAGINAS} />);

    const abas = screen.getAllByRole("tab").map((aba) => aba.textContent?.trim());
    expect(abas).toEqual(["Aplicativo do Hospital", "Ana"]);
    expect(screen.queryByText("Em preparação")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Ana" }));

    expect(screen.getByText("Em preparação")).toBeTruthy();
    expect(screen.queryByText("Texto de Reuniões.")).toBeNull();
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

  it("o bloco fluxograma vira o desenho do Fluxograma, e não código cru", () => {
    sessao.participante = pessoa({ access_profile: null, perfil_pop: "coordenador" });

    const { container } = render(<Manual paginas={PAGINAS} />);

    expect(container.querySelector('[data-passo="abrir"]')?.textContent).toContain("Abrir o POP");
    expect(container.querySelector("pre")).toBeNull();
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
