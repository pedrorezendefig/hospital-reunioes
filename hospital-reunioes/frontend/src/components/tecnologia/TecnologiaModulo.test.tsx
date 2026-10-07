/**
 * @vitest-environment jsdom
 */

/**
 * A tela da aba Tecnologia (issue #636, PRD #634, ADR 0050).
 *
 * A casca: as duas abas, com qual delas a aba abre, e o que é carregado uma vez
 * para as duas. O cadastro de Produtos saiu daqui na issue #1060 e tem teste
 * próprio, em `app/admin/tecnologia/produtos/page.test.tsx`.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TecnologiaModulo } from "./TecnologiaModulo";
import { EU_DESCONHECIDO, EuNaAba } from "./demandas";

// `loading` é parametrizável de propósito, e não cravado em `false`: cravar
// esconde o estado de BOOT do `useAuth` (`{ token: null, loading: true }`, duas
// idas à rede antes do token), que é onde um aviso de sessão apressado vira
// alarme falso em toda abertura da aba.
const sessao = vi.hoisted(() => ({
  token: "token-de-teste" as string | null,
  carregando: false,
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    token: sessao.token,
    userId: sessao.token ? "auth-1" : null,
    userEmail: sessao.token ? "p1@hsm" : null,
    loading: sessao.carregando,
  }),
}));

type Chamada = { url: string; metodo: string; corpo: unknown };

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta", email: "pedro@hsm" },
  { id: "P2", nome_completo: "Sócia Vitta", email: "socia@hsm" },
];

function produto(
  id: string,
  nome: string,
  ordem: number,
  extra: { ativo?: boolean; dono_id?: string | null; dono_nome?: string | null } = {},
) {
  return {
    id,
    nome,
    ordem,
    ativo: extra.ativo ?? true,
    dono_id: extra.dono_id ?? null,
    dono_nome: extra.dono_nome ?? null,
  };
}

let chamadas: Chamada[] = [];

/** Monta a tela com o servidor falso. */
function montar(
  produtos: ReturnType<typeof produto>[],
  opcoes: {
    /** Quem está olhando, do ponto de vista do Vínculo (issue #674). */
    eu?: EuNaAba;
    /** O `GET /eu` responde erro: a aba tem que seguir de pé sem ele. */
    euFalha?: boolean;
  } = {},
) {
  chamadas = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({
        url,
        metodo,
        corpo: init?.body ? JSON.parse(String(init.body)) : null,
      });

      // As duas abas (o Quadro da issue #637 e o Painel da #1059) carregam o
      // que mostram e têm teste só delas: aqui elas ficam vazias.
      if (url.includes("/demandas")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }
      if (url.includes("/painel")) {
        const vazio = {
          numeros: { abertas: 0, com_o_hospital: 0, em_desenvolvimento: 0, entregues_30_dias: 0 },
          com_voce: [],
          entregas: [],
          historico: [],
        };
        return { ok: true, status: 200, json: async () => vazio } as unknown as Response;
      }

      if (url.endsWith("/eu")) {
        if (opcoes.euFalha) {
          return { ok: false, status: 500, json: async () => ({}) } as unknown as Response;
        }
        const eu = opcoes.eu ?? EU_DESCONHECIDO;
        return { ok: true, status: 200, json: async () => eu } as unknown as Response;
      }

      const corpo = url.includes("/pessoas") ? PESSOAS : produtos;
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  render(<TecnologiaModulo />);
}

beforeEach(() => {
  chamadas = [];
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao
  // abrir a lista. É buraco do ambiente, não da tela.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessao.token = "token-de-teste";
  sessao.carregando = false;
  vi.restoreAllMocks();
});

describe("A casca da aba", () => {
  it("tem só duas abas: Quadro e Painel", async () => {
    // Issue #1059: o Painel entra no lugar de "Minha vez" e do Histórico.
    montar([]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(2));
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Quadro", "Painel"]);
  });
});

