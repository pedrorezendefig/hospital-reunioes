/**
 * @vitest-environment jsdom
 */

/**
 * O item Tecnologia no menu da área admin (issue #636, PRD #634, ADR 0050).
 *
 * Só Super admin enxerga a aba. O gate de verdade é o `require_super_admin` do
 * backend, e o teste dele mora em `test_admin_tecnologia.py`; aqui se prova a
 * outra metade: quem não é Super admin não recebe o caminho.
 *
 * O menu do celular é o MESMO componente na variante `drawer` (é o que a
 * `AppShell` monta dentro da gaveta), então as duas superfícies entram no teste
 * pelo mesmo caminho, uma de cada vez.
 *
 * Teste de ausência sem irmão de presença é vazio: um menu que não renderizasse
 * nada passaria em "não vê Tecnologia". Por isso todo caso que afirma ausência
 * confere, no mesmo render, um item que a persona VÊ.
 */

import {
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AdminSidebar } from "./AdminSidebar";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

// A tela aberta. O padrão é a de Usuários; o teste da marcação do item ativo
// abre uma tela da Central.
const rota = vi.hoisted(() => ({ atual: "/admin/usuarios" }));

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

function pessoa(access_profile: "super_admin" | "secretaria" | "regular"): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile,
  };
}

afterEach(() => {
  cleanup();
  sessao.participante = null;
  rota.atual = "/admin/usuarios";
  vi.unstubAllEnvs();
});

/** Os links do menu, na ordem em que aparecem. */
function linksDoMenu(): (string | undefined)[] {
  const menu = screen.getByRole("navigation");
  return within(menu)
    .getAllByRole("link")
    .map((link) => link.textContent?.trim());
}

/**
 * A seção Central de Comando (issue #814, PRD #809, ADR 0058).
 *
 * Só Super admin vê, entre Atendimento e Tecnologia, com os quatro itens que
 * funcionam. O gate de verdade é o `require_super_admin` do router da Central
 * (`test_central_de_comando_visao_geral.py`) e o guard do `layout.tsx` da
 * seção; aqui se prova a metade do menu.
 *
 * A seção nasceu dormente, só fora de produção, e a issue #827 a ligou: o
 * menu não olha mais o ambiente. Quem decide é o perfil, e só ele.
 */
describe.each([
  ["desktop", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Seção Central de Comando na %s", (_rotulo, variant) => {
  it("Super admin vê a seção com os quatro itens, cada um na sua tela", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getByText("Central de Comando")).toBeTruthy();
    const destinos = ["Visão Geral", "Objetivos", "Dados do Google", "Instagram"].map(
      (nome) => within(menu).getByRole("link", { name: nome }).getAttribute("href"),
    );
    expect(destinos).toEqual([
      "/admin/central-de-comando/visao-geral",
      "/admin/central-de-comando/objetivos",
      "/admin/central-de-comando/dados-do-google",
      "/admin/central-de-comando/instagram",
    ]);
  });

  it("a seção fica entre Atendimento e Tecnologia", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const links = linksDoMenu();
    const atendimento = links.indexOf("Dados do Atendimento");
    const tecnologia = links.indexOf("Tecnologia");
    expect(links.slice(atendimento + 1, tecnologia)).toEqual([
      "Visão Geral",
      "Objetivos",
      "Dados do Google",
      "Instagram",
    ]);
  });

  it("secretária não vê a seção, e continua vendo o que é dela", () => {
    sessao.participante = pessoa("secretaria");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getByRole("link", { name: "Dados do Atendimento" })).toBeTruthy();
    expect(within(menu).queryByText("Central de Comando")).toBeNull();
    expect(within(menu).queryByRole("link", { name: "Visão Geral" })).toBeNull();
  });

  it("facilitador não vê a seção, e continua vendo o que é dele", () => {
    sessao.participante = pessoa("regular");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getByRole("link", { name: "Dados do Atendimento" })).toBeTruthy();
    expect(within(menu).queryByText("Central de Comando")).toBeNull();
    expect(within(menu).queryByRole("link", { name: "Instagram" })).toBeNull();
  });

  // A Central foi ligada em produção (ADR 0058, decisão 8): o ambiente da
  // build não entra mais na conta. O caso de produção é o que importa, e os
  // outros valores ficam para provar que nenhum deles esconde a seção, nem a
  // variável ausente, que antes valia produção.
  it.each(["production", "", "prod", "development"])(
    "com NEXT_PUBLIC_ENVIRONMENT=%j o Super admin vê a seção",
    (valor) => {
      vi.stubEnv("NEXT_PUBLIC_ENVIRONMENT", valor);
      sessao.participante = pessoa("super_admin");

      render(<AdminSidebar variant={variant} />);

      const menu = screen.getByRole("navigation");
      expect(within(menu).getByText("Central de Comando")).toBeTruthy();
      expect(within(menu).getByRole("link", { name: "Visão Geral" })).toBeTruthy();
    },
  );

  it.each([
    ["secretária", "secretaria" as const],
    ["facilitador", "regular" as const],
  ])("em produção a %s não vê a seção, e continua vendo o que é dela", (_quem, perfil) => {
    vi.stubEnv("NEXT_PUBLIC_ENVIRONMENT", "production");
    sessao.participante = pessoa(perfil);

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getByRole("link", { name: "Dados do Atendimento" })).toBeTruthy();
    expect(within(menu).queryByText("Central de Comando")).toBeNull();
  });

  it("o item da tela aberta fica marcado, e só ele", () => {
    rota.atual = "/admin/central-de-comando/dados-do-google";
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    const marcados = within(menu)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page")
      .map((link) => link.textContent?.trim());
    expect(marcados).toEqual(["Dados do Google"]);
  });
});

