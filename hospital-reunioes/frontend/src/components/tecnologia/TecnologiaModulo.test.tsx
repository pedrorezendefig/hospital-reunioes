/**
 * @vitest-environment jsdom
 */

/**
 * A tela da aba Tecnologia (issue #636, PRD #634, ADR 0050).
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

const SETE_PRODUTOS = [
  "Ana",
  "Integração Ana x MV",
  "Reuniões",
  "Ouvidoria",
  "POPs",
  "Site",
  "Infra",
];

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
    pessoas?: typeof PESSOAS;
    recusa?: { status: number; detail: string };
    // A rede CAI: o `fetch` rejeita, em vez de responder com status de erro.
    // São dois caminhos diferentes no componente, por isso dois valores.
    redeFora?: "carregar" | "salvar";
    /** Quem está olhando, do ponto de vista do Vínculo (issue #674). */
    eu?: EuNaAba;
    /** O `GET /eu` responde erro: a aba tem que seguir de pé sem ele. */
    euFalha?: boolean;
  } = {},
) {
  chamadas = [];
  const pessoas = opcoes.pessoas ?? PESSOAS;

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

      // As três abas (o Quadro da issue #637, e "Minha vez" e o Histórico da
      // #641) carregam as próprias listas e têm teste só delas: aqui elas ficam
      // vazias, para não disputar os `getBy*` com a lista de Produtos.
      if (url.includes("/demandas") || url.includes("/minha-vez") || url.includes("/historico")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }

      if (url.endsWith("/eu")) {
        if (opcoes.euFalha) {
          return { ok: false, status: 500, json: async () => ({}) } as unknown as Response;
        }
        const eu = opcoes.eu ?? EU_DESCONHECIDO;
        return { ok: true, status: 200, json: async () => eu } as unknown as Response;
      }

      const corpo = url.includes("/pessoas") ? pessoas : produtos;
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  render(<TecnologiaModulo />);
}