describe("A aba com que a Tecnologia abre (issue #1059)", () => {
  /** A tela finge ser de celular (ou não) pela mesma pergunta que o navegador responde. */
  function telaDeCelular(celular: boolean) {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((consulta: string) => ({ matches: celular && consulta.includes("max-width"), media: consulta })),
    );
  }

  const selecionada = () =>
    screen
      .getAllByRole("tab")
      .filter((t) => t.getAttribute("aria-selected") === "true")
      .map((t) => t.textContent);

  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("no celular, abre no Painel, e o Quadro nem é pedido", async () => {
    telaDeCelular(true);
    montar([]);

    await waitFor(() => expect(selecionada()).toEqual(["Painel"]));
    await waitFor(() => expect(chamadas.some((c) => c.url.includes("/painel"))).toBe(true));
    expect(chamadas.some((c) => c.url.includes("/demandas"))).toBe(false);
  });

  it("fora do celular, abre no Quadro", async () => {
    // A irmã do de cima, com a MESMA pergunta respondida ao contrário: sem ela,
    // uma tela que abrisse sempre no Painel passaria naquele.
    telaDeCelular(false);
    montar([]);

    await waitFor(() => expect(selecionada()).toEqual(["Quadro"]));
    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
  });

  it("no celular, o link de uma Demanda abre o Quadro, que é quem abre o card", async () => {
    telaDeCelular(true);
    window.history.replaceState({}, "", "/admin/tecnologia?demanda=d7");
    montar([]);

    await waitFor(() => expect(selecionada()).toEqual(["Quadro"]));
  });
});

describe("Produtos em tela própria (issue #1060)", () => {
  it("o Quadro não renderiza mais a seção Produtos", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    // A irmã de presença: o Quadro está de pé, com o botão de Nova Demanda.
    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Produtos" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Novo Produto/ })).toBeNull();
    expect(screen.queryByLabelText("Nome do Produto")).toBeNull();
  });
});

describe("Sem filtros no módulo (issue #1058)", () => {
  const aba = (nome: string) => screen.getByRole("tab", { name: nome });
  const semFiltro = () => {
    expect(screen.queryAllByRole("combobox", { name: /Filtrar por/ })).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).toBeNull();
  };

  it("nenhuma das abas tem filtro por tipo, Produto ou responsável", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    // Cada aba de pé (a irmã de presença), e sem barra de filtros nenhuma.
    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
    semFiltro();

    fireEvent.click(aba("Painel"));
    expect(await screen.findByText(/Nada esperando por você/)).toBeTruthy();
    expect(screen.getByLabelText("Buscar no Histórico")).toBeTruthy();
    semFiltro();
  });
});

describe("Quem está olhando, do ponto de vista do Vínculo (issue #674)", () => {
  const DA_VITTA: EuNaAba = {
    id: "P1",
    nome_completo: "Pedro Vitta",
    tem_github_login: true,
    integracao_configurada: true,
  };

  it("a aba pergunta ao servidor quem está olhando", async () => {
    montar([produto("prod-1", "Ana", 1)], { eu: DA_VITTA });

    await waitFor(() => {
      expect(chamadas.some((c) => c.url.endsWith("/admin/tecnologia/eu") && c.metodo === "GET")).toBe(true);
    });
  });

  it("a pergunta sai UMA vez, e não uma por aba", async () => {
    // As duas abas mostram o mesmo modal: uma chamada por aba multiplicaria a
    // ida à rede e abriria espaço para elas discordarem entre si.
    montar([produto("prod-1", "Ana", 1)], { eu: DA_VITTA });

    await waitFor(() => {
      expect(chamadas.filter((c) => c.url.endsWith("/admin/tecnologia/eu")).length).toBe(1);
    });

    fireEvent.click(screen.getByRole("tab", { name: "Painel" }));
    fireEvent.click(screen.getByRole("tab", { name: "Quadro" }));

    expect(chamadas.filter((c) => c.url.endsWith("/admin/tecnologia/eu")).length).toBe(1);
  });

  it("o `eu` que falha não derruba a aba", async () => {
    // Ele decide apenas se os controles do Vínculo aparecem: uma aba inteira em
    // vermelho porque essa rota caiu seria desproporcional. Sem resposta, vale
    // o default restrito e o resto da tela continua funcionando.
    montar([produto("prod-1", "Ana", 1)], { euFalha: true });

    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("o default de antes da resposta é o mais restrito", () => {
    expect(EU_DESCONHECIDO.tem_github_login).toBe(false);
    expect(EU_DESCONHECIDO.integracao_configurada).toBe(false);
  });
});
