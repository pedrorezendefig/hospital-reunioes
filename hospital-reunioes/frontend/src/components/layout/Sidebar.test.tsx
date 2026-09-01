/**
 * @vitest-environment jsdom
 */

/**
 * O menu lateral, que no celular é o conteúdo da gaveta (issue #478, PRD #468).
 *
 * Este arquivo existe por causa de uma consequência: a barra inferior passou a
 * ceder a vaga do Admin para a Ouvidoria quando a pessoa tem os dois acessos.
 * Isso só é aceitável enquanto o Admin continuar alcançável pelo menu, que é a
 * outra superfície de navegação do celular. Sem este teste, tirar o Admin do
 * menu deixaria a suíte verde e o super admin sem caminho nenhum no celular.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { Sidebar } from "./Sidebar";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/ouvidoria",
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

afterEach(() => {
  cleanup();
  sessao.participante = null;
});

describe("Sidebar na gaveta do celular", () => {
  it("quem tem Ouvidoria e Admin continua com o Admin no menu", () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      access_profile: "super_admin",
      perfil_ouvidoria: "ouvidor",
    };

    render(<Sidebar variant="drawer" />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu).getByRole("link", { name: "Admin" }).getAttribute("href")
    ).toBe("/admin");
  });
});
