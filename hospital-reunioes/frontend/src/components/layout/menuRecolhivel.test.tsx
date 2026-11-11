/**
 * @vitest-environment jsdom
 */

/**
 * O menu lateral recolhível para só os ícones (issue #1550, PRD #1548).
 *
 * As duas barras do computador (a do app e a da administração) entram pelo
 * mesmo `describe.each`: a preferência é uma só e vale para as duas, então o
 * que uma promete a outra também tem de cumprir.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { Sidebar } from "./Sidebar";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

const rota = vi.hoisted(() => ({ atual: "/" }));

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

const superAdmin: CurrentParticipante = {
  id: "p1",
  nome_completo: "Fulana de Tal",
  email: "fulana@hsm",
  access_profile: "super_admin",
  perfil_ouvidoria: "ouvidor",
};

beforeEach(() => {
  sessao.participante = superAdmin;
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

const barras = [
  {
    nome: "a barra do app",
    rota: "/ouvidoria",
    ativo: "Ouvidoria",
    outro: "Admin",
    desenhar: (variant: "desktop" | "drawer") => <Sidebar variant={variant} />,
  },
  {
    nome: "a barra da administração",
    rota: "/admin/usuarios",
    ativo: "Usuários",
    outro: "Tecnologia",
    desenhar: (variant: "desktop" | "drawer") => (
      <AdminSidebar variant={variant} />
    ),
  },
];

function classesDaBarra(container: HTMLElement): string[] {
  const aside = container.querySelector("aside");
  expect(aside).not.toBeNull();
  return aside!.className.split(/\s+/);
}

describe.each(barras)("$nome recolhível", ({ rota: rotaDaBarra, ativo, outro, desenhar }) => {
  beforeEach(() => {
    rota.atual = rotaDaBarra;
  });

  it("recolhe e expande pelo botão", () => {
    const { container } = render(desenhar("desktop"));
    expect(classesDaBarra(container)).toContain("w-64");

    fireEvent.click(screen.getByRole("button", { name: "Recolher menu" }));
    expect(classesDaBarra(container)).toContain("w-16");
    expect(classesDaBarra(container)).not.toContain("w-64");

    fireEvent.click(screen.getByRole("button", { name: "Expandir menu" }));
    expect(classesDaBarra(container)).toContain("w-64");
  });

  it("recolhida, cada item mostra o nome no hover e o ativo continua marcado", () => {
    render(desenhar("desktop"));
    fireEvent.click(screen.getByRole("button", { name: "Recolher menu" }));

    const links = within(screen.getByRole("navigation")).getAllByRole("link");
    expect(links.length).toBeGreaterThan(1);
    for (const link of links) {
      // O hover é o `title`, e ele diz o mesmo nome que o leitor de tela lê.
      expect(link.getAttribute("title")).toBe(link.textContent);
      expect(link.querySelector("svg")).not.toBeNull();
    }

    const ativoLink = screen.getByRole("link", { name: ativo });
    expect(ativoLink.getAttribute("title")).toBe(ativo);
    expect(ativoLink.getAttribute("aria-current")).toBe("page");
    expect(ativoLink.className.split(/\s+/)).toContain("bg-primary/10");

    const outroLink = screen.getByRole("link", { name: outro });
    expect(outroLink.getAttribute("aria-current")).toBeNull();
    expect(outroLink.className.split(/\s+/)).not.toContain("bg-primary/10");
  });
});
