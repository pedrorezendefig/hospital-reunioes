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
  fireEvent,
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { CSS_DO_ORCAMENTO } from "@/lib/ouvidoria/atalhos";
import { Sidebar, itensDoMenu, type NavItem } from "./Sidebar";

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
 * O item Admin é só do Super admin (issue #1907, ADR 0101). O relato do
 * diretor: um médico sem super admin clicou em Admin e caiu em Dados do
 * Atendimento. Sem o item, não há caminho pelo menu.
 */
describe.each([
  ["computador", "desktop" as const],
  ["gaveta do celular", "drawer" as const],
])("Sidebar com o item Admin no %s", (_rotulo, variant) => {
  it.each([
    ["o facilitador", "regular" as const],
    ["a secretária", "secretaria" as const],
  ])("%s não vê o item Admin", (_quem, access_profile) => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      access_profile,
    };

    render(<Sidebar variant={variant} />);

    const menu = screen.getByRole("navigation");
    expect(within(menu).queryByRole("link", { name: "Admin" })).toBeNull();
  });

  it("o super admin vê o item Admin", () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      access_profile: "super_admin",
    };

    render(<Sidebar variant={variant} />);

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
      ["Início", "Dashboard", "Calendário", "Definições de processo", "Rotinas", "Ouvidoria"],
    ],
    [
      "Secretária",
      { access_profile: "secretaria" },
      ["Início", "Nova reunião", "Calendário", "Ouvidoria"],
    ],
    [
      "só POPs",
      { access_profile: null, perfil_pop: "leitor" },
      ["Início", "POPs"],
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

/**
 * O item Segurança do Paciente (issue #1765, PRD #1764, ADR 0095).
 *
 * Quem decide é o servidor: `/participantes/me` devolve `recursos_nsp`, e o
 * item aparece só com `ver_modulo` (Participação vigente no Núcleo, Acesso
 * pleno ou Diretoria). O super admin recebe só `configuracao` e não vê o item.
 */
describe("Sidebar com o item Segurança do Paciente", () => {
  const SEM_TERMO = ["agenda", "calendario", "painel", "ver_modulo"];

  function entrar(papeis: Partial<CurrentParticipante>) {
    sessao.participante = {
      id: "p1",
      nome_completo: "Pessoa de Teste",
      email: "pessoa@hsm",
      ...papeis,
    } as CurrentParticipante;
    rota.atual = "/seguranca-do-paciente";
    render(<Sidebar />);
    return screen.getByRole("navigation");
  }

  function hrefs(menu: HTMLElement): string[] {
    return within(menu)
      .queryAllByRole("link")
      .map((link) => link.getAttribute("href") ?? "");
  }

  it.each([
    ["membro do Núcleo sem papel nas Reuniões", { access_profile: null, recursos_nsp: SEM_TERMO }],
    ["diretor com papel nas Reuniões", { access_profile: "regular", recursos_nsp: SEM_TERMO }],
  ] as const)("aparece para %s, com as cinco telas da primeira fase", (_nome, papeis) => {
    const menu = entrar(papeis as Partial<CurrentParticipante>);

    expect(within(menu).getByRole("button", { name: "Segurança do Paciente" })).toBeTruthy();
    expect(hrefs(menu)).toEqual(
      expect.arrayContaining([
        "/seguranca-do-paciente",
        "/seguranca-do-paciente/reunioes",
        "/seguranca-do-paciente/membros",
        "/seguranca-do-paciente/documentos",
        "/seguranca-do-paciente/capacitacoes",
        "/seguranca-do-paciente/agenda",
      ])
    );
  });

  it("chama a página do módulo de Visão geral, para não haver dois Início (issue #1942)", () => {
    const menu = entrar({ access_profile: "regular", recursos_nsp: SEM_TERMO } as Partial<CurrentParticipante>);

    const visaoGeral = within(menu)
      .getAllByRole("link")
      .find((link) => link.getAttribute("href") === "/seguranca-do-paciente");
    expect(visaoGeral?.textContent?.trim()).toBe("Visão geral");
    const inicios = within(menu)
      .getAllByRole("link")
      .filter((link) => link.textContent?.trim() === "Início");
    expect(inicios.map((link) => link.getAttribute("href"))).toEqual(["/inicio"]);
  });

  it.each([
    ["super admin sem Acesso pleno", { access_profile: "super_admin", recursos_nsp: ["configuracao"] }],
    ["quem só tem papel nas Reuniões", { access_profile: "regular", recursos_nsp: [] }],
    ["quem ainda não tem a lista do servidor", { access_profile: "regular" }],
    ["quem não tem papel em módulo nenhum", { access_profile: null, recursos_nsp: [] }],
  ] as const)("para %s, o grupo aparece só com o botão Notificar incidente (issue #1987)", (_nome, papeis) => {
    const menu = entrar(papeis as Partial<CurrentParticipante>);

    expect(within(menu).getByRole("button", { name: "Segurança do Paciente" })).toBeTruthy();
    const doModulo = within(menu)
      .getAllByRole("link")
      .filter((link) => /^\/(seguranca-do-paciente|notificar)/.test(link.getAttribute("href") ?? ""));
    expect(doModulo.map((link) => [link.textContent?.trim(), link.getAttribute("href")])).toEqual([
      ["Notificar incidente", "/notificar/modulo"],
    ]);
    // Nem os itens Em breve: eles são do módulo, que a pessoa não abre.
    expect(within(menu).queryByRole("button", { name: /^Comissões/ })).toBeNull();
  });

  it("o botão mora só no menu: nem o topo nem a barra inferior têm atalho (Ajuste do plano #2045)", () => {
    for (const arquivo of ["Header.tsx", "BottomNav.tsx", "AppShell.tsx", "MobileDrawer.tsx"]) {
      const fonte = readFileSync(join(__dirname, arquivo), "utf-8");
      expect(fonte.length, arquivo).toBeGreaterThan(0);
      expect(fonte, arquivo).not.toMatch(/notificar|Notificar incidente/);
    }
  });

  it("quem abre o módulo também tem o botão Notificar incidente, primeiro no grupo", () => {
    const menu = entrar({ access_profile: null, recursos_nsp: SEM_TERMO });

    const doModulo = hrefs(menu).filter((href) => /^\/(seguranca-do-paciente|notificar)/.test(href));
    expect(doModulo[0]).toBe("/notificar/modulo");
  });

  it("o item Notificações aparece para quem tem o recurso de casos, e só para ele", () => {
    const comCasos = entrar({ access_profile: null, recursos_nsp: [...SEM_TERMO, "casos"] });
    expect(hrefs(comCasos)).toContain("/seguranca-do-paciente/notificacoes");
    cleanup();

    const semCasos = entrar({ access_profile: null, recursos_nsp: SEM_TERMO });
    expect(hrefs(semCasos)).toContain("/seguranca-do-paciente/membros");
    expect(hrefs(semCasos)).not.toContain("/seguranca-do-paciente/notificacoes");
  });

  it.each([
    [
      "Auditorias de adesão",
      "Em breve: auditorias rápidas pelo celular. Um membro da equipe observa uma amostra de pacientes ou de procedimentos (pulseira de identificação, lista de verificação cirúrgica, higiene das mãos, risco de queda) e marca o que encontrou. Os resultados alimentam os indicadores dos protocolos sem digitação.",
    ],
    [
      "Gestão de riscos",
      "Em breve: mapa de riscos por setor e análise preventiva de processos críticos, antes que o incidente aconteça.",
    ],
    [
      "Comissões",
      "Em breve: as demais comissões do hospital (prontuário, óbito, ética) com a mesma estrutura de membros, documentos, reuniões e atas.",
    ],
  ])("%s aparece desabilitado, com o selo Em breve e o texto da especificação", (rotulo, texto) => {
    const menu = entrar({ access_profile: null, recursos_nsp: SEM_TERMO });

    const item = within(menu).getByRole("button", { name: new RegExp(`^${rotulo}`) });
    expect(item.getAttribute("aria-disabled")).toBe("true");
    expect(within(item).getByText("Em breve")).toBeTruthy();
    // Não é link: não leva a lugar nenhum.
    expect(within(menu).queryByRole("link", { name: new RegExp(rotulo) })).toBeNull();

    // O texto fica ligado ao item e aparece no toque (o celular não tem hover).
    const explicacao = document.getElementById(item.getAttribute("aria-describedby") ?? "");
    expect(explicacao?.textContent).toBe(texto);
    expect(explicacao?.hidden).toBe(true);
    fireEvent.click(item);
    expect(explicacao?.hidden).toBe(false);
    expect(item.getAttribute("aria-expanded")).toBe("true");
  });

  it("recolhido, o menu não mostra os itens Em breve como ícone navegável", () => {
    localStorage.setItem("menu-recolhido", "1");
    try {
      const menu = entrar({ access_profile: null, recursos_nsp: SEM_TERMO });
      // Controle positivo: recolhido de fato, com os ícones do módulo.
      expect(hrefs(menu)).toContain("/seguranca-do-paciente/membros");
      expect(within(menu).queryByRole("button", { name: "Segurança do Paciente" })).toBeNull();
      expect(hrefs(menu).filter((href) => href === "" || href === "#")).toEqual([]);
      expect(within(menu).queryByRole("link", { name: /Comissões/ })).toBeNull();
    } finally {
      localStorage.removeItem("menu-recolhido");
    }
  });
});

/**
 * O item Ouvidoria pelo papel na Ouvidoria (issue #1884, ADR 0099): o
 * responsável do setor vê o item, e quem não tem papel nenhum deixa de ver.
 */
describe("Sidebar com o item Ouvidoria pelo papel", () => {
  function links(): string[] {
    return within(screen.getByRole("navigation"))
      .getAllByRole("link")
      .map((link) => link.textContent?.trim() ?? "");
  }

  it("o médico sem papel na Ouvidoria não vê o item", () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Dra. Clara",
      email: "clara@hsm",
      access_profile: "regular",
      papel_ouvidoria: "nenhum",
    };

    render(<Sidebar />);

    expect(links()).not.toContain("Ouvidoria");
  });

  it("o responsável do setor vê o item", () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Dr. Bruno",
      email: "bruno@hsm",
      access_profile: "regular",
      papel_ouvidoria: "responsavel",
    };

    render(<Sidebar />);

    expect(links()).toContain("Ouvidoria");
  });

  it("o responsável que só tem POPs também vê o item", () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Enf. Dora",
      email: "dora@hsm",
      access_profile: null,
      perfil_pop: "coordenador",
      papel_ouvidoria: "responsavel",
    };

    render(<Sidebar />);

    // O Início vem primeiro para todos menos a Secretária (issue #1934).
    expect(links()).toEqual(["Início", "POPs", "Ouvidoria"]);
  });
});