const escritas = () => chamadas.filter((c) => c.metodo !== "GET");

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
  it("nasce com as três abas do quadro", async () => {
    montar([]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Quadro",
      "Minha vez",
      "Histórico",
    ]);
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
    montar([
      produto("p1", "Ana", 1),
      produto("p2", "Site", 2, { dono_id: "P1", dono_nome: "Pedro Vitta" }),
    ]);

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
    // O critério de aceite é "a tela lista os sete Produtos na primeira
    // abertura". Sem aviso, quem abrisse com o backend parado concluiria que o
    // seed da migration não rodou.
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })], { redeFora: "carregar" });

    // A busca é dentro da seção de Produtos: com a rede fora, o Quadro avisa
    // do lado dele também, e o que se afirma aqui é o aviso DESTA lista.
    const secao = screen.getByRole("region", { name: "Produtos" });
    const aviso = await within(secao).findByRole("alert");
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
    // `carregar` desiste na primeira linha quando não há token, e sem este
    // caminho ninguém desligaria a espera: "Carregando Produtos..." ficaria na
    // tela até a pessoa desistir.
    //
    // A frase é a das DUAS causas de propósito. O `useAuth` devolve
    // `token: null` tanto com a sessão acabada quanto com o `getUser()` dele
    // falhando por rede, e o componente não distingue: mandar entrar de novo
    // cobraria justo a ação impossível quando a causa é a rede. Asserir esse
    // trecho é o que trava a volta da frase antiga.
    sessao.token = null;
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    // Dentro da seção de Produtos: sem sessão, o Quadro avisa do lado dele
    // também (com a frase dele, sobre Demandas), e o que se afirma aqui é o
    // aviso DESTA lista.
    const secao = screen.getByRole("region", { name: "Produtos" });
    const aviso = await within(secao).findByRole("alert");
    expect(aviso.textContent).toContain(
      "a sessão não está ativa ou o servidor não respondeu"
    );
    expect(aviso.textContent).toContain("Tente recarregar a página");
    expect(screen.queryByText("Carregando Produtos...")).toBeNull();
  });

  it("durante o boot da autenticação, a aba não acusa sessão nenhuma", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }` e só entrega o
    // token depois de `getUser()` e `getSession()`. Nesse intervalo, um aviso
    // de sessão pintaria o alerta vermelho em TODA abertura da aba, com a
    // sessão perfeitamente válida. A asserção é sobre a tela inteira, e não só
    // sobre a lista de Produtos: quem grita aqui é o Quadro, que recebe o
    // token por prop e não veria o `loading` sozinho.
    sessao.carregando = true;
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
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

describe("Os filtros do Quadro, lembrados entre as abas", () => {
  const aba = (nome: string) => screen.getByRole("tab", { name: nome });
  const demandasPedidas = () => chamadas.filter((c) => c.url.includes("/demandas"));

  it("o filtro escolhido continua valendo depois de ir a outra aba e voltar", async () => {
    // Se os filtros morassem dentro do Quadro, a troca de aba desmontaria o
    // componente e o filtro voltaria ao zero: por isso eles moram aqui.
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    fireEvent.click(await screen.findByRole("combobox", { name: "Filtrar por tipo" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ajuste"));
    await waitFor(() =>
      expect(demandasPedidas().at(-1)!.url).toBe("/api/admin/tecnologia/demandas?tipo=ajuste"),
    );

    fireEvent.click(aba("Minha vez"));
    // O painel trocou de verdade: o botão de abrir Demanda é do Quadro, e ele
    // saiu de cena junto com ele.
    expect(screen.queryByRole("button", { name: /Nova Demanda/ })).toBeNull();
    // E o filtro atravessou a troca: desde a issue #641 a aba nova desenha a
    // mesma barra, já com o tipo escolhido no Quadro.
    expect(screen.getByRole("combobox", { name: "Filtrar por tipo" }).textContent).toContain("Ajuste");

    fireEvent.click(aba("Quadro"));

    const filtro = await screen.findByRole("combobox", { name: "Filtrar por tipo" });
    expect(filtro.textContent).toContain("Ajuste");
    await waitFor(() =>
      expect(demandasPedidas().at(-1)!.url).toBe("/api/admin/tecnologia/demandas?tipo=ajuste"),
    );
  });

  it("sem escolher filtro, a volta à aba pede o Quadro inteiro", async () => {
    // O par de presença do teste acima: uma tela que sempre mandasse
    // `?tipo=ajuste` passaria naquele sozinho.
    montar([produto("p1", "Ana", 1, { dono_id: "P1" })]);

    await screen.findByRole("combobox", { name: "Filtrar por tipo" });
    fireEvent.click(aba("Histórico"));
    fireEvent.click(aba("Quadro"));

    await waitFor(() => expect(demandasPedidas().at(-1)!.url).toBe("/api/admin/tecnologia/demandas"));
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
    // As três abas mostram o mesmo modal: uma chamada por aba multiplicaria a
    // ida à rede e abriria espaço para elas discordarem entre si.
    montar([produto("prod-1", "Ana", 1)], { eu: DA_VITTA });

    await waitFor(() => {
      expect(chamadas.filter((c) => c.url.endsWith("/admin/tecnologia/eu")).length).toBe(1);
    });

    fireEvent.click(screen.getByRole("tab", { name: "Minha vez" }));
    fireEvent.click(screen.getByRole("tab", { name: "Histórico" }));

    expect(chamadas.filter((c) => c.url.endsWith("/admin/tecnologia/eu")).length).toBe(1);
  });

  it("o `eu` que falha não derruba a aba", async () => {
    // Ele decide apenas se os controles do Vínculo aparecem: uma aba inteira em
    // vermelho porque essa rota caiu seria desproporcional. Sem resposta, vale
    // o default restrito e o resto da tela continua funcionando.
    montar([produto("prod-1", "Ana", 1)], { euFalha: true });

    expect(await screen.findByText("Ana")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("o default de antes da resposta é o mais restrito", () => {
    expect(EU_DESCONHECIDO.tem_github_login).toBe(false);
    expect(EU_DESCONHECIDO.integracao_configurada).toBe(false);
  });
});
