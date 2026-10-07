/**
 * @vitest-environment jsdom
 */

/**
 * A aba "Minha vez" (issue #641, PRD #634, ADR 0050).
 *
 * O servidor é falso, mas a REGRA fica com ele: quem decide de quem é a vez é
 * o backend, que lê o participante da sessão. O que se prova aqui é o outro
 * lado disso, que é o que a tela pode errar sozinha:
 *
 * - ela pede `/minha-vez` e NÃO manda id de pessoa nenhum (se mandasse, a
 *   lista seria a de quem a tela achasse que é o usuário, e o `useAuth` carrega
 *   o id do Supabase Auth, que não é o `participantes.id`);
 * - ela mostra o que veio, e o porquê de cada card estar ali;
 * - ela não confunde "nada esperando por você" com falha.
 *
 * As corridas de duas leituras no ar são do `useListaDeDemandas`, e moram no
 * teste do Histórico: lá a busca troca a leitura, e aqui nada troca desde que
 * os filtros saíram do módulo (issue #1058).
 *
 * Armadilhas de teste vazio evitadas: toda asserção de ausência espera a tela
 * TERMINAR de carregar e tem irmã de presença no mesmo render.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MinhaVez } from "./MinhaVez";
import { DemandaDaMinhaVez, EU_DESCONHECIDO } from "./demandas";

const PRODUTOS = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
];

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

/** Quantos dias atrás, em texto ISO com hora, como o backend devolve. */
function diasAtras(dias: number): string {
  return new Date(Date.now() - dias * 86_400_000).toISOString();
}

function demanda(id: string, titulo: string, extra: Partial<DemandaDaMinhaVez> = {}): DemandaDaMinhaVez {
  return {
    id,
    titulo,
    descricao: null,
    tipo: "decisao",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova",
    responsavel_id: "P2",
    responsavel_nome: "Sócia Vitta",
    autor_id: "P1",
    prioridade: "normal",
    prazo: null,
    criado_em: diasAtras(1),
    concluida_em: null,
    cancelada_em: null,
    motivo: "responsavel",
    ...extra,
  };
}

let urls: string[] = [];

function montar(
  demandas: DemandaDaMinhaVez[],
  opcoes: {
    recusa?: number;
    redeFora?: boolean;
    token?: string | null;
    carregandoAuth?: boolean;
  } = {},
) {
  urls = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      if (opcoes.redeFora) throw new TypeError("Failed to fetch");
      if (url.includes("/conversa")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }
      if (opcoes.recusa) {
        return { ok: false, status: opcoes.recusa, json: async () => ({ detail: "não deu" }) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => demandas } as unknown as Response;
    }),
  );

  render(
    <MinhaVez
      token={opcoes.token === undefined ? "token-de-teste" : opcoes.token}
      carregandoAuth={opcoes.carregandoAuth ?? false}
      produtos={PRODUTOS}
      pessoas={PESSOAS}
      eu={EU_DESCONHECIDO}
    />,
  );
}

/** Espera a tela sair do "Carregando", que é a condição de toda ausência. */
async function esperarCarregar() {
  await waitFor(() => expect(screen.queryByText("Carregando o que espera por você...")).toBeNull());
}

