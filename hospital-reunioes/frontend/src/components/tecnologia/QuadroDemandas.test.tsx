/**
 * @vitest-environment jsdom
 */

/**
 * O Quadro de Demandas (issue #637, PRD #634, ADR 0050).
 *
 * O servidor é falso, mas as REGRAS ficam com ele: a tela não decide se a
 * transição existe nem se o Produto tem dono, ela mostra o que a API
 * respondeu. As asserções olham duas coisas: o que o Super admin vê no card e
 * na coluna, e a chamada que o clique dispara (URL, método e corpo).
 *
 * Armadilhas de teste vazio evitadas aqui:
 *
 * - "a coluna Concluída está recolhida" seria satisfeito por uma tela que não
 *   desenha coluna nenhuma; por isso todo teste de ausência tem irmã de
 *   presença no MESMO render;
 * - "o card mostra o símbolo do tipo" passaria com os sete tipos desenhando o
 *   mesmo ícone; por isso o teste compara os sete desenhos entre si;
 * - "a idade fica vermelha aos 14 dias" passaria com toda idade vermelha; por
 *   isso o mesmo render tem uma de 13 dias que não pode estar.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuadroDemandas } from "./QuadroDemandas";
import { Demanda, EstadoDemanda, PrioridadeDemanda, TipoDemanda, TIPOS } from "./demandas";

type Chamada = { url: string; metodo: string; corpo: unknown };

const PRODUTOS = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
  { id: "prod-3", nome: "Site antigo", ativo: false },
];

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

/** Quantos dias atrás, em texto ISO com hora, como o backend devolve. */
function diasAtras(dias: number): string {
  return new Date(Date.now() - dias * 86_400_000).toISOString();
}

/** Uma data (sem hora), no fuso de quem está olhando a tela. */
function dataEm(dias: number): string {
  const d = new Date(Date.now() + dias * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function demanda(id: string, titulo: string, extra: Partial<Demanda> = {}): Demanda {
  return {
    id,
    titulo,
    descricao: null,
    tipo: "decisao" as TipoDemanda,
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova" as EstadoDemanda,
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P1",
    prioridade: "normal" as PrioridadeDemanda,
    prazo: null,
    criado_em: diasAtras(1),
    concluida_em: null,
    cancelada_em: null,
    ...extra,
  };
}

let chamadas: Chamada[] = [];

function montar(
  demandas: Demanda[],
  opcoes: {
    conversa?: unknown[];
    recusa?: { status: number; detail: string };
    // A rede CAI: o `fetch` rejeita, em vez de responder com status de erro.
    redeFora?: "carregar" | "salvar";
    token?: string | null;
  } = {},
) {
  chamadas = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });

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

      const corpo = url.includes("/conversa") ? (opcoes.conversa ?? []) : demandas;
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  render(
    <QuadroDemandas
      token={opcoes.token === undefined ? "token-de-teste" : opcoes.token}
      produtos={PRODUTOS}
      pessoas={PESSOAS}
    />,
  );
}

const escritas = () => chamadas.filter((c) => c.metodo !== "GET");
const colunaDe = (nome: string) => screen.getByRole("region", { name: nome });
const cardDe = (titulo: string) => screen.getByText(titulo).closest("li")!;

