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

import {
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { CSS_DO_ORCAMENTO } from "@/lib/ouvidoria/atalhos";
import { Sidebar } from "./Sidebar";

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

const rota = vi.hoisted(() => ({ atual: "/ouvidoria" }));

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

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  sessao.participante = null;
  rota.atual = "/ouvidoria";
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
    expect(distintivo.getAttribute("aria-label")).toBe("5 novidades na Ouvidoria");
  });

  it("o distintivo é a soma dos casos com novidade e dos e-mails da triagem (issue #652)", () => {
    // O servidor soma: dois e-mails esperando decisão e um caso com novidade.
    sessao.participante = daOuvidoria();

    render(<Sidebar novidadesOuvidoria={{ estado: "ok", total: 3 }} />);

    const distintivo = within(itemDaOuvidoria()).getByRole("status");
    expect(distintivo.textContent).toBe("3");
    // O rótulo não diz "casos": parte da soma é e-mail, e não caso.
    expect(distintivo.getAttribute("aria-label")).toBe("3 novidades na Ouvidoria");
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

/**
 * O item Manual (issue #1718, ADR 0094, decisão 1). Ele mora no rodapé da
 * barra, acima do botão de recolher, e não na lista de links do menu: por isso
 * cada caso confere as duas coisas. A lista inteira de links prova que o menu
 * de cada variante continua o mesmo (e que nenhum link para o site antigo do
 * manual voltou), e o rodapé prova que o Manual está lá, levando a /manual.
 */
describe.each([
  ["computador", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Sidebar com o item Manual no %s", (_rotulo, variant) => {
  it.each([
    [
      "padrão",
      { access_profile: "regular", perfil_ouvidoria: "ouvidor" },
      ["Dashboard", "Calendário", "Ouvidoria", "Admin"],
    ],
    [
      "Secretária",
      { access_profile: "secretaria" },
      ["Início", "Nova reunião", "Calendário", "Ouvidoria", "Admin"],
    ],
    [
      "só POPs",
      { access_profile: null, perfil_pop: "leitor" },
      ["POPs"],
    ],
  ] as const)(
    "no menu %s o Manual fica no rodapé, e o resto do menu é o da variante",
    (_nome, papeis, linksEsperados) => {
      sessao.participante = {
        id: "p1",
        nome_completo: "Fulana de Tal",
        email: "fulana@hsm",
        ...papeis,
      } as CurrentParticipante;

      const { container } = render(<Sidebar variant={variant} />);

      const menu = screen.getByRole("navigation");
      expect(
        within(menu)
          .getAllByRole("link")
          .map((link) => link.textContent?.trim())
      ).toEqual([...linksEsperados]);

      const manual = screen.getByRole("link", { name: "Manual" });
      expect(manual.getAttribute("href")).toBe("/manual");
      expect(menu.contains(manual)).toBe(false);
      expect(container.querySelector("[data-rodape-do-menu]")?.contains(manual)).toBe(true);
    }
  );
});

it("no computador, o Manual fica logo acima do botão de recolher", () => {
  sessao.participante = {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
  };

  render(<Sidebar />);

  const manual = screen.getByRole("link", { name: "Manual" });
  const recolher = screen.getByRole("button", { name: "Recolher menu" });
  expect(manual.nextElementSibling).toBe(recolher);
});

/**
 * O item Contas médicas (issue #1114, PRD #1113, ADR 0070).
 *
 * O módulo tem eixo próprio (`perfil_contas_medicas`), e o item só aparece
 * para quem tem um perfil nele ou é super admin do app, que passa em todos os
 * módulos. A pergunta parte da lista de links do menu, e não de um texto solto
 * na tela.
 */
describe("Sidebar com o item Contas médicas", () => {
  function linkDeContasMedicas(): HTMLElement | undefined {
    const menu = screen.getByRole("navigation");
    return within(menu)
      .queryAllByRole("link")
      .find((link) => link.textContent?.trim() === "Contas médicas");
  }

  it.each([
    ["faturista", { access_profile: null, perfil_contas_medicas: "faturista" }],
    [
      "coordenadora com papel nas Reuniões",
      { access_profile: "regular", perfil_contas_medicas: "coordenadora" },
    ],
    [
      "credenciamento que também é dos POPs",
      { access_profile: null, perfil_pop: "leitor", perfil_contas_medicas: "credenciamento" },
    ],
    ["super admin sem perfil no módulo", { access_profile: "super_admin" }],
  ] as const)("aparece para %s, levando a /contas-medicas", (_nome, papeis) => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      ...papeis,
    } as CurrentParticipante;

    render(<Sidebar />);

    expect(linkDeContasMedicas()?.getAttribute("href")).toBe("/contas-medicas");
  });

  it.each([
    ["quem só tem papel nas Reuniões", { access_profile: "regular" }],
    ["a Ouvidoria", { access_profile: "regular", perfil_ouvidoria: "ouvidor" }],
    ["quem só é dos POPs", { access_profile: null, perfil_pop: "leitor" }],
  ] as const)("não aparece para %s", (_nome, papeis) => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      ...papeis,
    } as CurrentParticipante;

    render(<Sidebar />);

    // Controle positivo: o menu montou, e o item é que não está nele.
    const menu = screen.getByRole("navigation");
    expect(within(menu).getAllByRole("link").length).toBeGreaterThan(0);
    expect(linkDeContasMedicas()).toBeUndefined();
  });
});
