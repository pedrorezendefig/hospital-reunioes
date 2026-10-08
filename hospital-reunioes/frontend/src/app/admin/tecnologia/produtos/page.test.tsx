/**
 * @vitest-environment jsdom
 */

/**
 * A tela de Produtos (issue #636, PRD #634, ADR 0050), em endereço próprio
 * desde a issue #1060 (PRD #1056): saiu do rodapé do Quadro e mora atrás da
 * engrenagem ao lado de "Nova Demanda".
 *
 * O servidor é falso, mas as REGRAS ficam com ele: a tela não decide quem pode
 * ser dono nem recusa Produto ativo sem dono, ela mostra o que a API respondeu.
 * Por isso as asserções olham duas coisas: o que o Super admin vê e a chamada
 * que o clique dispara (URL, método e corpo), que é o que a tela realmente
 * controla.
 *
 * Duas armadilhas de teste vazio evitadas aqui:
 *
 * - afirmar que a lista tem sete linhas passaria com a tela ignorando a API e
 *   desenhando uma lista fixa; por isso o teste da lista confere os NOMES que
 *   vieram na resposta;
 * - afirmar que o Produto desativado "sumiu" seria o contrário do critério: o
 *   que se afirma é o marcador positivo, a linha continua e aparece Inativo.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProdutosPage from "./page";

// `loading` é parametrizável de propósito, e não cravado em `false`: cravar
// esconde o estado de BOOT do `useAuth` (`{ token: null, loading: true }`, duas
// idas à rede antes do token), que é onde um aviso de sessão apressado vira
// alarme falso em toda abertura da tela.
const sessao = vi.hoisted(() => ({
  token: "token-de-teste" as string | null,
  carregando: false,
}));

const perfil = vi.hoisted(() => ({
  participante: { id: "p1", nome_completo: "Pedro", email: "p@hsm.com", access_profile: "super_admin" } as Record<
    string,
    unknown
  > | null,
  loading: false,
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    token: sessao.token,
    userId: sessao.token ? "auth-1" : null,
    userEmail: sessao.token ? "p1@hsm" : null,
    loading: sessao.carregando,
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({ participante: perfil.participante, loading: perfil.loading, error: null }),
}));

type Chamada = { url: string; metodo: string; corpo: unknown };

const SETE_PRODUTOS = ["Ana", "Integração Ana x MV", "Reuniões", "Ouvidoria", "POPs", "Site", "Infra"];

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

/**
 * Monta a tela com o servidor falso.
 *
 * `recusa` é a resposta que o SERVIDOR dá à escrita, com o status e a frase
 * dele: é ela que o Super admin precisa ler na tela.
 */