beforeEach(() => {
  chamadas = [];
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("As cinco colunas", () => {
  it("desenha as cinco, cada uma com o seu contador", async () => {
    montar([
      demanda("d1", "Uma nova"),
      demanda("d2", "Outra nova"),
      demanda("d3", "Em curso", { estado: "em_andamento" }),
      demanda("d4", "Fechada", { estado: "concluida" }),
    ]);

    await screen.findByText("Uma nova");
    for (const nome of ["Nova", "Em andamento", "Aguardando", "Concluída", "Cancelada"]) {
      expect(colunaDe(nome)).toBeTruthy();
    }
    expect(within(colunaDe("Nova")).getByText("2")).toBeTruthy();
    expect(within(colunaDe("Em andamento")).getByText("1")).toBeTruthy();
    expect(within(colunaDe("Aguardando")).getByText("0")).toBeTruthy();
    expect(within(colunaDe("Concluída")).getByText("1")).toBeTruthy();
  });

  it("Concluída e Cancelada nascem recolhidas, com o contador à vista", async () => {
    montar([
      demanda("d1", "Uma nova"),
      demanda("d2", "Fechada", { estado: "concluida" }),
      demanda("d3", "Desistimos", { estado: "cancelada" }),
    ]);

    // A irmã de presença: a coluna viva mostra o card no mesmo render, então
    // "não aparece" abaixo significa recolhida, e não tela vazia.
    expect(await screen.findByText("Uma nova")).toBeTruthy();
    expect(screen.queryByText("Fechada")).toBeNull();
    expect(screen.queryByText("Desistimos")).toBeNull();

    // Recolhida não é escondida: o contador continua dizendo quantas são.
    expect(within(colunaDe("Concluída")).getByText("1")).toBeTruthy();
    expect(within(colunaDe("Cancelada")).getByText("1")).toBeTruthy();
  });

  it("a coluna recolhida abre ao clicar", async () => {
    montar([demanda("d2", "Fechada", { estado: "concluida" })]);

    await screen.findByRole("region", { name: "Concluída" });
    const cabecalho = within(colunaDe("Concluída")).getByRole("button");
    expect(cabecalho.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(cabecalho);

    expect(await screen.findByText("Fechada")).toBeTruthy();
    expect(cabecalho.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("O card", () => {
  it("mostra símbolo do tipo, título, Produto, responsável, prioridade e idade", async () => {
    montar([
      demanda("d1", "Encerrar conversas", {
        tipo: "decisao",
        produto_nome: "Ana",
        responsavel_nome: "Sócia Vitta",
        prioridade: "alta",
        criado_em: diasAtras(3),
      }),
    ]);

    await screen.findByText("Encerrar conversas");
    const card = cardDe("Encerrar conversas");
    expect(within(card).getByRole("img", { name: "Decisão" })).toBeTruthy();
    expect(within(card).getByText("Ana")).toBeTruthy();
    expect(within(card).getByText("Sócia Vitta")).toBeTruthy();
    expect(within(card).getByText("Alta")).toBeTruthy();
    expect(within(card).getByText("há 3 dias")).toBeTruthy();
  });

  it("os sete tipos desenham sete símbolos diferentes", async () => {
    // Um mapa que devolvesse o mesmo ícone para todos passaria no teste acima,
    // porque o nome acessível vem do rótulo do tipo, não do desenho.
    montar(TIPOS.map((tipo, i) => demanda(`d${i}`, `Demanda ${tipo}`, { tipo })));

    await screen.findByText("Demanda decisao");
    const desenhos = TIPOS.map((tipo) => {
      const rotulo = { decisao: "Decisão", informacao: "Informação", terceiro: "Terceiro", ajuste: "Ajuste", novo: "Novo", defeito: "Defeito", consultoria: "Consultoria" }[tipo];
      return screen.getByRole("img", { name: rotulo }).innerHTML;
    });

    expect(new Set(desenhos).size).toBe(7);
  });

  it("a idade fica vermelha a partir de 14 dias, e não antes", async () => {
    montar([
      demanda("d1", "Envelheceu", { criado_em: diasAtras(14) }),
      demanda("d2", "Ainda nova", { criado_em: diasAtras(13) }),
    ]);

    await screen.findByText("Envelheceu");
    expect(within(cardDe("Envelheceu")).getByText("há 14 dias").className).toContain("text-red-600");
    expect(within(cardDe("Ainda nova")).getByText("há 13 dias").className).not.toContain("text-red-600");
  });

  it("o prazo vencido marca atrasada; sem prazo o card só envelhece", async () => {
    montar([
      demanda("d1", "Passou do prazo", { prazo: dataEm(-1) }),
      demanda("d2", "Vence amanhã", { prazo: dataEm(1) }),
      demanda("d3", "Sem prazo nenhum", { prazo: null, criado_em: diasAtras(30) }),
    ]);

    await screen.findByText("Passou do prazo");
    expect(within(cardDe("Passou do prazo")).getByText(/Atrasada desde/)).toBeTruthy();
    expect(within(cardDe("Vence amanhã")).queryByText(/Atrasada/)).toBeNull();

    // Velha não é atrasada: sem prazo, o card envelhece e não atrasa.
    const semPrazo = cardDe("Sem prazo nenhum");
    expect(within(semPrazo).queryByText(/Atrasada/)).toBeNull();
    expect(within(semPrazo).getByText("há 30 dias")).toBeTruthy();
  });
});

describe("Abrir uma Demanda", () => {
  async function abrirFormulario() {
    fireEvent.click(await screen.findByRole("button", { name: /Nova Demanda/ }));
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Encerrar conversas" } });
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
  }

  it("manda título, tipo, Produto e prioridade Normal por padrão", async () => {
    montar([]);
    await abrirFormulario();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas",
      metodo: "POST",
      // Sem estado nem responsável: quem decide os dois é o backend, pelo
      // Produto (a Demanda nasce em Nova, com o dono).
      corpo: {
        titulo: "Encerrar conversas",
        tipo: "decisao",
        produto_id: "prod-1",
        prioridade: "normal",
        descricao: "",
      },
    });
  });

  it("só oferece Produto ativo", async () => {
    montar([]);
    fireEvent.click(await screen.findByRole("button", { name: /Nova Demanda/ }));
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Ana", "POPs"]);
  });

  it("a recusa do servidor chega ao Super admin", async () => {
    const motivo = "Produto sem dono nao recebe Demanda nova: ela nasceria sem responsavel.";
    montar([], { recusa: { status: 422, detail: motivo } });
    await abrirFormulario();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Produto sem dono");
  });

  it("sem recusa, nenhum aviso aparece", async () => {
    // O par de presença do teste acima: um `role="alert"` cravado na tela
    // passaria naquele sozinho.
    montar([]);
    await abrirFormulario();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Mover pelo card", () => {
  it("de Nova oferece os quatro destinos, e nenhum deles é Nova", async () => {
    montar([demanda("d1", "Uma nova", { estado: "nova" })]);

    fireEvent.click(await screen.findByRole("button", { name: "Mover Uma nova" }));

    const card = cardDe("Uma nova");
    for (const destino of ["Em andamento", "Aguardando", "Concluída", "Cancelada"]) {
      expect(within(card).getByRole("button", { name: destino })).toBeTruthy();
    }
    // A tela não oferece o caminho que o backend recusaria: ninguém volta a Nova.
    expect(within(card).queryByRole("button", { name: "Nova" })).toBeNull();
  });

  it("de Concluída o único destino é reabrir em Em andamento", async () => {
    montar([demanda("d1", "Fechada", { estado: "concluida" })]);

    await screen.findByRole("region", { name: "Concluída" });
    fireEvent.click(within(colunaDe("Concluída")).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "Mover Fechada" }));

    const card = cardDe("Fechada");
    expect(within(card).getByRole("button", { name: "Em andamento" })).toBeTruthy();
    for (const proibido of ["Nova", "Aguardando", "Cancelada"]) {
      expect(within(card).queryByRole("button", { name: proibido })).toBeNull();
    }
  });

  it("clicar no destino chama a rota de mover com o estado escolhido", async () => {
    montar([demanda("d1", "Uma nova", { estado: "nova" })]);

    fireEvent.click(await screen.findByRole("button", { name: "Mover Uma nova" }));
    fireEvent.click(within(cardDe("Uma nova")).getByRole("button", { name: "Aguardando" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/mover",
      metodo: "POST",
      corpo: { estado: "aguardando" },
    });
  });

  it("a recusa da transição aparece com a frase do servidor", async () => {
    montar([demanda("d1", "Uma nova")], {
      recusa: { status: 422, detail: "A Demanda já está em Nova." },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Mover Uma nova" }));
    fireEvent.click(within(cardDe("Uma nova")).getByRole("button", { name: "Aguardando" }));

    expect((await screen.findByRole("alert")).textContent).toContain("A Demanda já está em Nova.");
  });
});

describe("O modal da Demanda", () => {
  const CONVERSA = [
    {
      id: "c1",
      autor_id: "P2",
      autor_nome: "Sócia Vitta",
      linha: "resposta",
      texto: "Vou olhar hoje",
      movimento_campo: null,
      criado_em: "2026-09-01T12:00:00Z",
    },
    {
      id: "c2",
      autor_id: null,
      autor_nome: null,
      linha: "movimento",
      texto: "Pedro Vitta moveu para Aguardando",
      movimento_campo: "estado",
      criado_em: "2026-09-02T12:00:00Z",
    },
  ];

  async function abrirModal(extra: Partial<Demanda> = {}) {
    montar([demanda("d1", "Encerrar conversas", extra)], { conversa: CONVERSA });
    // O título do card é o que abre o modal (o clique sobe para o botão).
    fireEvent.click(await screen.findByText("Encerrar conversas"));
    return await screen.findByRole("dialog");
  }

  it("lista a Conversa em ordem cronológica, com autor, data e hora", async () => {
    const modal = await abrirModal();

    const linhas = await within(modal).findAllByRole("listitem");
    expect(linhas[0].textContent).toContain("Sócia Vitta");
    expect(linhas[0].textContent).toContain("Vou olhar hoje");
    expect(linhas[0].textContent).toContain("01/09/2026");
    expect(linhas[1].textContent).toContain("Pedro Vitta moveu para Aguardando");
    expect(linhas[1].textContent).toContain("02/09/2026");
  });

  it("salva os campos editáveis numa chamada só", async () => {
    const modal = await abrirModal({ prazo: "2026-10-01" });

    fireEvent.change(within(modal).getByLabelText("Título"), { target: { value: "Título novo" } });
    fireEvent.change(within(modal).getByLabelText("Descrição"), { target: { value: "Contexto" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar/ }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1",
      metodo: "PATCH",
      corpo: {
        titulo: "Título novo",
        descricao: "Contexto",
        tipo: "decisao",
        produto_id: "prod-1",
        prioridade: "normal",
        prazo: "2026-10-01",
      },
    });
  });

  it("apagar o prazo manda null, e não texto vazio", async () => {
    // `""` numa coluna DATE é erro de banco, não "sem prazo".
    const modal = await abrirModal({ prazo: "2026-10-01" });

    fireEvent.change(within(modal).getByLabelText("Prazo"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar/ }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect((escritas()[0].corpo as { prazo: unknown }).prazo).toBeNull();
  });

  it("trocar o responsável usa a porta de atribuir, entre as pessoas da aba", async () => {
    const modal = await abrirModal();

    fireEvent.click(within(modal).getByRole("combobox", { name: "Responsável" }));
    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Pedro Vitta", "Sócia Vitta"]);

    fireEvent.click(within(screen.getByRole("listbox")).getByText("Sócia Vitta"));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/atribuir",
      metodo: "POST",
      corpo: { responsavel_id: "P2" },
    });
  });

  it("mover pelo modal usa a mesma porta do card", async () => {
    const modal = await abrirModal({ estado: "aguardando" });

    fireEvent.click(within(modal).getByRole("button", { name: "Em andamento" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/mover",
      metodo: "POST",
      corpo: { estado: "em_andamento" },
    });
  });
});

describe("A falha de rede não vira quadro vazio e calado", () => {
  it("backend fora do ar: a tela avisa, em vez de mostrar cinco colunas zeradas", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([demanda("d1", "Uma nova")], { redeFora: "carregar" });

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
    expect(screen.queryByText("Carregando Demandas...")).toBeNull();
  });

  it("com servidor de pé, a espera termina, os cards aparecem e não há aviso", async () => {
    // O par de presença do teste acima: sem ele, uma tela que nunca mostrasse
    // "Carregando Demandas..." passaria nos dois.
    montar([demanda("d1", "Uma nova")]);

    expect(screen.getByText("Carregando Demandas...")).toBeTruthy();
    expect(await screen.findByText("Uma nova")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
