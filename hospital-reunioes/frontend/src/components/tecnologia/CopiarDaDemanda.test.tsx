/**
 * @vitest-environment jsdom
 */

/**
 * Os dois botões de copiar do modal (issue #640, PRD #634, ADR 0050).
 *
 * O que se prova aqui é o que o Super admin leva embora: o texto que sai da
 * API, sem uma segunda montagem na tela, e o endereço que a própria aplicação
 * sabe abrir.
 *
 * Armadilhas de teste vazio evitadas:
 *
 * - "escreveu no clipboard" passaria com a tela escrevendo qualquer coisa; por
 *   isso a asserção compara com o texto EXATO que o servidor falso respondeu, e
 *   esse texto tem uma marca que a tela não teria como inventar;
 * - "quando a cópia falha aparece um aviso" passaria com um aviso que não
 *   entrega o texto; por isso o mesmo teste procura o texto na caixa de pegar à
 *   mão, que é a saída que a pessoa tem;
 * - o clipboard some de duas maneiras diferentes (a API não existe no contexto,
 *   e a API existe mas nega), e as duas têm teste, porque no código são dois
 *   caminhos.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopiarDaDemanda } from "./CopiarDaDemanda";
import { Demanda } from "./demandas";

const TEXTO_DA_API =
  "Este é um pedido de tecnologia registrado no aplicativo do hospital.\n\nTítulo: Encerrar conversas da Ana";

const DEMANDA: Demanda = {
  id: "d1",
  titulo: "Encerrar conversas da Ana",
  descricao: null,
  tipo: "decisao",
  produto_id: "prod-1",
  produto_nome: "Ana",
  estado: "nova",
  responsavel_id: "P1",
  responsavel_nome: "Pedro Vitta",
  autor_id: "P1",
  prioridade: "normal",
  prazo: null,
  criado_em: "2026-09-01T13:00:00Z",
  concluida_em: null,
  cancelada_em: null,
};

type Chamada = { url: string; metodo: string };

let chamadas: Chamada[] = [];
let copiado: string[] = [];

function montar(
  opcoes: {
    texto?: string;
    recusa?: number;
    redeFora?: boolean;
    // Como o clipboard falha: `ausente` é o contexto sem a API (http, iframe
    // sem permissão), `negado` é a API existindo e recusando.
    clipboard?: "ok" | "ausente" | "negado";
  } = {},
) {
  chamadas = [];
  copiado = [];

  // Os caminhos de falha logam no console de propósito (o padrão da aba). O
  // silêncio aqui é só para a saída do teste não virar um muro de stack trace.
  if (opcoes.redeFora || (opcoes.clipboard ?? "ok") !== "ok") {
    vi.spyOn(console, "error").mockImplementation(() => {});
  }

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, metodo: init?.method ?? "GET" });
      if (opcoes.redeFora) throw new TypeError("Failed to fetch");
      if (opcoes.recusa) {
        return { ok: false, status: opcoes.recusa, json: async () => ({}) } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ texto: opcoes.texto ?? TEXTO_DA_API }),
      } as unknown as Response;
    }),
  );

  const modo = opcoes.clipboard ?? "ok";
  if (modo === "ausente") {
    Object.defineProperty(window.navigator, "clipboard", { value: undefined, configurable: true });
  } else {
    Object.defineProperty(window.navigator, "clipboard", {
      value: {
        writeText: vi.fn(async (texto: string) => {
          if (modo === "negado") throw new Error("NotAllowedError");
          copiado.push(texto);
        }),
      },
      configurable: true,
    });
  }

  render(<CopiarDaDemanda demanda={DEMANDA} token="token-de-teste" />);
}

const botao = (nome: string) => screen.getByRole("button", { name: nome });

beforeEach(() => {
  chamadas = [];
  copiado = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Copiar para IA", () => {
  it("escreve no clipboard exatamente o texto que a API devolveu", async () => {
    montar();

    fireEvent.click(botao("Copiar para IA"));

    await waitFor(() => expect(copiado).toEqual([TEXTO_DA_API]));
    expect(chamadas).toEqual([{ url: "/api/admin/tecnologia/demandas/d1/texto-para-ia", metodo: "GET" }]);
  });

  it("a tela não monta o texto por conta própria", async () => {
    // O texto do servidor falso é outro de propósito: se a tela montasse o
    // texto sozinha (título, tipo, Produto), o clipboard levaria a versão dela
    // e não a da API, que é a fonte única.
    montar({ texto: "TEXTO QUE SÓ O SERVIDOR SABE" });

    fireEvent.click(botao("Copiar para IA"));

    await waitFor(() => expect(copiado).toEqual(["TEXTO QUE SÓ O SERVIDOR SABE"]));
  });

  it("diz que copiou, para o clique não ficar sem resposta", async () => {
    montar();

    fireEvent.click(botao("Copiar para IA"));

    expect((await screen.findByRole("status")).textContent).toContain("copiado");
  });

  it("a API recusa: avisa e não finge que copiou", async () => {
    montar({ recusa: 500 });

    fireEvent.click(botao("Copiar para IA"));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível montar o texto");
    expect(copiado).toEqual([]);
    // Irmã de presença: o aviso de sucesso não está na tela no mesmo render.
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a rede cai: avisa com a frase de conexão da aba", async () => {
    montar({ redeFora: true });

    fireEvent.click(botao("Copiar para IA"));

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    expect(copiado).toEqual([]);
  });
});

describe("Copiar link", () => {
  it("escreve a URL da Demanda, com o id, no clipboard", async () => {
    montar();

    fireEvent.click(botao("Copiar link"));

    await waitFor(() => expect(copiado).toEqual([`${window.location.origin}/admin/tecnologia?demanda=d1`]));
  });

  it("copiar o link não pede nada à API", async () => {
    montar();

    fireEvent.click(botao("Copiar link"));

    await waitFor(() => expect(copiado.length).toBe(1));
    expect(chamadas).toEqual([]);
  });
});

describe("Quando o navegador não deixa copiar", () => {
  it("sem a API de clipboard, o texto vai para uma caixa de onde dá para copiar à mão", async () => {
    montar({ clipboard: "ausente" });

    fireEvent.click(botao("Copiar para IA"));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("não liberou a cópia automática");
    // A saída de verdade: o texto está na tela, inteiro, para selecionar.
    const caixa = screen.getByLabelText("Texto para copiar à mão") as HTMLTextAreaElement;
    expect(caixa.value).toBe(TEXTO_DA_API);
  });

  it("com a cópia negada pelo navegador, a saída é a mesma", async () => {
    montar({ clipboard: "negado" });

    fireEvent.click(botao("Copiar para IA"));

    await screen.findByRole("alert");
    expect((screen.getByLabelText("Texto para copiar à mão") as HTMLTextAreaElement).value).toBe(TEXTO_DA_API);
  });

  it("o link também cai na caixa, e não some em silêncio", async () => {
    montar({ clipboard: "negado" });

    fireEvent.click(botao("Copiar link"));

    await screen.findByRole("alert");
    expect((screen.getByLabelText("Texto para copiar à mão") as HTMLTextAreaElement).value).toBe(
      `${window.location.origin}/admin/tecnologia?demanda=d1`,
    );
  });

  it("com o clipboard funcionando, a caixa de pegar à mão não aparece", async () => {
    // Irmã de presença dos três testes acima: a caixa é a saída da falha, e
    // não um pedaço fixo da tela.
    montar();

    fireEvent.click(botao("Copiar para IA"));

    await waitFor(() => expect(copiado.length).toBe(1));
    expect(screen.queryByLabelText("Texto para copiar à mão")).toBeNull();
  });

  it("a caixa some quando a cópia seguinte funciona", async () => {
    montar({ clipboard: "negado" });

    fireEvent.click(botao("Copiar link"));
    await screen.findByLabelText("Texto para copiar à mão");

    // O navegador volta a deixar copiar (a pessoa concedeu a permissão).
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: vi.fn(async (texto: string) => void copiado.push(texto)) },
      configurable: true,
    });
    fireEvent.click(botao("Copiar link"));

    await waitFor(() => expect(copiado.length).toBe(1));
    expect(screen.queryByLabelText("Texto para copiar à mão")).toBeNull();
  });
});


describe("Uma ação começa do zero (rodada 1 de fix)", () => {
  it("a caixa da ação anterior não sobrevive à falha da ação seguinte", async () => {
    // O pior caso que o revisor rodou: o clipboard está negado, a pessoa copia
    // o link (a caixa aparece com ele), e a busca do texto para a IA falha
    // depois. Sem zerar, a tela fica com o aviso "não foi possível montar o
    // texto" e, logo abaixo, o LINK numa caixa que diz "para copiar à mão".
    montar({ clipboard: "negado", recusa: 500 });

    fireEvent.click(botao("Copiar link"));
    const caixa = await screen.findByLabelText("Texto para copiar à mão");
    expect((caixa as HTMLTextAreaElement).value).toContain("?demanda=d1");

    fireEvent.click(botao("Copiar para IA"));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível montar o texto");
    // O par: o aviso está na tela no MESMO render em que a caixa não está.
    expect(screen.queryByLabelText("Texto para copiar à mão")).toBeNull();
  });

  it("o aviso de sucesso da ação anterior também sai da tela", async () => {
    montar({ recusa: 500 });

    fireEvent.click(botao("Copiar link"));
    expect((await screen.findByRole("status")).textContent).toContain("copiado");

    fireEvent.click(botao("Copiar para IA"));

    await screen.findByRole("alert");
    // Sem zerar, a tela diria "Link da Demanda copiado." e "não foi possível
    // montar o texto" ao mesmo tempo, e as duas frases falam de ações
    // diferentes sem dizer qual é qual.
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a caixa velha sai da tela enquanto o navegador ainda decide sobre a cópia", async () => {
    // O `writeText` fica PENDENTE enquanto o navegador pergunta à pessoa se
    // libera a área de transferência, e isso são segundos. Nesse intervalo a
    // caixa da ação anterior não pode continuar na tela oferecendo o texto de
    // antes: quem clicou já mudou de ação.
    montar({ clipboard: "negado" });

    fireEvent.click(botao("Copiar para IA"));
    expect((await screen.findByLabelText("Texto para copiar à mão")).textContent).toContain("Título");

    let liberar: (() => void) | null = null;
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: vi.fn(() => new Promise<void>((resolve) => (liberar = () => resolve()))) },
      configurable: true,
    });

    fireEvent.click(botao("Copiar link"));

    await waitFor(() => expect(screen.queryByLabelText("Texto para copiar à mão")).toBeNull());
    // Par de presença: a cópia ainda NÃO terminou (ninguém resolveu a promessa),
    // então a caixa sumiu por causa do começo da ação, e não do fim dela.
    expect(liberar).not.toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("A tela diz para onde o texto vai", () => {
  it("avisa que o texto sai do app antes de a pessoa colar", async () => {
    montar();

    const marca = screen.getByText(/sai do app e vai para uma IA de fora/);

    expect(marca).toBeTruthy();
  });
});
