/**
 * @vitest-environment jsdom
 */

/**
 * A fiação do contador de novidades na casca do app (issue #487, PRD #470).
 *
 * Este arquivo existe por causa de um teste vácuo por AUSÊNCIA, achado na
 * review: as peças do contador tinham teste (a régua, o hook, o distintivo em
 * cada menu), e mesmo assim dava para apagar a chamada do hook e as três
 * passagens de prop daqui que a suíte inteira do frontend continuava verde. O
 * distintivo estaria morto em produção sem um vermelho sequer, porque nenhum
 * teste montava a casca de verdade: o único que a tocava (`app/ouvidoria/
 * layout.test.tsx`) mocka o `AppShell` inteiro.
 *
 * O que se prova aqui é só a ligação: um perfil da Ouvidoria, uma resposta do
 * servidor com um total, e o número aparecendo nas TRÊS superfícies de menu que
 * a casca monta (o menu lateral do desktop, a gaveta do celular e a barra
 * inferior), com UMA ida ao servidor para as três.
 *
 * `Header` e `Footer` entram dublados porque são vizinhos de layout e não fazem
 * parte da fiação: montá-los de verdade traria os `fetch` das notificações para
 * dentro deste teste. O `MobileDrawer` também, e por um motivo que muda o que o
 * teste alcança: fechado ele existe no DOM mas com a gaveta invisível, e o
 * dublê a deixa sempre montada, que é o estado em que o ouvidor a olha.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AppShell } from "./AppShell";
import { esquecerNovidades } from "@/hooks/useNovidadesOuvidoria";

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

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "tok-123" } },
      }),
    },
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

vi.mock("@/components/layout/Header", () => ({
  Header: () => <header />,
}));

vi.mock("@/components/layout/Footer", () => ({
  Footer: () => <footer />,
}));

vi.mock("@/components/layout/MobileDrawer", () => ({
  MobileDrawer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

let buscar: ReturnType<typeof vi.fn>;

function resposta(corpo: unknown) {
  return { ok: true, status: 200, json: async () => corpo } as Response;
}

beforeEach(() => {
  esquecerNovidades();
  buscar = vi.fn(async () => resposta({ total: 7, degradado: [] }));
  vi.stubGlobal("fetch", buscar);
});

afterEach(() => {
  cleanup();
  esquecerNovidades();
  vi.unstubAllGlobals();
  sessao.participante = null;
  rota.atual = "/dashboard";
});

/**
 * Monta a casca fora do `act` e devolve o DOM do PRIMEIRO commit, antes de
 * qualquer passive effect.
 *
 * O `render` do testing-library só devolve a tela depois dos efeitos, e é
 * exatamente entre o commit e o primeiro efeito que o vazamento desta rodada
 * acontecia: o `useState` semeia com o valor guardado no módulo, e a guarda de
 * perfil mora no efeito. Um quadro é pouco tempo, mas é tempo suficiente para
 * pintar o número no DOM e no `aria-label` de quem não podia vê-lo.
 */
function primeiroQuadroDaCasca(): HTMLElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const raiz = createRoot(container);
  // O React marca o ambiente de teste para exigir `act`; aqui a montagem é
  // deliberadamente crua, para o DOM poder ser lido antes dos efeitos.
  const ambiente = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const eraAmbienteDeAct = ambiente.IS_REACT_ACT_ENVIRONMENT;
  ambiente.IS_REACT_ACT_ENVIRONMENT = false;
  try {
    flushSync(() => {
      raiz.render(
        <AppShell userName="Sofia Secretaria">
          <p>conteúdo</p>
        </AppShell>
      );
    });
  } finally {
    ambiente.IS_REACT_ACT_ENVIRONMENT = eraAmbienteDeAct;
  }
  return container;
}

/** Os itens Ouvidoria de todos os menus que a casca montou. */
function itensDaOuvidoria(): HTMLElement[] {
  return screen
    .getAllByRole("navigation")
    .map((menu) =>
      within(menu)
        .getAllByRole("link")
        .find((link) => link.textContent?.includes("Ouvidoria"))
    )
    .filter((item): item is HTMLElement => item !== undefined);
}

function comAppShell() {
  return render(
    <AppShell userName="Marta Ouvidora">
      <p>conteúdo</p>
    </AppShell>
  );
}

describe("AppShell liga o contador de novidades aos menus", () => {
  it("o total do servidor chega às três superfícies de menu", async () => {
    sessao.participante = {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      access_profile: null,
      perfil_ouvidoria: "ouvidor",
    };

    comAppShell();

    await waitFor(() => {
      const itens = itensDaOuvidoria();
      // Menu lateral do desktop, gaveta do celular e barra inferior.
      expect(itens).toHaveLength(3);
      for (const item of itens) {
        expect(within(item).getByRole("status").textContent).toBe("7");
      }
    });
    expect(buscar).toHaveBeenCalledWith(
      "/api/ouvidoria/novidades",
      expect.anything()
    );
    // Uma pergunta ao servidor para os três menus: a casca busca, os menus
    // recebem. Três buscas seriam três vezes o custo pela mesma resposta.
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("a contagem de quem saiu não chega ao primeiro quadro de quem entrou", async () => {
    // A troca de conta na mesma aba: o logout do app é navegação do cliente,
    // então o módulo do contador sobrevive ao próximo login.
    sessao.participante = {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      access_profile: null,
      perfil_ouvidoria: "ouvidor",
    };
    comAppShell();
    await waitFor(() =>
      expect(itensDaOuvidoria()[0].querySelector("[role=status]")?.textContent).toBe("7")
    );
    cleanup();

    sessao.participante = {
      id: "p2",
      nome_completo: "Sofia Secretaria",
      email: "sofia@hsm",
      access_profile: "secretaria",
      perfil_ouvidoria: null,
    };
    const quadro = primeiroQuadroDaCasca();

    expect(quadro.querySelectorAll("[role=status]")).toHaveLength(0);
    expect(quadro.textContent).not.toContain("7 casos com novidade");
  });

  it("sem Perfil da Ouvidoria, nenhum menu ganha distintivo e nada é perguntado", async () => {
    sessao.participante = {
      id: "p2",
      nome_completo: "Sofia Secretaria",
      email: "sofia@hsm",
      access_profile: "secretaria",
      perfil_ouvidoria: null,
    };

    comAppShell();

    await waitFor(() => expect(screen.getAllByRole("navigation").length).toBeGreaterThan(0));
    for (const item of itensDaOuvidoria()) {
      expect(within(item).queryByRole("status")).toBeNull();
    }
    expect(buscar).not.toHaveBeenCalled();
  });
});
