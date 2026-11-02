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

import { ToastProvider } from "@/components/ui/Toast";

import { ABERTURA } from "./ChatDaTecnologia";
import { TecnologiaModulo } from "./TecnologiaModulo";
import { EU_DESCONHECIDO, EuNaAba, FALHA_DE_CONEXAO } from "./demandas";

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
    /** A rede CAI na leitura: todo `GET` rejeita, em vez de responder erro. */
    redeFora?: boolean;
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

      if (opcoes.redeFora && metodo === "GET") {
        throw new TypeError("Failed to fetch");
      }

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

  render(
    <ToastProvider>
      <TecnologiaModulo />
    </ToastProvider>,
  );
}

/** O Quadro deixou de ser a aba de abertura (issue #1381): quem o testa, abre. */
async function abrirOQuadro() {
  fireEvent.click(await screen.findByRole("tab", { name: "Quadro" }));
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
  it("tem três abas: o Assistente, o Quadro e o Painel", async () => {
    // Issue #1381 (ADR 0077): o chat do Assistente entra na frente; o Quadro e
    // o Painel saem numa fatia própria, depois.
    montar([]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Assistente", "Quadro", "Painel"]);
  });
});

describe("A aba com que a Tecnologia abre (issue #1381, ADR 0077)", () => {
  const selecionada = () =>
    screen
      .getAllByRole("tab")
      .filter((t) => t.getAttribute("aria-selected") === "true")
      .map((t) => t.textContent);

  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("abre no chat, com a pergunta bug ou melhoria, e o Quadro e o Painel nem são pedidos", async () => {
    montar([]);

    await waitFor(() => expect(selecionada()).toEqual(["Assistente"]));
    expect(screen.getByText(ABERTURA)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Bug" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Melhoria" })).toBeTruthy();
    expect(screen.getByLabelText("Sua mensagem")).toBeTruthy();
    expect(chamadas.some((c) => c.url.includes("/demandas") || c.url.includes("/painel"))).toBe(false);
  });

  it("o link de uma Demanda abre o Quadro, que é quem abre o card", async () => {
    window.history.replaceState({}, "", "/admin/tecnologia?demanda=d7");
    montar([]);

    await waitFor(() => expect(selecionada()).toEqual(["Quadro"]));
  });
});

describe("Produtos em tela própria (issue #1060)", () => {
  it("o Quadro não renderiza mais a seção Produtos", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);
    await abrirOQuadro();

    // A irmã de presença: o Quadro está de pé, com o botão de Nova Demanda.
    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Produtos" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Novo Produto/ })).toBeNull();
    expect(screen.queryByLabelText("Nome do Produto")).toBeNull();
  });
});

describe("O aviso do módulo, acima das abas (issue #1060)", () => {
  it("backend fora do ar: a aba avisa, fora do Quadro, em vez de calar", async () => {
    // Produtos e pessoas são carregados AQUI e vão para o card aberto do
    // Quadro e do Painel. Sem o aviso, a escolha de Produto ficaria vazia e
    // muda. Com a rede fora o Quadro avisa do lado dele também, por isso a
    // busca é pelo alerta que fica FORA do painel da aba: é o do módulo.
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })], { redeFora: true });

    const painel = await screen.findByRole("tabpanel");
    await waitFor(() => {
      const doModulo = screen.getAllByRole("alert").filter((a) => !painel.contains(a));
      expect(doModulo).toHaveLength(1);
      expect(doModulo[0].textContent).toContain(FALHA_DE_CONEXAO);
    });
  });

  it("durante o boot da autenticação, a aba não acusa sessão nenhuma", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }` e só entrega o
    // token depois de `getUser()` e `getSession()`. Nesse intervalo, o aviso
    // de sessão pintaria o alerta vermelho em TODA abertura da aba, com a
    // sessão perfeitamente válida. A asserção é sobre a tela inteira: o
    // módulo e as abas, que recebem `carregandoAuth` por prop.
    sessao.carregando = true;
    sessao.token = null;
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
    expect(await screen.findByRole("tabpanel")).toBeTruthy();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    // E ninguém foi à rede antes de saber se existe sessão.
    expect(chamadas).toHaveLength(0);
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
    await abrirOQuadro();

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
    await abrirOQuadro();

    expect(await screen.findByRole("link", { name: /Nova Demanda/ })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("o default de antes da resposta é o mais restrito", () => {
    expect(EU_DESCONHECIDO.tem_github_login).toBe(false);
    expect(EU_DESCONHECIDO.integracao_configurada).toBe(false);
  });
});