function montar(
  produtos: ReturnType<typeof produto>[],
  opcoes: {
    recusa?: { status: number; detail: string };
    // A rede CAI: o `fetch` rejeita, em vez de responder com status de erro.
    // São dois caminhos diferentes no componente, por isso dois valores.
    redeFora?: "carregar" | "salvar";
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

      if (
        (opcoes.redeFora === "carregar" && metodo === "GET") ||
        (opcoes.redeFora === "salvar" && metodo !== "GET")
      ) {
        throw new TypeError("Failed to fetch");
      }

      if (metodo !== "GET") {
        if (opcoes.recusa) {
          return {
            ok: false,
            status: opcoes.recusa.status,
            json: async () => ({ detail: opcoes.recusa!.detail }),
          } as unknown as Response;
        }
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }

      const corpo = url.includes("/pessoas") ? PESSOAS : produtos;
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  render(<ProdutosPage />);
}

const escritas = () => chamadas.filter((c) => c.metodo !== "GET");

beforeEach(() => {
  chamadas = [];
  perfil.participante = { id: "p1", nome_completo: "Pedro", email: "p@hsm.com", access_profile: "super_admin" };
  perfil.loading = false;
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

describe("A tela própria de Produtos (issue #1060)", () => {
  it("tem um caminho de volta ao Quadro", async () => {
    montar([]);

    const volta = await screen.findByRole("link", { name: "Voltar ao Quadro" });
    expect(volta.getAttribute("href")).toBe("/admin/tecnologia");
  });

  it("quem não é Super admin não alcança o cadastro", () => {
    perfil.participante = { id: "p2", nome_completo: "Outra", email: "o@hsm.com", access_profile: "regular" };
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    expect(screen.getByText(/Sem acesso à aba Tecnologia/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Novo Produto/ })).toBeNull();
    // Nem foi à rede: o cadastro não chegou a montar.
    expect(chamadas).toHaveLength(0);
  });

  it("enquanto o perfil não chegou, o cadastro não é desenhado", () => {
    // Desenhar e esconder depois deixaria os botões à mão de quem não é Super
    // admin durante as idas à rede do hook. O layout de `/admin` deixa entrar
    // qualquer papel.
    perfil.loading = true;
    perfil.participante = null;
    montar([]);

    expect(screen.queryByRole("button", { name: /Novo Produto/ })).toBeNull();
    expect(screen.queryByText(/Sem acesso à aba Tecnologia/)).toBeNull();
  });

  it("o Super admin alcança o cadastro", async () => {
    // O par de presença: uma tela que recusasse todo mundo passaria nos dois
    // acima sozinha.
    montar([]);

    expect(await screen.findByRole("button", { name: /Novo Produto/ })).toBeTruthy();
    expect(screen.queryByText(/Sem acesso à aba Tecnologia/)).toBeNull();
  });
});

describe("A lista de Produtos", () => {
  it("mostra os sete Produtos que a API devolveu, sem cadastro prévio", async () => {
    montar(SETE_PRODUTOS.map((nome, i) => produto(`p${i}`, nome, i + 1, { dono_id: "P1" })));

    for (const nome of SETE_PRODUTOS) {
      expect(await screen.findByText(nome)).toBeTruthy();
    }
  });

  it("o Produto desativado continua na lista, marcado como inativo", async () => {
    montar([
      produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" }),
      produto("p2", "Site", 2, { ativo: false }),
    ]);

    const linha = (await screen.findByText("Site")).closest("li")!;
    expect(within(linha).getByText("Inativo")).toBeTruthy();

    // O par de presença: "Inativo" só significa algo porque a outra linha diz
    // "Ativo" no mesmo render.
    const viva = screen.getByText("Ana").closest("li")!;
    expect(within(viva).getByText("Ativo")).toBeTruthy();
  });

  it("o Produto ativo sem dono aparece marcado, e o que tem dono não", async () => {
    // Os sete do seed nascem ativos e sem dono, e a API não recusa renomear um
    // deles. Quem cobra o dono é esta marca, então ela é o marcador positivo do
    // critério "a tela avisa".
    montar([produto("p1", "Ana", 1), produto("p2", "Site", 2, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    const orfa = (await screen.findByText("Ana")).closest("li")!;
    expect(within(orfa).getByText("Falta dono")).toBeTruthy();

    const cuidada = screen.getByText("Site").closest("li")!;
    expect(within(cuidada).queryByText("Falta dono")).toBeNull();
  });

  it("o Produto inativo sem dono não é cobrado", async () => {
    // Sem dono só é problema enquanto o Produto está ativo: inativo não recebe
    // Demanda nova.
    montar([produto("p1", "Ana", 1, { ativo: false })]);

    const linha = (await screen.findByText("Ana")).closest("li")!;
    expect(within(linha).getByText("Inativo")).toBeTruthy();
    expect(within(linha).queryByText("Falta dono")).toBeNull();
  });

  it("o dono que perdeu o acesso à aba aparece marcado, e o que tem acesso não", async () => {
    // Par na tela do carimbo do backend: a API recusa abrir Demanda num
    // Produto assim e manda trocar o dono AQUI. Sem a marca, quem segue a
    // instrução chega na lista, vê um nome normal e não descobre qual é o
    // problema.
    montar([
      produto("p1", "Ana", 1, { dono_id: "P9", dono_nome: "Saiu da Vitta" }),
      produto("p2", "POPs", 2, { dono_id: "P1", dono_nome: "Pedro Vitta" }),
    ]);

    const orfao = await screen.findByRole("combobox", { name: "Dono de Ana" });
    expect(orfao.textContent).toContain("Saiu da Vitta (sem acesso à aba)");

    const cuidado = screen.getByRole("combobox", { name: "Dono de POPs" });
    expect(cuidado.textContent).toContain("Pedro Vitta");
    expect(cuidado.textContent).not.toContain("sem acesso à aba");
  });

  it("o dono só pode ser escolhido entre as pessoas com acesso à aba", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    const seletor = await screen.findByRole("combobox", { name: "Dono de Ana" });
    fireEvent.click(seletor);

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Pedro Vitta", "Sócia Vitta"]);
  });
});

describe("O Super admin mexe nos Produtos", () => {
  it("cria um Produto com nome e dono", async () => {
    montar([]);
    await screen.findByRole("button", { name: /Novo Produto/ });

    fireEvent.change(screen.getByLabelText("Nome do Produto"), {
      target: { value: "Portal do Paciente" },
    });
    fireEvent.click(screen.getByRole("combobox", { name: "Dono do Produto novo" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Sócia Vitta"));
    fireEvent.click(screen.getByRole("button", { name: /Novo Produto/ }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/produtos",
      metodo: "POST",
      corpo: { nome: "Portal do Paciente", dono_id: "P2" },
    });
  });

  it("renomeia um Produto", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    fireEvent.click(await screen.findByRole("button", { name: "Renomear Ana" }));
    fireEvent.change(screen.getByLabelText("Novo nome de Ana"), {
      target: { value: "Ana WhatsApp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar nome" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/produtos/p1",
      metodo: "PATCH",
      corpo: { nome: "Ana WhatsApp" },
    });
  });

  it("desativa um Produto", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    fireEvent.click(await screen.findByRole("button", { name: "Desativar Ana" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/produtos/p1",
      metodo: "PATCH",
      corpo: { ativo: false },
    });
  });

  it("reativa um Produto", async () => {
    // A irmã do de cima: o mesmo botão manda o contrário quando o Produto está
    // inativo. Sem ela, um botão que sempre desativasse passaria.
    montar([produto("p1", "Ana", 1, { ativo: false })]);

    fireEvent.click(await screen.findByRole("button", { name: "Reativar Ana" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/produtos/p1",
      metodo: "PATCH",
      corpo: { ativo: true },
    });
  });

  it("troca o dono do Produto", async () => {
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    fireEvent.click(await screen.findByRole("combobox", { name: "Dono de Ana" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Sócia Vitta"));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/produtos/p1",
      metodo: "PATCH",
      corpo: { dono_id: "P2" },
    });
  });
});

describe("A falha de rede não vira lista vazia e calada", () => {
  it("backend fora do ar: a tela avisa, em vez de fingir que não há Produto", async () => {
    // Sem aviso, quem abrisse com o backend parado concluiria que o seed da
    // migration não rodou.
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })], { redeFora: "carregar" });

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
    expect(screen.queryByText("Carregando Produtos...")).toBeNull();
  });

  it("rede fora ao salvar: o clique em Novo Produto avisa", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([], { redeFora: "salvar" });
    await screen.findByRole("button", { name: /Novo Produto/ });

    fireEvent.change(screen.getByLabelText("Nome do Produto"), {
      target: { value: "Portal do Paciente" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Novo Produto/ }));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
  });

  it("sem token, a tela diz o que houve em vez de girar para sempre", async () => {
    // A frase é a das DUAS causas de propósito. O `useAuth` devolve
    // `token: null` tanto com a sessão acabada quanto com o `getUser()` dele
    // falhando por rede, e a tela não distingue: mandar entrar de novo
    // cobraria justo a ação impossível quando a causa é a rede.
    sessao.token = null;
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("a sessão não está ativa ou o servidor não respondeu");
    expect(aviso.textContent).toContain("Tente recarregar a página");
    expect(screen.queryByText("Carregando Produtos...")).toBeNull();
  });

  it("durante o boot da autenticação, a tela não acusa sessão nenhuma", () => {
    sessao.carregando = true;
    sessao.token = null;
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    // E ninguém foi à rede antes de saber se existe sessão.
    expect(chamadas).toHaveLength(0);
  });

  it("com token e servidor de pé, a espera termina e a lista aparece", async () => {
    // O par de presença dos três acima: sem ele, uma tela que nunca mostrasse
    // "Carregando Produtos..." passaria em todos.
    montar([produto("p1", "Ana", 1, { dono_id: "P1", dono_nome: "Pedro Vitta" })]);

    expect(screen.getByText("Carregando Produtos...")).toBeTruthy();
    expect(await screen.findByText("Ana")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("A recusa do servidor chega ao Super admin", () => {
  it("mostra o motivo de 422 ao tentar criar Produto ativo sem dono", async () => {
    montar([], {
      recusa: {
        status: 422,
        detail: "Produto ativo precisa de dono. Escolha um dono ou desative o Produto.",
      },
    });
    await screen.findByRole("button", { name: /Novo Produto/ });

    fireEvent.change(screen.getByLabelText("Nome do Produto"), {
      target: { value: "Portal do Paciente" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Novo Produto/ }));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Produto ativo precisa de dono");
  });

  it("sem recusa, nenhum aviso aparece", async () => {
    // O par de presença do teste acima: um `role="alert"` cravado na tela
    // passaria naquele sozinho.
    montar([]);
    await screen.findByRole("button", { name: /Novo Produto/ });

    fireEvent.change(screen.getByLabelText("Nome do Produto"), {
      target: { value: "Portal do Paciente" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Novo Produto/ }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
