/**
 * @vitest-environment jsdom
 */

/**
 * Quem responde a você (issue #1943, PRD #1932, ADR 0104 decisão 9).
 *
 * Quem aparece, a ordem e o último acesso vêm prontos do servidor, que tem os
 * testes da regra em `backend/tests/test_inicio_quem_responde.py`. Aqui se
 * trava o que a pessoa vê: a linha com nome, cargo e números, o detalhe que
 * abre no clique e no Enter, o bloco que some para quem não acompanha
 * ninguém, a falha que fica no bloco e a rolagem no celular.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InicioPage from "@/app/inicio/page";

import type { InicioDaPessoa } from "./MinhaFila";
import { QuemRespondeAVoce, type QuemResponde } from "./QuemRespondeAVoce";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const EQUIPE: QuemResponde = {
  pessoas: [
    {
      id: "P_BRUNO",
      nome: "Bruno Reis",
      cargo: "Farmacêutico",
      vencidos: 2,
      em_aberto: 3,
      ultimo_acesso: "há 4 dias",
      entregas_90_dias: { no_prazo: 5, fora_do_prazo: 3 },
      itens_vencidos: [
        {
          id: "B2",
          titulo: "Revisar o estoque",
          origem: "Reunião de Farmácia, de 28/10/2026.",
          prazo: "2026-11-06",
          dias_de_atraso: 12,
        },
        {
          id: "B1",
          titulo: "Trocar o filtro",
          origem: "Reunião de Farmácia, de 28/10/2026.",
          prazo: "2026-11-17",
          dias_de_atraso: 1,
        },
      ],
    },
    {
      id: "P_ANA",
      nome: "Ana Souza",
      cargo: "Enfermeira",
      vencidos: 0,
      em_aberto: 1,
      ultimo_acesso: "nunca entrou",
      entregas_90_dias: { no_prazo: 1, fora_do_prazo: 0 },
      itens_vencidos: [],
    },
  ],
};

const INICIO: InicioDaPessoa = {
  hoje: "2026-11-18",
  frase: { titulo: "Sara, você está em dia.", apoio: "Nenhum prazo aberto no seu nome." },
  contadores: { passou_do_prazo: 0, ate_48_horas: 0, proximos_7_dias: 0 },
  itens: [],
  avisos: [],
  trilho: [],
  filas_do_papel: [],
};

type Resposta = { status: number; corpo: unknown };

function servidor(rotas: Record<string, Resposta>) {
  const chamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      chamadas.push(url);
      const { status, corpo } = rotas[url] ?? { status: 404, corpo: null };
      return { ok: status < 300, status, json: async () => corpo } as Response;
    })
  );
  return chamadas;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrir(corpo: QuemResponde = EQUIPE) {
  const chamadas = servidor({ "/api/inicio/quem-responde": { status: 200, corpo } });
  render(<QuemRespondeAVoce />);
  const bloco = await screen.findByRole("region", { name: "Quem responde a você" });
  return { bloco, chamadas };
}

function linhaDe(nome: string): HTMLElement {
  return screen.getByText(nome).closest("tr") as HTMLElement;
}

describe("a linha de cada pessoa", () => {
  it("traz nome, cargo, vencidos agora, em aberto, entregas de 90 dias e último acesso, na ordem do servidor", async () => {
    const { bloco, chamadas } = await abrir();

    expect(chamadas).toEqual(["/api/inicio/quem-responde"]);
    expect(within(bloco).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Pessoa",
      "Vencidos agora",
      "Em aberto",
      "Entregas em 90 dias",
      "Último acesso",
    ]);
    const linhas = within(bloco).getAllByRole("row").slice(1);
    expect(linhas.map((tr) => Array.from(tr.querySelectorAll("td")).map((td) => td.textContent))).toEqual([
      ["Bruno ReisFarmacêutico", "2", "3", "5 no prazo, 3 fora", "há 4 dias"],
      ["Ana SouzaEnfermeira", "0", "1", "1 no prazo, 0 fora", "nunca entrou"],
    ]);
  });

  it("clicar na linha abre ali mesmo o que venceu, com há quantos dias, e clicar de novo fecha", async () => {
    await abrir();
    const linha = linhaDe("Bruno Reis");
    expect(linha.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(linha);

    expect(linha.getAttribute("aria-expanded")).toBe("true");
    const vencidos = screen.getByRole("list", { name: "O que venceu e não foi entregue por Bruno Reis" });
    expect(within(vencidos).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Revisar o estoqueReunião de Farmácia, de 28/10/2026.há 12 dias",
      "Trocar o filtroReunião de Farmácia, de 28/10/2026.há 1 dia",
    ]);
    // Só leitura: nada para clicar dentro do detalhe.
    expect(within(vencidos).queryAllByRole("link")).toEqual([]);
    expect(within(vencidos).queryAllByRole("button")).toEqual([]);

    fireEvent.click(linha);
    expect(screen.queryByRole("list", { name: /O que venceu/ })).toBeNull();
  });

  it("apertar Enter na linha, chegando pelo teclado, também abre", async () => {
    await abrir();
    const linha = linhaDe("Ana Souza");
    expect(linha.tabIndex).toBe(0);

    fireEvent.keyDown(linha, { key: "Enter" });

    expect(linha.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Nada vencido e não entregue.")).toBeTruthy();
  });
});

describe("o bloco", () => {
  it("não aparece para quem não acompanha ninguém", async () => {
    const chamadas = servidor({ "/api/inicio/quem-responde": { status: 200, corpo: null } });
    const { container } = render(<QuemRespondeAVoce />);

    await vi.waitFor(() => expect(chamadas).toEqual(["/api/inicio/quem-responde"]));
    await Promise.resolve();
    expect(container.innerHTML).toBe("");
  });

  it("no celular a tabela rola dentro do próprio bloco", async () => {
    const { bloco } = await abrir();

    const tabela = within(bloco).getByRole("table");
    const rolagem = tabela.parentElement as HTMLElement;
    expect(rolagem.className.split(/\s+/)).toContain("overflow-x-auto");
    expect(bloco.contains(rolagem)).toBe(true);
    expect(tabela.className).toMatch(/min-w-\[\d+px\]/);
  });

  it("a falha do bloco fica no bloco e o resto do Início continua", async () => {
    servidor({
      "/api/inicio": { status: 200, corpo: INICIO },
      "/api/inicio/quem-responde": { status: 500, corpo: null },
    });
    render(<InicioPage />);

    expect(await screen.findByText("Sara, você está em dia.")).toBeTruthy();
    const bloco = await screen.findByRole("region", { name: "Quem responde a você" });
    expect(within(bloco).getByRole("status").textContent).toBe(
      "Não foi possível carregar quem responde a você agora. Tente de novo em instantes."
    );
    expect(screen.queryByText("Não foi possível abrir o seu Início agora. Tente de novo em instantes.")).toBeNull();
  });
});
