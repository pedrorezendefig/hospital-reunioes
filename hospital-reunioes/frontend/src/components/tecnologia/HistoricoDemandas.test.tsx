/**
 * @vitest-environment jsdom
 */

/**
 * A aba Histórico (issue #641, PRD #634, ADR 0050).
 *
 * O servidor é falso, e a busca de verdade (título, descrição e o texto das
 * respostas da Conversa) é dele, com teste no backend. O que se prova aqui é o
 * que a tela pode errar sozinha:
 *
 * - o termo digitado vira `busca` na URL, depois que a digitação para;
 * - termo só de espaços não vira busca nenhuma;
 * - a linha diz quando e por quem a Demanda fechou;
 * - as quatro listas vazias dizem coisas diferentes (nada ainda, filtro, busca,
 *   e busca com filtro);
 * - duas leituras no ar não pintam a lista errada.
 *
 * Toda asserção de ausência espera a tela terminar de carregar e tem irmã de
 * presença no mesmo render.
 */

import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HistoricoDemandas } from "./HistoricoDemandas";
import { DemandaDoHistorico, FiltrosDoQuadro, SEM_FILTRO } from "./demandas";

const PRODUTOS = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
];

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

function demanda(id: string, titulo: string, extra: Partial<DemandaDoHistorico> = {}): DemandaDoHistorico {
  return {
    id,
    titulo,
    descricao: null,
    tipo: "decisao",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "concluida",
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P1",
    prioridade: "normal",
    prazo: null,
    criado_em: "2026-09-01T09:00:00Z",
    concluida_em: "2026-09-08T15:00:00Z",
    cancelada_em: null,
    fechada_em: "2026-09-08T15:00:00Z",
    fechada_por_id: "P2",
    fechada_por_nome: "Sócia Vitta",
    ...extra,
  };
}

let urls: string[] = [];