/**
 * O Início é o primeiro item do menu de quem não é Secretária (issue #1934,
 * ADR 0104, decisão 1). A Secretária continua com o Início dela, a tela da
 * secretaria, e não ganha o Início novo.
 */
describe("Sidebar com o item Início", () => {
  function primeiroLink(): HTMLElement {
    return within(screen.getByRole("navigation")).getAllByRole("link")[0];
  }

  it.each([
    ["o facilitador", { access_profile: "regular" as const }],
    ["o super admin", { access_profile: "super_admin" as const }],
    ["quem só tem POPs", { access_profile: null, perfil_pop: "coordenador" as const }],
  ])("%s tem o Início como primeiro item", (_quem, perfil) => {
    sessao.participante = { id: "p1", nome_completo: "Fulana", email: "f@hsm", ...perfil };

    render(<Sidebar />);

    expect(primeiroLink().textContent?.trim()).toBe("Início");
    expect(primeiroLink().getAttribute("href")).toBe("/inicio");
  });

  it("a Secretária não ganha o Início novo", () => {
    sessao.participante = { id: "p1", nome_completo: "Selma", email: "s@hsm", access_profile: "secretaria" };

    render(<Sidebar />);

    const hrefs = within(screen.getByRole("navigation"))
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(hrefs).not.toContain("/inicio");
    expect(hrefs[0]).toBe("/secretaria");
  });

  it.each([
    ["o facilitador", { access_profile: "regular" as const }],
    ["quem só tem POPs", { access_profile: null, perfil_pop: "coordenador" as const }],
  ])("o logo leva %s ao Início (issue #1942)", (_quem, perfil) => {
    sessao.participante = { id: "p1", nome_completo: "Fulana", email: "f@hsm", ...perfil };

    render(<Sidebar />);

    const logo = screen.getAllByRole("link").find((link) => !link.closest("nav"));
    expect(logo?.getAttribute("href")).toBe("/inicio");
  });

  it("o logo leva a Secretária à tela dela", () => {
    sessao.participante = { id: "p1", nome_completo: "Selma", email: "s@hsm", access_profile: "secretaria" };

    render(<Sidebar />);

    const logo = screen.getAllByRole("link").find((link) => !link.closest("nav"));
    expect(logo?.getAttribute("href")).toBe("/secretaria");
  });
});

describe("Comitê de Conduta no menu (issue #1822)", () => {
  const folhas = (item: NavItem): string[] =>
    item.subItems?.length ? item.subItems.flatMap(folhas) : [item.href];
  const links = (papeis: Partial<CurrentParticipante>) =>
    itensDoMenu({ id: "p1", nome_completo: "Pessoa de Teste", email: "p@hsm", ...papeis } as CurrentParticipante).flatMap(
      folhas
    );

  it.each([
    ["membro do Comitê sem papel nas Reuniões", { access_profile: null, ve_membros_do_comite: true }],
    ["quem tem o perfil de cadastro", { access_profile: "regular", ve_membros_do_comite: true }],
  ] as const)("a tela Membros aparece para %s", (_nome, papeis) => {
    expect(links(papeis as Partial<CurrentParticipante>)).toContain("/comite-de-conduta/membros");
  });

  it("o super admin sem o perfil nem participação não vê a tela", () => {
    expect(
      links({ access_profile: "super_admin", is_super_admin: true, ve_membros_do_comite: false })
    ).not.toContain("/comite-de-conduta/membros");
  });
});
