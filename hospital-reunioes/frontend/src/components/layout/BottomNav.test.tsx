/**
 * @vitest-environment jsdom
 */

/**
 * A barra inferior do celular, por perfil (issue #478, PRD #468, D-01).
 *
 * A barra de baixo tem cinco vagas e quatro delas já são fixas (Início,
 * Reuniões, Pendências, Perfil). Sobra uma, e é por isso que o Admin e a
 * Ouvidoria não cabem juntos: quando as duas concorrem, a Ouvidoria leva,
 * porque o Admin continua alcançável pelo menu lateral e a fila da Ouvidoria,
 * no celular, não tinha caminho nenhum.
 *
 * O que só existe aqui dentro é essa disputa de vaga. O `usePathname` e o
 * `useCurrentParticipante` entram dublados: o que se prova é qual item a barra
 * monta para cada perfil, não como o Next resolve a rota nem como o hook busca
 * o participante.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { BottomNav } from "./BottomNav";

const rota = vi.hoisted(() => ({ atual: "/dashboard" }));
const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => rota.atual,
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: sessao.participante,
    loading: false,
    error: null,
  }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function participante(
  overrides: Partial<CurrentParticipante> = {}
): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
    perfil_ouvidoria: null,
    ...overrides,
  };
}

/** Os rótulos dos itens, na ordem em que a barra os monta. */
function rotulos(): string[] {
  const barra = screen.getByRole("navigation", { name: "Navegação principal" });
  return within(barra)
    .getAllByRole("link")
    .map((link) => link.textContent?.trim() ?? "");
}

afterEach(() => {
  cleanup();
  rota.atual = "/dashboard";
  sessao.participante = null;
});

describe("BottomNav por perfil", () => {
  it("quem tem Perfil da Ouvidoria vê o item Ouvidoria", () => {
    sessao.participante = participante({ perfil_ouvidoria: "ouvidor" });

    render(<BottomNav />);

    expect(rotulos()).toContain("Ouvidoria");
  });

  it("Diretoria Executiva também tem o item", () => {
    sessao.participante = participante({
      perfil_ouvidoria: "diretoria_executiva",
    });

    render(<BottomNav />);

    expect(rotulos()).toContain("Ouvidoria");
  });

  it("com acesso a Admin, a Ouvidoria toma a vaga do Admin", () => {
    sessao.participante = participante({
      access_profile: "super_admin",
      perfil_ouvidoria: "ouvidor",
    });

    render(<BottomNav />);

    const itens = rotulos();
    expect(itens).toEqual([
      "Início",
      "Reuniões",
      "Pendências",
      "Perfil",
      "Ouvidoria",
    ]);
    expect(itens).not.toContain("Admin");
  });

  it("quem não tem o perfil vê a barra como hoje: Admin na vaga", () => {
    sessao.participante = participante({ access_profile: "super_admin" });

    render(<BottomNav />);

    const itens = rotulos();
    expect(itens).toEqual([
      "Início",
      "Reuniões",
      "Pendências",
      "Perfil",
      "Admin",
    ]);
    expect(itens).not.toContain("Ouvidoria");
  });

  it("quem não tem o perfil nem Admin vê só os quatro itens de sempre", () => {
    sessao.participante = participante({ access_profile: null });

    render(<BottomNav />);

    expect(rotulos()).toEqual(["Início", "Reuniões", "Pendências", "Perfil"]);
  });

  it("o item leva à fila da Ouvidoria", () => {
    sessao.participante = participante({ perfil_ouvidoria: "ouvidor" });

    render(<BottomNav />);

    expect(
      screen.getByRole("link", { name: "Ouvidoria" }).getAttribute("href")
    ).toBe("/ouvidoria");
  });

  it("estando na Ouvidoria, o item marca o estado ativo", () => {
    sessao.participante = participante({ perfil_ouvidoria: "ouvidor" });
    rota.atual = "/ouvidoria/painel";

    render(<BottomNav />);

    expect(
      screen.getByRole("link", { name: "Ouvidoria" }).getAttribute("aria-current")
    ).toBe("page");
    expect(
      screen.getByRole("link", { name: "Início" }).getAttribute("aria-current")
    ).toBeNull();
  });
});