beforeEach(() => {
  urls = [];
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A lista", () => {
  it("mostra o que o servidor devolveu, na ordem em que ele devolveu", async () => {
    // A ordem (prioridade e depois idade) é do backend, e tem teste lá. Aqui o
    // que se prova é que a tela NÃO reordena: se ela ordenasse por conta
    // própria, a regra passaria a existir em dois lugares.
    montar([
      demanda("d1", "Decidir o encerramento", { prioridade: "alta" }),
      demanda("d2", "Conferir os POPs", { prioridade: "baixa" }),
    ]);

    await screen.findByText("Decidir o encerramento");
    const titulos = within(screen.getByRole("list", { name: "Demandas esperando por você" }))
      .getAllByRole("button")
      .map((b) => b.textContent);

    expect(titulos).toEqual(["Decidir o encerramento", "Conferir os POPs"]);
  });

  it("cada linha mostra Produto, responsável, prioridade e idade", async () => {
    montar([
      demanda("d1", "Decidir o encerramento", {
        produto_nome: "POPs",
        responsavel_nome: "Pedro Vitta",
        prioridade: "alta",
        criado_em: diasAtras(3),
      }),
    ]);

    const linha = (await screen.findByText("Decidir o encerramento")).closest("li")!;

    expect(within(linha).getByText("POPs")).toBeTruthy();
    expect(within(linha).getByText("Pedro Vitta")).toBeTruthy();
    expect(within(linha).getByText("Alta")).toBeTruthy();
    expect(within(linha).getByText("há 3 dias")).toBeTruthy();
  });

  it("pede /minha-vez e não manda id de pessoa nenhum", async () => {
    // O critério da aba. A tela não sabe qual participante é o usuário logado
    // (o `useAuth` carrega o id do Supabase Auth, não o `participantes.id`), e
    // por isso ela NÃO pode ser quem diz de quem é a vez.
    montar([demanda("d1", "Decidir o encerramento")]);

    await screen.findByText("Decidir o encerramento");

    expect(urls[0]).toContain("/admin/tecnologia/minha-vez");
    expect(urls[0]).not.toContain("P1");
    expect(urls[0]).not.toContain("P2");
    expect(urls[0]).not.toContain("responsavel_id");
  });

  it("diz por que cada card está na aba", async () => {
    // Sem esta marca, o card de uma Demanda cujo responsável é OUTRA pessoa
    // não explicaria por que está aqui. As duas no mesmo render: uma tela que
    // escrevesse sempre o mesmo rótulo passaria com uma só.
    montar([
      demanda("d1", "Sou eu", { motivo: "responsavel" }),
      demanda("d2", "Me chamaram", { motivo: "mencao", responsavel_nome: "Pedro Vitta" }),
    ]);

    await screen.findByText("Sou eu");

    expect(within(screen.getByText("Sou eu").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
    expect(within(screen.getByText("Me chamaram").closest("li")!).getByText("Mencionaram você")).toBeTruthy();
  });

  it("mostra o recado da entrega no card que voltou para quem pediu", async () => {
    // Issue #679: a Entrega devolve o card e o selo diz o que fazer com ele. O
    // card comum entra no mesmo render: uma tela que escrevesse o recado em
    // todo card passaria com um só.
    montar([
      demanda("d1", "Entregue para conferir", { motivo: "entregue", estado: "aguardando" }),
      demanda("d2", "Ainda comigo", { motivo: "responsavel" }),
    ]);

    await screen.findByText("Entregue para conferir");

    expect(
      within(screen.getByText("Entregue para conferir").closest("li")!).getByText("Entregue, confira e conclua"),
    ).toBeTruthy();
    expect(within(screen.getByText("Ainda comigo").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
  });

  it("abre o modal da Demanda ao clicar na linha", async () => {
    montar([demanda("d1", "Decidir o encerramento")]);

    fireEvent.click(await screen.findByText("Decidir o encerramento"));

    expect(await screen.findByRole("dialog")).toBeTruthy();
  });
});

describe("A lista vazia", () => {
  it("diz que não há nada esperando, e não que falhou", async () => {
    montar([]);
    await esperarCarregar();

    expect(screen.getByText(/Nada esperando por você agora/)).toBeTruthy();
    // A ausência que importa: vazio aqui é boa notícia, e não pode desenhar o
    // alerta vermelho. A espera acima é o que dá valor a esta linha.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Quando não dá para ler", () => {
  it("a autenticação carregando NÃO é sessão ausente", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }`. Ler esse token
    // nulo como "não há sessão" pisca o alerta vermelho em toda abertura da
    // aba, com a sessão perfeitamente válida (foi must-fix na fatia #637).
    montar([], { token: null, carregandoAuth: true });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(screen.queryByRole("alert")).toBeNull();
    // A irmã de presença: a tela diz o que está de fato acontecendo.
    expect(screen.getByText("Carregando o que espera por você...")).toBeTruthy();
  });

  it("resolvida a autenticação, token nulo vira aviso", async () => {
    // O par do teste acima: sem ele, uma tela que engolisse TODO token nulo
    // passaria naquele.
    montar([], { token: null, carregandoAuth: false });

    expect((await screen.findByRole("alert")).textContent).toContain("a sessão não está ativa");
    expect(screen.queryByText("Carregando o que espera por você...")).toBeNull();
  });

  it("a rede fora vira aviso, e não lista vazia", async () => {
    montar([], { redeFora: true });

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    // O que não pode acontecer: a frase de boa notícia por cima de uma falha.
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
  });

  it("o erro do servidor vira aviso, e não lista vazia", async () => {
    montar([], { recusa: 500 });

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Não foi possível carregar o que espera por você.",
    );
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
  });
});