describe.each([
  ["desktop", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Item Tecnologia na %s", (_rotulo, variant) => {
  it("Super admin chega na aba pelo menu", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu).getByRole("link", { name: "Tecnologia" }).getAttribute("href"),
    ).toBe("/admin/tecnologia");
  });

  it("secretária não vê Tecnologia, e continua vendo o que é dela", () => {
    sessao.participante = pessoa("secretaria");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu).getByRole("link", { name: "Dados do Atendimento" }),
    ).toBeTruthy();
    expect(within(menu).queryByRole("link", { name: "Tecnologia" })).toBeNull();
  });

  it("facilitador não vê Tecnologia, e continua vendo o que é dele", () => {
    sessao.participante = pessoa("regular");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu).getByRole("link", { name: "Dados do Atendimento" }),
    ).toBeTruthy();
    expect(within(menu).queryByRole("link", { name: "Tecnologia" })).toBeNull();
  });
});

describe.each([
  ["desktop", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Sem seção Ferramentas na %s (issue #671)", (_rotulo, variant) => {
  it("nem o Super admin vê Utilitários, e continua vendo Tecnologia", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getByRole("link", { name: "Tecnologia" })).toBeTruthy();
    expect(within(menu).queryByRole("link", { name: "Utilitários" })).toBeNull();
    expect(within(menu).queryByText("Ferramentas")).toBeNull();
  });
});

/**
 * O menu do Admin sem o item Ajuda: o Manual do usuário saiu da plataforma em
 * 05/11/2026. A lista inteira de links prova que nenhum link para o site
 * apagado sobrou no fim, nas duas montagens do menu.
 */
describe.each([
  ["desktop", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Menu do Admin sem a Ajuda na %s", (_rotulo, variant) => {
  it("quem não é super admin vê só o próprio módulo", () => {
    sessao.participante = pessoa("secretaria");

    render(<AdminSidebar variant={variant} />);

    expect(linksDoMenu()).toEqual(["Dados do Atendimento"]);
  });

  it("no menu do super admin a Tecnologia é o último item", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    expect(linksDoMenu()).toEqual([
      "Usuários",
      "Setores",
      "Cargos",
      "Tipos de Reunião",
      "Dados do Atendimento",
      "Visão Geral",
      "Objetivos",
      "Dados do Google",
      "Instagram",
      "Tecnologia",
    ]);
  });
});
