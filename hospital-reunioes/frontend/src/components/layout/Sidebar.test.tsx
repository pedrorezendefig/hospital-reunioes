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
  fireEvent,
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

/**
 * O item Ajuda do menu (issue #734, PRD #731, ADR 0057 decisão 11).
 *
 * O manual é um site à parte, então o endereço não passa pelo roteador do app:
 * quem decide a seção é o prefixo da rota em que a pessoa está. O teste ancora
 * no href inteiro de propósito. Conferir só o fim ("termina em /pops/") deixaria
 * passar uma base errada, e conferir só a base deixaria passar a seção errada.
 */
describe("Sidebar com o item Ajuda", () => {
  function hrefDaAjuda(): string {
    const menu = screen.getByRole("navigation");
    return within(menu)
      .getByRole("link", { name: "Ajuda" })
      .getAttribute("href")!;
  }

  it("na Ouvidoria a Ajuda abre a seção da Ouvidoria", () => {
    rota.atual = "/ouvidoria";

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/ouvidoria/");
  });

  it("o formulário de manifestação também cai na seção da Ouvidoria", () => {
    rota.atual = "/manifestacao";

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/ouvidoria/");
  });

  it("nos POPs a Ajuda abre a seção dos POPs", () => {
    rota.atual = "/pops";

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/pops/");
  });

  it("numa tela interna do Admin a Ajuda abre a seção do Admin", () => {
    rota.atual = "/admin/usuarios";

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/admin/");
  });

  it("fora dos módulos com seção própria a Ajuda cai em Reuniões e metas", () => {
    rota.atual = "/dashboard";

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/reunioes/");
  });

  // O `.env.example` promete que a variável vazia vale o padrão, e uma variável
  // declarada sem valor no Coolify chega como string vazia, não como ausente.
  it("variável do manual declarada vazia continua caindo no endereço de produção", () => {
    vi.stubEnv("NEXT_PUBLIC_MANUAL_URL", "");

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://manual-hsm.vercel.app/ouvidoria/");
  });

  it("variável do manual preenchida troca a base do endereço", () => {
    vi.stubEnv("NEXT_PUBLIC_MANUAL_URL", "https://previa.manual.hsm");

    render(<Sidebar />);

    expect(hrefDaAjuda()).toBe("https://previa.manual.hsm/ouvidoria/");
  });

  // O `rel` vai inteiro na asserção, não por `toContain`. O `noreferrer` não é
  // enfeite do `noopener`: o menu também é renderizado em rotas que carregam
  // identificador na URL (/ouvidoria/m/[protocolo], /pops/[id]/elaboracao,
  // /reunioes/[id], /admin/usuarios/[id]), e sem ele o clique na Ajuda entrega
  // o protocolo da manifestação a um domínio externo pelo cabeçalho Referer.
  it("a Ajuda abre em outra aba, sem passar a aba de origem nem o endereço atual", () => {
    render(<Sidebar />);

    const menu = screen.getByRole("navigation");
    const ajuda = within(menu).getByRole("link", { name: "Ajuda" });
    expect(ajuda.getAttribute("target")).toBe("_blank");
    expect(ajuda.getAttribute("rel")).toBe("noopener noreferrer");
  });

  // O menu tem três montagens diferentes e a Ajuda não pertence a nenhum
  // módulo: ela tem que sobreviver às três. Cada caso confere a lista inteira
  // de links do menu, e não só a presença da Ajuda, porque é a lista que prova
  // que a montagem esperada foi a que rodou: um participante mal montado cairia
  // noutra variante e o teste continuaria verde procurando só pela Ajuda.
  it.each([
    [
      "padrão",
      { access_profile: "regular", perfil_ouvidoria: "ouvidor" },
      ["Dashboard", "Calendário", "Ouvidoria", "Admin", "Ajuda"],
    ],
    [
      "Secretária",
      { access_profile: "secretaria" },
      ["Início", "Nova reunião", "Calendário", "Ouvidoria", "Admin", "Ajuda"],
    ],
    [
      "só POPs",
      { access_profile: null, perfil_pop: "leitor" },
      ["POPs", "Ajuda"],
    ],
  ] as const)(
    "no menu %s a Ajuda é o último item, e o resto do menu é o da variante",
    (_nome, papeis, linksEsperados) => {
      sessao.participante = {
        id: "p1",
        nome_completo: "Fulana de Tal",
        email: "fulana@hsm",
        ...papeis,
      } as CurrentParticipante;

      render(<Sidebar />);

      const menu = screen.getByRole("navigation");
      expect(
        within(menu)
          .getAllByRole("link")
          .map((link) => link.textContent?.trim())
      ).toEqual([...linksEsperados]);
    }
  );

  /**
   * A dívida era herdada: o item Ajuda nasceu na issue #734 com
   * `onClick={onNavigate}` e sem teste nenhum que clicasse nele, então apagar o
   * `onClick` deixava a suíte verde. Só a gaveta recebe a prop da `AppShell`, e
   * é ela que fecha a gaveta depois do clique. Como a Ajuda abre em outra aba,
   * quem não fecha a gaveta deixa a pessoa voltando para o app com o menu por
   * cima da tela.
   */
  it("na gaveta do celular, clicar na Ajuda avisa a casca para fechar", () => {
    const fecharAGaveta = vi.fn();

    render(<Sidebar variant="drawer" onNavigate={fecharAGaveta} />);

    const menu = screen.getByRole("navigation");
    fireEvent.click(within(menu).getByRole("link", { name: "Ajuda" }));

    expect(fecharAGaveta).toHaveBeenCalledTimes(1);
  });
});
