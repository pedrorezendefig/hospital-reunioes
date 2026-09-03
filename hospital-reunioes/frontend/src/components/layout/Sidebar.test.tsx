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
import { CSS_DO_ORCAMENTO } from "@/lib/ouvidoria/atalhos";
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

/**
 * O distintivo de novidades no item Ouvidoria do menu (issue #487, PRD #470,
 * RN-69).
 *
 * A ancoragem é a mesma da barra inferior, e pelo mesmo motivo: um número
 * solto casa com qualquer coisa numa tela cheia, então a pergunta parte sempre
 * do link da Ouvidoria para dentro.
 */
describe("Sidebar com o contador de novidades", () => {
  function itemDaOuvidoria(): HTMLElement {
    const menu = screen.getByRole("navigation");
    return within(menu)
      .getAllByRole("link")
      .find((link) => link.textContent?.includes("Ouvidoria"))!;
  }

  function daOuvidoria(): CurrentParticipante {
    return {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      access_profile: "regular",
      perfil_ouvidoria: "ouvidor",
    };
  }

  it("o item Ouvidoria exibe o total de casos com novidade", () => {
    sessao.participante = daOuvidoria();

    render(<Sidebar novidadesOuvidoria={{ estado: "ok", total: 5 }} />);

    const distintivo = within(itemDaOuvidoria()).getByRole("status");
    expect(distintivo.textContent).toBe("5");
    expect(distintivo.getAttribute("aria-label")).toBe("5 casos com novidade");
  });

  it("sem novidade nenhuma, o item fica sem distintivo", () => {
    sessao.participante = daOuvidoria();

    render(<Sidebar novidadesOuvidoria={{ estado: "ok", total: 0 }} />);

    expect(within(itemDaOuvidoria()).queryByRole("status")).toBeNull();
  });

  it("contagem que não carregou não vira zero: o distintivo fica, sem número", () => {
    sessao.participante = daOuvidoria();

    render(<Sidebar novidadesOuvidoria={{ estado: "indisponivel" }} />);

    const distintivo = within(itemDaOuvidoria()).getByRole("status");
    expect(distintivo.textContent).not.toBe("0");
    expect(distintivo.getAttribute("aria-label")).toContain(
      "Não foi possível contar"
    );
  });

  it("nenhum outro item do menu ganha distintivo", () => {
    sessao.participante = { ...daOuvidoria(), access_profile: "super_admin" };

    render(<Sidebar novidadesOuvidoria={{ estado: "ok", total: 5 }} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).getAllByRole("status")).toHaveLength(1);
  });
});

/**
 * O sidebar entra no orçamento de largura da barra de atalhos da Ouvidoria
 * (issue #489). Ele divide a tela com a área de conteúdo a partir do `md`, e
 * a conta de `lib/ouvidoria/atalhos` desconta a largura dele da linha.
 *
 * A primeira versão daquela conta ignorava que este sidebar existia, e por
 * isso afirmava que cabia uma barra que transbordava 200px. O número lá é
 * derivado da classe declarada aqui embaixo: sem esta amarração, trocar a
 * largura do menu reabriria o buraco sem um vermelho sequer.
 */
describe("a largura do sidebar é a que o orçamento da Ouvidoria supõe", () => {
  it("a aside do computador usa a classe que `lib/ouvidoria/atalhos` desconta", () => {
    // Sem perfil nenhum: a moldura do menu é a mesma para todo mundo, e é dela
    // que o orçamento trata.
    const { container } = render(<Sidebar />);

    const aside = container.querySelector("aside");
    expect(aside).not.toBeNull();
    expect(aside!.className.split(/\s+/)).toContain(CSS_DO_ORCAMENTO.sidebar);
  });
});
