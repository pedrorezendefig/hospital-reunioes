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

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AdminSidebar } from "./AdminSidebar";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/usuarios",
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
 * O item Ajuda no menu do Admin (ADR 0057, decisão 11).
 *
 * A `AppShell` troca a `Sidebar` por esta quando a pessoa entra no /admin, e
 * até aqui só a `Sidebar` tinha o item Ajuda: a seção Admin do manual estava
 * publicada e ninguém chegava nela pela barra. O teste ancora no href inteiro
 * de propósito. Conferir só o fim ("termina em /admin/") deixaria passar uma
 * base errada, e conferir só a base deixaria passar a seção errada.
 *
 * O `rel` vai inteiro na asserção, não por `toContain`. O `noreferrer` não é
 * enfeite do `noopener`: este menu também é renderizado em rotas que carregam
 * identificador na URL (/admin/usuarios/[id]), e sem ele o clique na Ajuda
 * entrega o endereço atual a um domínio externo pelo cabeçalho Referer.
 */
describe.each([
  ["desktop", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Item Ajuda na %s", (_rotulo, variant) => {
  function ajudaDoMenu(): HTMLElement {
    const menu = screen.getByRole("navigation");
    return within(menu).getByRole("link", { name: "Ajuda" });
  }

  it("a Ajuda abre a seção Admin do manual", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    expect(ajudaDoMenu().getAttribute("href")).toBe(
      "https://manual-hsm.vercel.app/admin/",
    );
  });

  it("a Ajuda abre em outra aba, sem passar a aba de origem nem o endereço atual", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const ajuda = ajudaDoMenu();
    expect(ajuda.getAttribute("target")).toBe("_blank");
    expect(ajuda.getAttribute("rel")).toBe("noopener noreferrer");
  });

  // Confere a lista inteira de links do menu, e não só a presença da Ajuda,
  // porque é a lista que prova que a montagem esperada foi a que rodou: um
  // participante mal montado cairia noutro recorte de seções e o teste
  // continuaria verde procurando só pela Ajuda. Também é o que prende a Ajuda
  // no fim da `<nav>`, depois de todas as seções.
  it("quem não é super admin também tem a Ajuda, no fim do menu dele", () => {
    sessao.participante = pessoa("secretaria");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu)
        .getAllByRole("link")
        .map((link) => link.textContent?.trim()),
    ).toEqual(["Dados do Atendimento", "Ajuda"]);
  });

  it("no menu do super admin a Ajuda é o último item", () => {
    sessao.participante = pessoa("super_admin");

    render(<AdminSidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(
      within(menu)
        .getAllByRole("link")
        .map((link) => link.textContent?.trim()),
    ).toEqual([
      "Usuários",
      "Setores",
      "Cargos",
      "Tipos de Reunião",
      "Dados do Atendimento",
      "Tecnologia",
      "Ajuda",
    ]);
  });
});