function montar(
  demandas: DemandaDoHistorico[],
  opcoes: {
    recusa?: number;
    // O servidor recusa SÓ quando há termo de busca. É o cenário em que a
    // lista de antes está na tela e a leitura nova falha.
    recusaNaBusca?: number;
    redeFora?: boolean;
    token?: string | null;
    carregandoAuth?: boolean;
    filtrosIniciais?: FiltrosDoQuadro;
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
      if (opcoes.recusaNaBusca && url.includes("busca=")) {
        return {
          ok: false,
          status: opcoes.recusaNaBusca,
          json: async () => ({ detail: "não deu" }),
        } as unknown as Response;
      }
      if (opcoes.recusa) {
        return { ok: false, status: opcoes.recusa, json: async () => ({ detail: "não deu" }) } as unknown as Response;
      }
      // Quem busca e quem filtra é o SERVIDOR: uma tela que peneirasse por
      // conta própria receberia tudo aqui e mostraria tudo.
      const parametros = new URLSearchParams(url.split("?")[1] ?? "");
      const termo = (parametros.get("busca") ?? "").toLowerCase();
      const casa = (chave: string, valor: string | null) =>
        !parametros.get(chave) || parametros.get(chave) === valor;
      const corpo = demandas.filter(
        (d) =>
          casa("tipo", d.tipo) &&
          casa("produto_id", d.produto_id) &&
          casa("responsavel_id", d.responsavel_id) &&
          (!termo || d.titulo.toLowerCase().includes(termo)),
      );
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(opcoes.filtrosIniciais ?? SEM_FILTRO);
    return (
      <HistoricoDemandas
        token={opcoes.token === undefined ? "token-de-teste" : opcoes.token}
        carregandoAuth={opcoes.carregandoAuth ?? false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
      />
    );
  }

  render(<Anfitriao />);
}

async function esperarCarregar() {
  await waitFor(() => expect(screen.queryByText("Carregando o Histórico...")).toBeNull());
}

function digitarNaBusca(termo: string) {
  fireEvent.change(screen.getByLabelText("Buscar no Histórico"), { target: { value: termo } });
}

beforeEach(() => {
  urls = [];
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A lista", () => {
  it("mostra o que o servidor devolveu, com o contador", async () => {
    montar([demanda("d1", "Encerrar conversas"), demanda("d2", "Trocar o logotipo")]);

    await screen.findByText("Encerrar conversas");

    expect(screen.getByText("2 Demandas fechadas")).toBeTruthy();
    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
  });

  it("cada linha diz quando e por quem a Demanda fechou", async () => {
    montar([
      demanda("d1", "Encerrar conversas", { fechada_por_nome: "Sócia Vitta" }),
      demanda("d2", "Trocar o logotipo", {
        estado: "cancelada",
        fechada_em: "2026-09-07T10:00:00Z",
        fechada_por_nome: "Pedro Vitta",
      }),
    ]);

    await screen.findByText("Encerrar conversas");

    const concluida = within(screen.getByText("Encerrar conversas").closest("li")!);
    expect(concluida.getByText(/Concluída/)).toBeTruthy();
    expect(concluida.getByText(/por Sócia Vitta/)).toBeTruthy();

    // A irmã do mesmo render: uma tela que escrevesse "Concluída" cravado
    // passaria na asserção acima.
    const cancelada = within(screen.getByText("Trocar o logotipo").closest("li")!);
    expect(cancelada.getByText(/Cancelada/)).toBeTruthy();
    expect(cancelada.getByText(/por Pedro Vitta/)).toBeTruthy();
  });

  it("sem o carimbo de quem fechou, a linha diz que não há registro", async () => {
    montar([demanda("d1", "Encerrar conversas", { fechada_por_nome: null })]);

    const linha = within((await screen.findByText("Encerrar conversas")).closest("li")!);

    expect(linha.getByText(/sem registro de quem/)).toBeTruthy();
  });

  it("abre o mesmo modal da Demanda ao clicar na linha", async () => {
    montar([demanda("d1", "Encerrar conversas")]);

    fireEvent.click(await screen.findByText("Encerrar conversas"));

    expect(await screen.findByRole("dialog")).toBeTruthy();
  });
});

describe("A busca", () => {
  it("a caixa diz o que a busca procura", async () => {
    // A promessa da caixa: quem digita precisa saber que a Conversa entra,
    // antes de concluir que "não tem nada sobre X".
    montar([demanda("d1", "Encerrar conversas")]);
    await screen.findByText("Encerrar conversas");

    expect(screen.getByPlaceholderText(/título, descrição ou texto da Conversa/)).toBeTruthy();
  });

  it("o termo digitado vira `busca` na chamada", async () => {
    montar([demanda("d1", "Encerrar conversas"), demanda("d2", "Trocar o logotipo")]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("logotipo");

    await waitFor(() => expect(urls[urls.length - 1]).toContain("busca=logotipo"));
    expect(await screen.findByText("Trocar o logotipo")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
  });

  it("termo só de espaços não vira busca", async () => {
    // Mandar `busca=%20` faria a API procurar um espaço, e a tela diria "nada
    // encontrado" para quem não buscou nada.
    montar([demanda("d1", "Encerrar conversas")]);
    await screen.findByText("Encerrar conversas");
    const antes = urls.length;

    digitarNaBusca("   ");

    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    for (const url of urls.slice(antes)) expect(url).not.toContain("busca=");
    // A irmã de presença: a lista continua ali, e não foi esvaziada.
    expect(screen.getByText("Encerrar conversas")).toBeTruthy();
  });

  it("a busca espera a digitação parar, e não pede uma vez por tecla", async () => {
    montar([demanda("d1", "Encerrar conversas")]);
    await screen.findByText("Encerrar conversas");
    const antes = urls.length;

    digitarNaBusca("l");
    digitarNaBusca("lo");
    digitarNaBusca("log");
    digitarNaBusca("logo");

    await waitFor(() => expect(urls.length).toBeGreaterThan(antes));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });

    // Uma chamada só, a do termo inteiro: sem a espera seriam quatro, cada uma
    // varrendo o Histórico inteiro no servidor.
    expect(urls.slice(antes)).toHaveLength(1);
    expect(urls[urls.length - 1]).toContain("busca=logo");
  });

  it("apagar a busca traz o Histórico inteiro de volta", async () => {
    montar([demanda("d1", "Encerrar conversas"), demanda("d2", "Trocar o logotipo")]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("logotipo");
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    digitarNaBusca("");

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(urls[urls.length - 1]).not.toContain("busca=");
  });
});

describe("A lista vazia", () => {
  it("sem busca e sem filtro, diz que ainda não fechou nada", async () => {
    montar([]);
    await esperarCarregar();

    expect(screen.getByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a busca sem resultado cita o termo procurado", async () => {
    montar([demanda("d1", "Encerrar conversas")]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("ouvidoria");

    expect(await screen.findByText(/"ouvidoria"/)).toBeTruthy();
    // Sem filtro ligado, a frase não manda limpar filtro nenhum: pedir uma ação
    // impossível deixa quem leu sem saída.
    expect(screen.queryByText(/limpe os filtros/)).toBeNull();
  });

  it("a frase cita o termo da lista que está na tela, e não o que está sendo digitado", async () => {
    // Entre a tecla e o fim da espera, a lista ainda é a da busca ANTERIOR.
    // Citar o termo novo daria a ele um resultado que não é dele: a pessoa leria
    // "nada com xyz" antes de o servidor ter sido perguntado sobre "xyz".
    montar([demanda("d1", "Encerrar conversas")]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("ouvidoria");
    expect(await screen.findByText(/"ouvidoria"/)).toBeTruthy();

    digitarNaBusca("xyz");

    expect(screen.getByText(/"ouvidoria"/)).toBeTruthy();
    expect(screen.queryByText(/"xyz"/)).toBeNull();
    // A irmã de presença: passada a espera, a frase acompanha o termo novo.
    expect(await screen.findByText(/"xyz"/)).toBeTruthy();
  });

  it("com filtro e sem busca, aponta o filtro e onde limpar", async () => {
    montar([], { filtrosIniciais: { tipo: "defeito", produto_id: "", responsavel_id: "" } });
    await esperarCarregar();

    expect(screen.getByText(/Limpe os filtros acima/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Limpar filtros" })).toBeTruthy();
  });
});

describe("Os filtros herdados das outras abas", () => {
  it("o filtro que veio por prop entra na chamada", async () => {
    montar([demanda("d1", "Encerrar conversas")], {
      filtrosIniciais: { tipo: "decisao", produto_id: "prod-1", responsavel_id: "P1" },
    });

    await screen.findByText("Encerrar conversas");

    expect(urls[0]).toContain("tipo=decisao");
    expect(urls[0]).toContain("produto_id=prod-1");
    expect(urls[0]).toContain("responsavel_id=P1");
  });

  it("o filtro e a busca viajam juntos", async () => {
    montar([demanda("d1", "Encerrar conversas")], {
      filtrosIniciais: { tipo: "decisao", produto_id: "", responsavel_id: "" },
    });
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("encerrar");

    await waitFor(() => expect(urls[urls.length - 1]).toContain("busca=encerrar"));
    expect(urls[urls.length - 1]).toContain("tipo=decisao");
  });
});

describe("Quando não dá para ler", () => {
  it("a autenticação carregando NÃO é sessão ausente", async () => {
    montar([], { token: null, carregandoAuth: true });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Carregando o Histórico...")).toBeTruthy();
  });

  it("resolvida a autenticação, token nulo vira aviso", async () => {
    montar([], { token: null, carregandoAuth: false });

    expect((await screen.findByRole("alert")).textContent).toContain("a sessão não está ativa");
  });

  it("a rede fora vira aviso, e não Histórico vazio", async () => {
    montar([], { redeFora: true });

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    expect(screen.queryByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeNull();
  });

  it("o erro do servidor vira aviso, e não Histórico vazio", async () => {
    montar([], { recusa: 500 });

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar o Histórico.");
    expect(screen.queryByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeNull();
  });

  it("a leitura que falha leva a lista de ANTES junto, com o contador", async () => {
    // O que não pode acontecer: alerta vermelho, a caixa de busca escrita com o
    // termo novo, e embaixo a lista da busca anterior com "1 Demanda fechada".
    // O contador é mais forte que uma frase de vazio: ele diz um NÚMERO para uma
    // busca que o servidor recusou.
    montar([demanda("d1", "Encerrar conversas")], { recusaNaBusca: 500 });

    // O marcador positivo: a lista e o contador ESTAVAM na tela.
    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(screen.getByText("1 Demanda fechada")).toBeTruthy();

    digitarNaBusca("xyz");

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar o Histórico.");
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    expect(screen.queryByText("1 Demanda fechada")).toBeNull();
    // E nenhuma frase de vazio ocupa o lugar: sob erro o código não sabe se o
    // Histórico está vazio.
    expect(screen.queryByText(/Nenhuma Demanda/)).toBeNull();
  });

  it("a leitura seguinte que dá certo apaga o aviso e traz a lista de volta", async () => {
    // A irmã de presença da de cima, e a prova de que a leitura boa LIMPA o
    // alerta da leitura anterior.
    montar([demanda("d1", "Encerrar conversas")], { recusaNaBusca: 500 });
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("xyz");
    await screen.findByRole("alert");

    digitarNaBusca("");

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("1 Demanda fechada")).toBeTruthy();
  });
});

describe("Duas leituras no ar ao mesmo tempo", () => {
  type Pendente = { url: string; responder: (dados: DemandaDoHistorico[]) => void };

  function filaDeChamadas(): Pendente[] {
    const pendentes: Pendente[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise((resolve) => {
            pendentes.push({
              url,
              responder: (dados) =>
                resolve({ ok: true, status: 200, json: async () => dados } as unknown as Response),
            });
          }),
      ),
    );
    return pendentes;
  }

  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <HistoricoDemandas
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
      />
    );
  }

  const ENCERRAR = demanda("d1", "Encerrar conversas");
  const LOGOTIPO = demanda("d2", "Trocar o logotipo");

  async function deixarOReactProcessar() {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  /** `[0]` é a leitura inicial, `[1]` a busca por "encerrar" (VELHA), `[2]` a por "logotipo" (NOVA). */
  async function comDuasBuscasNoAr(): Promise<Pendente[]> {
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder([ENCERRAR, LOGOTIPO]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("encerrar");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    digitarNaBusca("logotipo");
    await waitFor(() => expect(pendentes).toHaveLength(3));

    expect(pendentes[1].url).toContain("busca=encerrar");
    expect(pendentes[2].url).toContain("busca=logotipo");
    return pendentes;
  }

  it("a resposta atrasada da busca antiga não repinta a lista da busca nova", async () => {
    // Digitar duas vezes rápido deixa duas leituras no ar. Se a primeira chegar
    // por último, uma tela ingênua mostra o resultado do termo que ninguém está
    // mais procurando, com a caixa escrita com o termo novo: mentira silenciosa,
    // sem erro e sem espera.
    const pendentes = await comDuasBuscasNoAr();

    pendentes[2].responder([LOGOTIPO]);
    await screen.findByText("Trocar o logotipo");
    pendentes[1].responder([ENCERRAR]);
    await deixarOReactProcessar();

    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
    expect(screen.queryByText("Encerrar conversas")).toBeNull();
  });

  it("a resposta da busca antiga que chega PRIMEIRO não desliga a espera", async () => {
    const pendentes = await comDuasBuscasNoAr();

    pendentes[1].responder([ENCERRAR]);
    await deixarOReactProcessar();

    expect(screen.getByText("Carregando o Histórico...")).toBeTruthy();
    expect(screen.queryByText("Encerrar conversas")).toBeNull();

    pendentes[2].responder([LOGOTIPO]);
    expect(await screen.findByText("Trocar o logotipo")).toBeTruthy();
    expect(screen.queryByText("Carregando o Histórico...")).toBeNull();
  });
});
