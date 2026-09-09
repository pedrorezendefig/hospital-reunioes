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

import { useState } from "react";
import { act, cleanup, createEvent, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuadroDemandas } from "./QuadroDemandas";
import {
  Demanda,
  EstadoDemanda,
  FiltrosDoQuadro,
  linkDaDemanda,
  PrioridadeDemanda,
  SEM_FILTRO,
  TipoDemanda,
  TIPOS,
} from "./demandas";

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
    // São caminhos diferentes no componente (carregar, salvar e a leitura da
    // Conversa dentro do modal), por isso três valores.
    redeFora?: "carregar" | "salvar" | "conversa";
    token?: string | null;
    // O estado de BOOT do `useAuth`: token ainda nulo porque a autenticação
    // não terminou, e não porque não há sessão.
    carregandoAuth?: boolean;
  } = {},
) {
  chamadas = [];

  /**
   * O fio como o servidor o guarda: escrever nele muda o que a leitura
   * seguinte devolve.
   *
   * Sem isso, "a resposta aparece no fio sem recarregar a página" passaria com
   * um componente que nem recarrega a Conversa, porque a lista devolvida seria
   * sempre a mesma.
   */
  const fio: Record<string, unknown>[] = [...((opcoes.conversa ?? []) as Record<string, unknown>[])];

  /**
   * O Quadro como o servidor o guarda: mover uma Demanda muda a coluna em que
   * a leitura seguinte a devolve.
   *
   * Sem isso, "o card fica na coluna nova" e "o card volta para a origem"
   * seriam a MESMA tela (a lista devolvida seria sempre a de partida), e o
   * teste da recusa passaria sobre um componente que move o card na hora e
   * ignora o 409.
   */
  const quadro: Demanda[] = demandas.map((d) => ({ ...d }));

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpoEnviado = init?.body ? JSON.parse(String(init.body)) : null;
      chamadas.push({ url, metodo, corpo: corpoEnviado });

      if (
        (opcoes.redeFora === "carregar" && metodo === "GET") ||
        (opcoes.redeFora === "salvar" && metodo !== "GET") ||
        (opcoes.redeFora === "conversa" && metodo === "GET" && url.includes("/conversa"))
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
        // Quem está logado no dublê é o P1: a resposta nova nasce dele e volta
        // com a janela de 10 minutos aberta, como o backend faz.
        if (metodo === "POST" && url.endsWith("/conversa")) {
          const nova = {
            id: `c-nova-${fio.length}`,
            autor_id: "P1",
            autor_nome: "Pedro Vitta",
            linha: "resposta",
            texto: corpoEnviado.texto,
            mencoes: corpoEnviado.mencoes ?? [],
            movimento_campo: null,
            criado_em: new Date().toISOString(),
            editado_em: null,
            editavel_ate: new Date(Date.now() + 600_000).toISOString(),
          };
          fio.push(nova);
          return { ok: true, status: 201, json: async () => nova } as unknown as Response;
        }
        if (metodo === "POST" && url.endsWith("/mover")) {
          const alvo = quadro.find((d) => url.endsWith(`/demandas/${d.id}/mover`));
          if (alvo) alvo.estado = corpoEnviado.estado;
          return { ok: true, status: 200, json: async () => alvo ?? {} } as unknown as Response;
        }
        if (metodo === "PATCH" && url.includes("/conversa/")) {
          const alvo = fio.find((linha) => url.endsWith(`/${linha.id}`));
          if (alvo) {
            alvo.texto = corpoEnviado.texto;
            alvo.mencoes = corpoEnviado.mencoes ?? [];
            alvo.editado_em = new Date().toISOString();
          }
          return { ok: true, status: 200, json: async () => alvo ?? {} } as unknown as Response;
        }
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }

      if (url.includes("/conversa")) {
        return { ok: true, status: 200, json: async () => fio } as unknown as Response;
      }

      // Os filtros são do SERVIDOR, como no backend: uma tela que peneirasse
      // os cards por conta própria receberia tudo aqui e mostraria tudo.
      const busca = new URLSearchParams(url.split("?")[1] ?? "");
      const casa = (chave: string, valor: string | null) => !busca.get(chave) || busca.get(chave) === valor;
      const corpo = quadro.filter(
        (d) =>
          casa("tipo", d.tipo) && casa("produto_id", d.produto_id) && casa("responsavel_id", d.responsavel_id),
      );
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  /**
   * O dono do estado dos filtros, no lugar do módulo.
   *
   * O Quadro não guarda os filtros: quem guarda é a aba Tecnologia, para eles
   * sobreviverem à troca de aba (issue #639). Aqui o anfitrião faz esse papel.
   */
  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <QuadroDemandas
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

  it("o campo Título não deixa passar de 200 caracteres", async () => {
    // O backend recusa com frase de gente, mas quem cola um texto longo tem
    // que ser barrado antes de clicar: é o limite do campo que evita a viagem.
    montar([]);
    fireEvent.click(await screen.findByRole("button", { name: /Nova Demanda/ }));

    expect((screen.getByLabelText("Título") as HTMLInputElement).maxLength).toBe(200);
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
      mencoes: [],
      movimento_campo: null,
      criado_em: "2026-09-01T12:00:00Z",
      editado_em: null,
      editavel_ate: null,
    },
    {
      id: "c2",
      autor_id: null,
      autor_nome: null,
      linha: "movimento",
      texto: "Pedro Vitta moveu para Aguardando",
      mencoes: [],
      movimento_campo: "estado",
      criado_em: "2026-09-02T12:00:00Z",
      editado_em: null,
      editavel_ate: null,
    },
  ];

  async function abrirModal(
    extra: Partial<Demanda> = {},
    opcoes: Parameters<typeof montar>[1] = {},
  ) {
    montar([demanda("d1", "Encerrar conversas", extra)], { conversa: CONVERSA, ...opcoes });
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

  it("o campo Título do modal também para nos 200 caracteres", async () => {
    const modal = await abrirModal();

    expect((within(modal).getByLabelText("Título") as HTMLInputElement).maxLength).toBe(200);
  });

  it("com o Título apagado, o Salvar fica desabilitado", async () => {
    // Por cima da guarda do backend, não no lugar dela: a API recusa `""` com
    // frase de gente. Aqui só se evita o clique que já se sabe recusado.
    const modal = await abrirModal();
    const salvar = screen.getByRole("button", { name: /Salvar/ }) as HTMLButtonElement;

    // O par de presença: com título, o botão está de pé no mesmo render.
    expect(salvar.disabled).toBe(false);

    fireEvent.change(within(modal).getByLabelText("Título"), { target: { value: "   " } });

    expect(salvar.disabled).toBe(true);
  });

  it("o responsável que perdeu o acesso à aba continua à vista no seletor", async () => {
    // Dado antigo existe: a recusa nova na criação não apaga quem já está
    // gravado. Sem a opção extra, o `Select` da casa cai no placeholder e o
    // modal diria "Sem responsável" enquanto o card mostra o nome.
    const modal = await abrirModal({ responsavel_id: "P9", responsavel_nome: "Saiu da Vitta" });

    const seletor = within(modal).getByRole("combobox", { name: "Responsável" });
    expect(seletor.textContent).toContain("Saiu da Vitta");
    expect(seletor.textContent).not.toContain("Sem responsável");
  });

  it("o responsável que está na lista aparece pelo nome, sem marca de sem acesso", async () => {
    // O par de presença do teste acima: uma opção extra cravada marcaria todo
    // mundo como fora da aba.
    const modal = await abrirModal({ responsavel_id: "P1", responsavel_nome: "Pedro Vitta" });

    const seletor = within(modal).getByRole("combobox", { name: "Responsável" });
    expect(seletor.textContent).toContain("Pedro Vitta");
    expect(seletor.textContent).not.toContain("sem acesso à aba");
  });

  it("rede fora ao salvar: o modal avisa", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const modal = await abrirModal({}, { redeFora: "salvar" });

    fireEvent.change(within(modal).getByLabelText("Título"), { target: { value: "Título novo" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar/ }));

    const aviso = await within(modal).findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
  });

  it("rede fora ao ler a Conversa: o modal avisa, em vez de mostrar fio vazio", async () => {
    // Sem o `catch` do `carregarConversa`, o modal mostraria "Nada aconteceu
    // nesta Demanda ainda", que é o contrário do que houve.
    vi.spyOn(console, "error").mockImplementation(() => {});
    const modal = await abrirModal({}, { redeFora: "conversa" });

    const aviso = await within(modal).findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
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

  it("rede fora ao mover: o clique avisa, em vez de não fazer nada", async () => {
    // O `catch` do caminho de ESCRITA. Sem ele, o clique em Mover com a rede
    // fora quebraria a promise sem alerta nenhum, e o card ficaria na coluna
    // antiga sem explicação.
    vi.spyOn(console, "error").mockImplementation(() => {});
    montar([demanda("d1", "Uma nova")], { redeFora: "salvar" });

    fireEvent.click(await screen.findByRole("button", { name: "Mover Uma nova" }));
    fireEvent.click(within(cardDe("Uma nova")).getByRole("button", { name: "Aguardando" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
  });

  it("sem sessão, o Quadro diz o que houve em vez de mostrar colunas zeradas", async () => {
    // `carregar` desiste na primeira linha quando não há token. Sem aviso, o
    // Quadro desenha Nova 0, Em andamento 0, Aguardando 0, indistinguível de
    // "não há Demanda nenhuma". O aviso do módulo não cobre este caso: ele
    // fala de Produtos e mora abaixo do tabpanel do Quadro.
    //
    // A frase é a das DUAS causas de propósito: o `useAuth` devolve
    // `token: null` tanto com a sessão acabada quanto com o `getUser()` dele
    // falhando por rede, e o componente não distingue.
    montar([demanda("d1", "Uma nova")], { token: null });

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("a sessão não está ativa ou o servidor não respondeu");
    expect(aviso.textContent).toContain("Tente recarregar a página");
    expect(screen.queryByText("Carregando Demandas...")).toBeNull();
    // E não fingiu que buscou: nenhuma chamada saiu.
    expect(chamadas).toHaveLength(0);
  });

  it("enquanto a autenticação carrega, o token nulo não vira aviso de sessão", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }`. Ler esse nulo
    // como "não há sessão" pintaria o alerta vermelho em toda abertura da aba,
    // com a sessão válida, e ele sumiria sozinho quando o token chegasse.
    // O par de presença é o teste seguinte: resolvida a autenticação, o mesmo
    // token nulo TEM que avisar.
    montar([demanda("d1", "Uma nova")], { token: null, carregandoAuth: true });

    expect(screen.getByText("Carregando Demandas...")).toBeTruthy();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    expect(chamadas).toHaveLength(0);
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

describe("A Conversa dentro do card", () => {
  /** Uma linha do fio como o backend a devolve. */
  function linhaDoFio(id: string, extra: Record<string, unknown> = {}) {
    return {
      id,
      autor_id: "P1",
      autor_nome: "Pedro Vitta",
      linha: "resposta",
      texto: "Vou olhar hoje",
      mencoes: [],
      movimento_campo: null,
      criado_em: "2026-09-01T12:00:00Z",
      editado_em: null,
      editavel_ate: null,
      ...extra,
    };
  }

  /** O instante que o backend manda quando a janela ainda está aberta. */
  const daTempo = () => new Date(Date.now() + 300_000).toISOString();
  /** E o que ele manda quando ela já fechou. */
  const tardeDemais = () => new Date(Date.now() - 60_000).toISOString();

  async function abrirCom(fio: unknown[], opcoes: Parameters<typeof montar>[1] = {}) {
    montar([demanda("d1", "Encerrar conversas")], { conversa: fio, ...opcoes });
    fireEvent.click(await screen.findByText("Encerrar conversas"));
    return await screen.findByRole("dialog");
  }

  const caixa = (modal: HTMLElement) => within(modal).getByLabelText("Resposta");
  const botaoResponder = (modal: HTMLElement) =>
    within(modal).getByRole("button", { name: /Responder/ }) as HTMLButtonElement;

  it("enviar a resposta grava a linha e ela aparece no fio sem recarregar a página", async () => {
    const modal = await abrirCom([]);

    fireEvent.change(caixa(modal), { target: { value: "Já pedi à Global Health" } });
    fireEvent.click(botaoResponder(modal));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/conversa",
      metodo: "POST",
      corpo: { texto: "Já pedi à Global Health", mencoes: [] },
    });
    // O fio recarregado mostra a linha nova, com o autor e a hora.
    const linha = await within(modal).findByText(/Já pedi à Global Health/);
    expect(linha.closest("li")!.textContent).toContain("Pedro Vitta");
  });

  it("a caixa esvazia depois do envio, para a resposta não sair duplicada", async () => {
    const modal = await abrirCom([]);

    fireEvent.change(caixa(modal), { target: { value: "Respondido" } });
    fireEvent.click(botaoResponder(modal));

    await waitFor(() => expect((caixa(modal) as HTMLTextAreaElement).value).toBe(""));
  });

  it("com a caixa vazia o botão Responder fica desabilitado", async () => {
    const modal = await abrirCom([]);

    // Par de presença: com texto, o mesmo botão está de pé no mesmo render.
    fireEvent.change(caixa(modal), { target: { value: "Tem texto" } });
    expect(botaoResponder(modal).disabled).toBe(false);

    fireEvent.change(caixa(modal), { target: { value: "   " } });
    expect(botaoResponder(modal).disabled).toBe(true);
  });

  it("o @ lista só as pessoas com acesso à aba, e a escolhida vira menção na linha", async () => {
    const modal = await abrirCom([]);

    fireEvent.change(caixa(modal), { target: { value: "Oi @" } });
    const lista = await within(modal).findByRole("list", { name: "Pessoas para mencionar" });
    expect(within(lista).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Pedro Vitta",
      "Sócia Vitta",
    ]);

    fireEvent.click(within(lista).getByRole("button", { name: "Sócia Vitta" }));
    expect((caixa(modal) as HTMLTextAreaElement).value).toBe("Oi @Sócia Vitta ");

    fireEvent.click(botaoResponder(modal));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0].corpo).toEqual({ texto: "Oi @Sócia Vitta ", mencoes: ["P2"] });
  });

  it("sem @ nenhum o autocomplete não aparece", async () => {
    // Par de presença do teste acima: uma lista sempre aberta passaria por ele
    // sem que o @ tivesse feito nada.
    const modal = await abrirCom([]);

    fireEvent.change(caixa(modal), { target: { value: "Sem menção nenhuma" } });

    expect(within(modal).queryByRole("list", { name: "Pessoas para mencionar" })).toBeNull();
  });

  it("apagar o nome do texto tira a menção do envio", async () => {
    const modal = await abrirCom([]);

    fireEvent.change(caixa(modal), { target: { value: "Oi @" } });
    const lista = await within(modal).findByRole("list", { name: "Pessoas para mencionar" });
    fireEvent.click(within(lista).getByRole("button", { name: "Sócia Vitta" }));
    fireEvent.change(caixa(modal), { target: { value: "Deixa comigo" } });
    fireEvent.click(botaoResponder(modal));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0].corpo).toEqual({ texto: "Deixa comigo", mencoes: [] });
  });

  it("a menção gravada aparece destacada no fio", async () => {
    // O par na tela da coluna `mencoes`: sem ele, chamar alguém ficaria
    // indistinguível de escrever o nome no meio da frase.
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "@Sócia Vitta consegue olhar?", mencoes: ["P2"] }),
      linhaDoFio("c2", { texto: "Falei com Sócia Vitta ontem", mencoes: [] }),
    ]);

    const linhas = await within(modal).findAllByRole("listitem");
    expect(within(linhas[0]).getByText("@Sócia Vitta").tagName).toBe("STRONG");
    expect(within(linhas[1]).queryByText("@Sócia Vitta")).toBeNull();
  });

  it("a própria resposta dentro da janela ganha o botão Corrigir; a linha de movimento, não", async () => {
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "Minha resposta", editavel_ate: daTempo() }),
      linhaDoFio("c2", {
        autor_id: null,
        autor_nome: null,
        linha: "movimento",
        texto: "Pedro Vitta moveu para Aguardando",
        movimento_campo: "estado",
        editavel_ate: null,
      }),
    ]);

    const linhas = await within(modal).findAllByRole("listitem");
    expect(within(linhas[0]).getByRole("button", { name: /Corrigir/ })).toBeTruthy();
    expect(within(linhas[1]).queryByRole("button", { name: /Corrigir/ })).toBeNull();
  });

  it("passada a janela, o botão Corrigir some", async () => {
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "Ainda dá", editavel_ate: daTempo() }),
      linhaDoFio("c2", { texto: "Tarde demais", editavel_ate: tardeDemais() }),
    ]);

    const linhas = await within(modal).findAllByRole("listitem");
    // A irmã de presença no MESMO render: a linha de cima ainda oferece o botão.
    expect(within(linhas[0]).getByRole("button", { name: /Corrigir/ })).toBeTruthy();
    expect(within(linhas[1]).queryByRole("button", { name: /Corrigir/ })).toBeNull();
  });

  it("a resposta de outra pessoa não oferece Corrigir", async () => {
    // Quem diz de quem é a linha é o backend, pelo `editavel_ate`: a tela não
    // sabe qual participante é o usuário logado.
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "Minha", editavel_ate: daTempo() }),
      linhaDoFio("c2", { autor_id: "P2", autor_nome: "Sócia Vitta", texto: "Da sócia", editavel_ate: null }),
    ]);

    const linhas = await within(modal).findAllByRole("listitem");
    expect(within(linhas[0]).getByRole("button", { name: /Corrigir/ })).toBeTruthy();
    expect(within(linhas[1]).queryByRole("button", { name: /Corrigir/ })).toBeNull();
  });

  it("corrigir manda o texto novo pela porta da linha e marca a resposta como editada", async () => {
    const modal = await abrirCom([linhaDoFio("c1", { texto: "Vou olhar hoje", editavel_ate: daTempo() })]);

    fireEvent.click(await within(modal).findByRole("button", { name: /Corrigir/ }));
    fireEvent.change(within(modal).getByLabelText("Corrigir a resposta"), {
      target: { value: "Vou olhar amanhã" },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Salvar correção" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/conversa/c1",
      metodo: "PATCH",
      corpo: { texto: "Vou olhar amanhã", mencoes: [] },
    });
    const corrigida = await within(modal).findByText(/Vou olhar amanhã/);
    expect(corrigida.closest("li")!.textContent).toContain("(editado)");
  });

  it("a correção não apaga a menção que já estava na linha", async () => {
    // Sem carregar as menções da linha ao abrir a caixa, um conserto de vírgula
    // tiraria o "@Fulano" da lista sem ninguém pedir.
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "@Sócia Vitta olha isso", mencoes: ["P2"], editavel_ate: daTempo() }),
    ]);

    fireEvent.click(await within(modal).findByRole("button", { name: /Corrigir/ }));
    fireEvent.change(within(modal).getByLabelText("Corrigir a resposta"), {
      target: { value: "@Sócia Vitta olha isso, por favor" },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Salvar correção" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect((escritas()[0].corpo as { mencoes: string[] }).mencoes).toEqual(["P2"]);
  });

  it("cancelar a correção deixa a linha como estava, sem chamar o servidor", async () => {
    const modal = await abrirCom([linhaDoFio("c1", { texto: "Como estava", editavel_ate: daTempo() })]);

    fireEvent.click(await within(modal).findByRole("button", { name: /Corrigir/ }));
    fireEvent.change(within(modal).getByLabelText("Corrigir a resposta"), { target: { value: "Desisti" } });
    fireEvent.click(within(modal).getByRole("button", { name: "Cancelar" }));

    expect(escritas()).toHaveLength(0);
    expect(within(modal).getByText(/Como estava/)).toBeTruthy();
  });

  it("o (editado) só aparece na linha que foi corrigida", async () => {
    // Par de presença do carimbo: uma marca cravada apareceria em todas.
    const modal = await abrirCom([
      linhaDoFio("c1", { texto: "Corrigida", editado_em: "2026-09-01T12:05:00Z" }),
      linhaDoFio("c2", { texto: "Intocada", editado_em: null }),
    ]);

    const linhas = await within(modal).findAllByRole("listitem");
    expect(linhas[0].textContent).toContain("(editado)");
    expect(linhas[1].textContent).not.toContain("(editado)");
  });

  it("o fio vazio não oferece Corrigir nenhum, e a caixa continua lá", async () => {
    const modal = await abrirCom([]);

    expect(await within(modal).findByText("Nada aconteceu nesta Demanda ainda.")).toBeTruthy();
    expect(within(modal).queryByRole("button", { name: /Corrigir/ })).toBeNull();
    expect(caixa(modal)).toBeTruthy();
  });

  it("a recusa do servidor aparece com a frase dele", async () => {
    const modal = await abrirCom([], {
      recusa: { status: 422, detail: "O prazo de 10 minutos para corrigir esta resposta já passou." },
    });

    fireEvent.change(caixa(modal), { target: { value: "Tarde demais" } });
    fireEvent.click(botaoResponder(modal));

    const aviso = await within(modal).findByRole("alert");
    expect(aviso.textContent).toContain("O prazo de 10 minutos");
  });

  it("rede fora ao responder: o modal avisa, em vez de engolir a resposta", async () => {
    // Sem o `catch`, a resposta sumiria calada e quem escreveu acharia que
    // falou. `redeFora: "salvar"` derruba só a escrita: o fio carrega normal.
    vi.spyOn(console, "error").mockImplementation(() => {});
    const modal = await abrirCom([], { redeFora: "salvar" });

    fireEvent.change(caixa(modal), { target: { value: "Some no caminho" } });
    fireEvent.click(botaoResponder(modal));

    const aviso = await within(modal).findByRole("alert");
    expect(aviso.textContent).toContain("Não foi possível falar com o servidor");
  });
});

describe("Arrastar entre colunas", () => {
  /** O gesto inteiro: pega o card, passa por cima da coluna e solta nela. */
  function arrastar(titulo: string, paraColuna: string) {
    fireEvent.dragStart(cardDe(titulo));
    const alvo = colunaDe(paraColuna);
    fireEvent.dragOver(alvo);
    fireEvent.drop(alvo);
  }

  it("o card sai arrastável e a coluna aceita recebê-lo", async () => {
    // O jsdom dispara `dragStart` e `drop` em qualquer elemento, então os
    // testes de gesto abaixo passariam num card que o navegador nem deixa
    // pegar. Estas duas são as condições que o NAVEGADOR cobra: o atributo
    // `draggable` no card e o `preventDefault` no `dragOver` da coluna, sem o
    // qual o "soltar aqui" é recusado antes de virar `drop`.
    montar([demanda("d1", "Uma nova")]);

    await screen.findByText("Uma nova");
    expect(cardDe("Uma nova").getAttribute("draggable")).toBe("true");

    fireEvent.dragStart(cardDe("Uma nova"));
    const passandoPorCima = createEvent.dragOver(colunaDe("Em andamento"));
    fireEvent(colunaDe("Em andamento"), passandoPorCima);

    expect(passandoPorCima.defaultPrevented).toBe(true);
  });

  it("soltar noutra coluna chama a mesma rota do botão Mover, e o card fica lá", async () => {
    montar([demanda("d1", "Uma nova"), demanda("d2", "Outra nova")]);

    await screen.findByText("Uma nova");
    arrastar("Uma nova", "Em andamento");

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/mover",
      metodo: "POST",
      corpo: { estado: "em_andamento" },
    });

    await waitFor(() => expect(within(colunaDe("Em andamento")).getByText("Uma nova")).toBeTruthy());
    // A irmã de presença: a outra Demanda continua em Nova no mesmo render,
    // então "saiu de Nova" não é "a coluna Nova sumiu".
    expect(within(colunaDe("Nova")).queryByText("Uma nova")).toBeNull();
    expect(within(colunaDe("Nova")).getByText("Outra nova")).toBeTruthy();
  });

  it("soltar numa transição proibida devolve o card à origem, com a frase do servidor", async () => {
    // De Concluída para Cancelada o backend recusa: reabrir é o único caminho.
    const motivo = "A Demanda não pode ir de Concluída para Cancelada.";
    montar([demanda("d1", "Fechada", { estado: "concluida" }), demanda("d2", "Uma nova")], {
      recusa: { status: 422, detail: motivo },
    });

    await screen.findByRole("region", { name: "Concluída" });
    fireEvent.click(within(colunaDe("Concluída")).getByRole("button"));
    await screen.findByText("Fechada");

    arrastar("Fechada", "Cancelada");

    expect((await screen.findByRole("alert")).textContent).toContain(motivo);
    // O card NÃO pode ter ficado no destino que o servidor recusou.
    expect(within(colunaDe("Concluída")).getByText("Fechada")).toBeTruthy();
    expect(within(colunaDe("Cancelada")).queryByText("Fechada")).toBeNull();
  });

  it("no 409 do Quadro desatualizado o card também não muda de coluna", async () => {
    const motivo =
      "O Quadro está desatualizado e este movimento não foi feito. Recarregue o Quadro e tente de novo.";
    montar([demanda("d1", "Uma nova")], { recusa: { status: 409, detail: motivo } });

    await screen.findByText("Uma nova");
    arrastar("Uma nova", "Aguardando");

    expect((await screen.findByRole("alert")).textContent).toContain("Quadro está desatualizado");
    expect(within(colunaDe("Nova")).getByText("Uma nova")).toBeTruthy();
    expect(within(colunaDe("Aguardando")).queryByText("Uma nova")).toBeNull();
  });

  it("soltar na coluna em que o card já está não chama a API", async () => {
    // A rota recusaria com 422 ("transição inválida") um gesto que não pediu
    // nada: a tela não gasta a viagem nem inventa um erro para quem desistiu.
    montar([demanda("d1", "Uma nova")]);

    await screen.findByText("Uma nova");
    arrastar("Uma nova", "Nova");

    await waitFor(() => expect(within(colunaDe("Nova")).getByText("Uma nova")).toBeTruthy());
    expect(escritas()).toHaveLength(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("o botão Mover continua fazendo o mesmo que o arrasto", async () => {
    montar([demanda("d1", "Uma nova")]);

    fireEvent.click(await screen.findByRole("button", { name: "Mover Uma nova" }));
    fireEvent.click(within(cardDe("Uma nova")).getByRole("button", { name: "Em andamento" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0].url).toBe("/api/admin/tecnologia/demandas/d1/mover");
    await waitFor(() => expect(within(colunaDe("Em andamento")).getByText("Uma nova")).toBeTruthy());
  });

  /** As leituras do Quadro (a Conversa do modal tem GET próprio). */
  const leiturasDoQuadro = () =>
    chamadas.filter((c) => c.metodo === "GET" && !c.url.includes("/conversa"));

  it("no 409 a tela recarrega o Quadro sozinha, e o motivo continua à vista", async () => {
    // A frase do servidor manda recarregar o Quadro, e a tela não tem botão de
    // recarregar: pedir uma ação que o app não oferece é deixar quem levou a
    // recusa sem saída. Recarregando aqui, a frase vira descrição do que já
    // aconteceu. O motivo NÃO some junto, senão o Quadro se corrigiria em
    // silêncio e o card "voltaria" sozinho sem explicação.
    montar([demanda("d1", "Uma nova")], {
      recusa: {
        status: 409,
        detail: "O Quadro está desatualizado e este movimento não foi feito. Recarregue o Quadro e tente de novo.",
      },
    });

    await screen.findByText("Uma nova");
    const antes = leiturasDoQuadro().length;
    arrastar("Uma nova", "Aguardando");

    await screen.findByRole("alert");
    await waitFor(() => expect(leiturasDoQuadro()).toHaveLength(antes + 1));
    expect(screen.getByRole("alert").textContent).toContain("Quadro está desatualizado");
  });

  it("no 422 a tela não recarrega: o que está velho não é o Quadro", async () => {
    // O par de presença do teste acima: uma tela que recarregasse depois de
    // toda recusa passaria naquele. A transição proibida não tem nada de
    // desatualizado, e recarregar ali só gastaria a viagem.
    montar([demanda("d1", "Fechada", { estado: "concluida" })], {
      recusa: { status: 422, detail: "A Demanda não pode ir de Concluída para Cancelada." },
    });

    await screen.findByRole("region", { name: "Concluída" });
    fireEvent.click(within(colunaDe("Concluída")).getByRole("button"));
    await screen.findByText("Fechada");
    const antes = leiturasDoQuadro().length;

    arrastar("Fechada", "Cancelada");

    await screen.findByRole("alert");
    expect(leiturasDoQuadro()).toHaveLength(antes);
  });
});


describe("A barra de filtros", () => {
  const CARDS = [
    demanda("d1", "Ajuste na Ana", { tipo: "ajuste", produto_id: "prod-1", responsavel_id: "P1" }),
    demanda("d2", "Defeito nos POPs", { tipo: "defeito", produto_id: "prod-2", responsavel_id: "P2" }),
  ];

  /**
   * Escolhe uma opção num dos filtros e espera o Quadro voltar do servidor.
   *
   * A espera é o que dá sentido à asserção de ausência: enquanto recarrega, a
   * tela troca as colunas por "Carregando Demandas..." e NENHUM card está na
   * tela, então um `queryByText(...).toBeNull()` disparado cedo passaria mesmo
   * com um servidor que não filtrasse nada.
   */
  async function filtrar(campo: string, opcao: string, buscaEsperada: string) {
    fireEvent.click(await screen.findByRole("combobox", { name: campo }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText(opcao));
    await waitFor(() => expect(chamadas.at(-1)!.url).toBe(buscaEsperada));
    await waitFor(() => expect(screen.queryByText("Carregando Demandas...")).toBeNull());
  }

  it("o filtro por tipo vai na busca da API e reduz o Quadro", async () => {
    montar(CARDS);
    await screen.findByText("Ajuste na Ana");

    await filtrar("Filtrar por tipo", "Ajuste", "/api/admin/tecnologia/demandas?tipo=ajuste");

    expect(screen.getByText("Ajuste na Ana")).toBeTruthy();
    expect(screen.queryByText("Defeito nos POPs")).toBeNull();
  });

  it("o filtro por Produto vai na busca da API e reduz o Quadro", async () => {
    montar(CARDS);
    await screen.findByText("Ajuste na Ana");

    await filtrar("Filtrar por Produto", "POPs", "/api/admin/tecnologia/demandas?produto_id=prod-2");

    expect(screen.getByText("Defeito nos POPs")).toBeTruthy();
    expect(screen.queryByText("Ajuste na Ana")).toBeNull();
  });

  it("o filtro por responsável vai na busca da API e reduz o Quadro", async () => {
    montar(CARDS);
    await screen.findByText("Ajuste na Ana");

    await filtrar("Filtrar por responsável", "Sócia Vitta", "/api/admin/tecnologia/demandas?responsavel_id=P2");

    expect(screen.getByText("Defeito nos POPs")).toBeTruthy();
    expect(screen.queryByText("Ajuste na Ana")).toBeNull();
  });

  it("com filtro ativo a tela diz que está filtrando, e limpar traz o Quadro inteiro de volta", async () => {
    // Um Quadro filtrado e calado é indistinguível de um Quadro vazio: quem
    // volta à aba precisa ver que sobrou filtro e ter onde desfazê-lo.
    montar(CARDS);
    await screen.findByText("Ajuste na Ana");

    await filtrar("Filtrar por tipo", "Ajuste", "/api/admin/tecnologia/demandas?tipo=ajuste");
    expect(screen.queryByText("Defeito nos POPs")).toBeNull();
    expect(screen.getByText(/O Quadro está filtrado/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));

    expect(await screen.findByText("Defeito nos POPs")).toBeTruthy();
    expect(screen.getByText("Ajuste na Ana")).toBeTruthy();
    expect(chamadas.at(-1)!.url).toBe("/api/admin/tecnologia/demandas");
  });

  it("sem filtro nenhum a tela não diz que está filtrando", async () => {
    // O par de presença do teste acima: um aviso cravado passaria naquele.
    montar(CARDS);

    await screen.findByText("Ajuste na Ana");
    expect(screen.queryByText(/O Quadro está filtrado/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).toBeNull();
  });

  it("o filtro alcança também o Produto inativado, marcado como tal", async () => {
    // Desativar um Produto o tira da ESCOLHA de quem abre Demanda nova, não do
    // histórico (ADR 0050, decisão 11). As Demandas dele continuam no Quadro,
    // então um filtro que não o oferecesse deixaria essas Demandas fora do
    // alcance de qualquer filtro. A marca evita a pergunta "por que este
    // Produto está aqui e não no formulário?".
    montar(CARDS);
    fireEvent.click(await screen.findByRole("combobox", { name: "Filtrar por Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual([
      "Todos os Produtos",
      "Ana",
      "POPs",
      "Site antigo (inativo)",
    ]);
  });

  it("o formulário de Demanda nova continua só com Produto ativo", async () => {
    // O par do teste acima: filtrar é ler o histórico, abrir é escolher onde a
    // Demanda nasce, e só a segunda cobra Produto ativo.
    montar(CARDS);
    fireEvent.click(await screen.findByRole("button", { name: /Nova Demanda/ }));
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Ana", "POPs"]);
  });
});

describe("Duas trocas de filtro em sequência", () => {
  /** Uma chamada que o componente fez e que ainda não teve resposta. */
  type Pendente = {
    url: string;
    /** Responde 200 com esta lista. */
    responder: (dados: Demanda[]) => void;
    /** Responde com este status de erro. */
    recusar: (status: number, detail?: string) => void;
  };

  /**
   * O `fetch` que NÃO responde sozinho.
   *
   * O servidor falso dos outros testes responde na hora, e por isso não sabe
   * dizer nada sobre ordem de chegada. Aqui cada chamada fica pendurada até o
   * teste mandar responder, que é o único jeito de escrever a ordem em que as
   * respostas voltam, que é onde a corrida mora.
   */
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
              recusar: (status, detail) =>
                resolve({
                  ok: false,
                  status,
                  json: async () => ({ detail: detail ?? "recusado" }),
                } as unknown as Response),
            });
          }),
      ),
    );
    return pendentes;
  }

  /**
   * Dá ao React o tempo de processar a resposta recém entregue.
   *
   * Sem esta espera PEDIDA, quem daria o tempo seria o ciclo de algum
   * `waitFor` mais adiante, e o teste passaria por sorte de agendamento em vez
   * de por asserção.
   */
  async function deixarOReactProcessar() {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  /** O host dos filtros, como o módulo faz. */
  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <QuadroDemandas
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
      />
    );
  }

  const AJUSTE = demanda("d1", "Ajuste na Ana", { tipo: "ajuste" });
  const DEFEITO = demanda("d2", "Defeito nos POPs", { tipo: "defeito" });

  /** Escolhe um tipo na barra de filtros. */
  function escolherTipo(rotulo: string) {
    fireEvent.click(screen.getByRole("combobox", { name: "Filtrar por tipo" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText(rotulo));
  }

  /**
   * Monta a tela com o Quadro já pintado e DOIS pedidos de filtro no ar.
   *
   * Devolve a fila: `[0]` é a leitura inicial (já respondida), `[1]` é o
   * pedido do filtro Ajuste (o VELHO) e `[2]` o do filtro Defeito (o NOVO).
   */
  async function comDoisPedidosNoAr(): Promise<Pendente[]> {
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder([AJUSTE, DEFEITO]);
    await screen.findByText("Ajuste na Ana");

    escolherTipo("Ajuste");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    escolherTipo("Defeito");
    await waitFor(() => expect(pendentes).toHaveLength(3));

    expect(pendentes[1].url).toContain("tipo=ajuste");
    expect(pendentes[2].url).toContain("tipo=defeito");
    return pendentes;
  }

  it("a resposta atrasada do filtro antigo não repinta o Quadro do filtro novo", async () => {
    // A rede não devolve na ordem em que foi chamada. Quem troca o filtro duas
    // vezes rápido deixa dois GET no ar; se o PRIMEIRO chegar por último, uma
    // tela ingênua pinta o resultado do filtro que ninguém está mais vendo, com
    // os campos mostrando o filtro novo. É mentira silenciosa: nada de erro,
    // nada de espera, só o Quadro errado.
    const pendentes = await comDoisPedidosNoAr();

    // O pedido NOVO chega primeiro, e o velho depois.
    pendentes[2].responder([DEFEITO]);
    await screen.findByText("Defeito nos POPs");
    pendentes[1].responder([AJUSTE]);
    await deixarOReactProcessar();

    expect(screen.getByText("Defeito nos POPs")).toBeTruthy();
    expect(screen.queryByText("Ajuste na Ana")).toBeNull();
  });

  it("a resposta do filtro antigo que chega PRIMEIRO não desliga a espera", async () => {
    // A ordem inversa da anterior, e é ela que exercita a guarda da espera: o
    // pedido velho chegando antes do novo. Sem a guarda, a tela diz "pronto" e
    // mostra a lista de ANTES do filtro, com o campo escrito com o filtro novo,
    // enquanto a leitura de verdade ainda está vindo.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[1].responder([AJUSTE]);
    await deixarOReactProcessar();

    expect(screen.getByText("Carregando Demandas...")).toBeTruthy();
    expect(screen.queryByText("Ajuste na Ana")).toBeNull();

    // A irmã de presença: quando o pedido NOVO chega, a espera acaba e o card
    // certo aparece, então "ainda carregando" acima não é uma tela travada.
    pendentes[2].responder([DEFEITO]);
    expect(await screen.findByText("Defeito nos POPs")).toBeTruthy();
    expect(screen.queryByText("Carregando Demandas...")).toBeNull();
  });

  it("a falha do pedido antigo não escreve aviso por cima do Quadro certo", async () => {
    // Filtro velho devolve 500, filtro novo devolve 200. Se o 500 chegar por
    // último, uma tela sem guarda mostraria "Não foi possível carregar as
    // Demandas." em cima de um Quadro que está perfeitamente certo.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[2].responder([DEFEITO]);
    await screen.findByText("Defeito nos POPs");
    pendentes[1].recusar(500);
    await deixarOReactProcessar();

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Defeito nos POPs")).toBeTruthy();
  });

  it("a falha do pedido mais novo, essa sim, vira aviso", async () => {
    // O par de presença do teste acima: sem ele, uma tela que engolisse TODA
    // falha de leitura passaria naquele.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[1].responder([AJUSTE]);
    pendentes[2].recusar(500);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Não foi possível carregar as Demandas.",
    );
  });

  it("o Quadro que volta não apaga a recusa de uma escrita", async () => {
    // Com o formulário aberto: trocar o filtro deixa um GET no ar, a escrita é
    // recusada e escreve o alerta, e o GET chega depois. Se ele limpasse o
    // erro, o formulário ficaria aberto, preenchido, e sem explicação nenhuma
    // de por que a Demanda não foi criada.
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder([AJUSTE, DEFEITO]);
    await screen.findByText("Ajuste na Ana");

    fireEvent.click(screen.getByRole("button", { name: /Nova Demanda/ }));
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Encerrar conversas" } });
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));

    escolherTipo("Ajuste");
    await waitFor(() => expect(pendentes).toHaveLength(2));

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));
    await waitFor(() => expect(pendentes).toHaveLength(3));
    pendentes[2].recusar(422, "Produto sem dono nao recebe Demanda nova.");
    expect((await screen.findByRole("alert")).textContent).toContain("Produto sem dono");

    pendentes[1].responder([AJUSTE]);
    await deixarOReactProcessar();

    expect(screen.getByRole("alert").textContent).toContain("Produto sem dono");
    // O formulário continua aberto com o que foi digitado, ao lado do motivo.
    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Encerrar conversas");
  });

  it("o Quadro que volta apaga, sim, o aviso da leitura anterior", async () => {
    // O par de presença do teste acima: um `carregar` que nunca limpasse erro
    // nenhum passaria naquele, e deixaria na tela um aviso de falha que a
    // leitura seguinte já desmentiu.
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].recusar(500);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Não foi possível carregar as Demandas.",
    );

    escolherTipo("Ajuste");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    pendentes[1].responder([AJUSTE]);

    expect(await screen.findByText("Ajuste na Ana")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Abrir a Demanda pelo link (issue #640)", () => {
  /** Põe a barra de endereços no que o link copiado teria trazido. */
  function chegarPor(busca: string) {
    window.history.replaceState({}, "", `/admin/tecnologia${busca}`);
  }

  /**
   * O anfitrião deste bloco, com o `carregandoAuth` como prop.
   *
   * O `montar()` lá de cima guarda os filtros dentro dele e não devolve o
   * `rerender`; os testes daqui precisam re-renderizar o Quadro com props
   * diferentes (a sessão que resolve) e envolvê-lo num `Profiler`. O papel dos
   * filtros é o mesmo do `Anfitriao` do `montar`: quem os guarda é a aba
   * Tecnologia (issue #639).
   */
  function QuadroHospedado({ carregandoAuth = false }: { carregandoAuth?: boolean }) {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <QuadroDemandas
        token="token-de-teste"
        carregandoAuth={carregandoAuth}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
      />
    );
  }

  /** O servidor falso mínimo deste bloco: a lista, e a Conversa vazia do modal. */
  function servidorCom(lista: Demanda[]) {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: string) =>
          ({
            ok: true,
            status: 200,
            json: async () => (url.includes("/conversa") ? [] : lista),
          }) as unknown as Response,
      ),
    );
  }

  afterEach(() => {
    window.history.replaceState({}, "", "/admin/tecnologia");
  });

  it("o link abre o card daquela Demanda já aberto", async () => {
    chegarPor("?demanda=d2");
    montar([demanda("d1", "Uma nova"), demanda("d2", "A do link")], { conversa: [] });

    const modal = await screen.findByRole("dialog");

    expect((within(modal).getByLabelText("Título") as HTMLInputElement).value).toBe("A do link");
    // Achada a Demanda, o aviso de "não está no Quadro" não pode ficar na tela
    // ao lado do card aberto, contando o contrário do que a tela mostra.
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("o link que o botão copia é o link que a tela abre", async () => {
    // A prova de que os dois lados falam o mesmo formato, pela URL de verdade:
    // quem chega é o endereço montado pelo `linkDaDemanda`, e não uma query
    // string escrita à mão neste teste.
    const link = linkDaDemanda("d2", window.location.origin);
    chegarPor(new URL(link).search);
    montar([demanda("d1", "Uma nova"), demanda("d2", "A do link")], { conversa: [] });

    const modal = await screen.findByRole("dialog");

    expect((within(modal).getByLabelText("Título") as HTMLInputElement).value).toBe("A do link");
  });

  it("sem o parâmetro, nenhum card abre sozinho", async () => {
    // Irmã de presença dos testes acima: o Quadro desenhou os cards no mesmo
    // render, então "nenhum modal" é sobre o link, e não sobre uma tela vazia.
    montar([demanda("d1", "Uma nova"), demanda("d2", "A do link")]);

    expect(await screen.findByText("A do link")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("link para uma Demanda que não está no Quadro: a tela diz isso, sem culpar ninguém", async () => {
    chegarPor("?demanda=nao-existe");
    montar([demanda("d1", "Uma nova")]);

    const aviso = await screen.findByRole("status");

    expect(aviso.textContent).toContain("não está no Quadro");
    // A frase NÃO afirma o que o código não sabe: nem que a Demanda foi
    // apagada (nada se apaga nesta aba), nem que falta permissão (o gate é da
    // API, e a recusa dela viraria erro de carregamento, não lista sem o card).
    expect(aviso.textContent).not.toContain("apagada");
    expect(aviso.textContent).not.toContain("permissão");
    // Irmã de presença: o Quadro carregou e mostra o que tem.
    expect(screen.getByText("Uma nova")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("enquanto a sessão carrega, o link não vira acusação nenhuma", async () => {
    // O caminho que mordeu na fatia anterior: o `useAuth` nasce com
    // `{ token: null, loading: true }`, e abrir pela URL acontece no primeiro
    // render, quando o token ainda não chegou. Dizer "não está no Quadro" aqui
    // seria acusar um link bom em toda abertura pelo link.
    chegarPor("?demanda=d1");
    montar([demanda("d1", "Uma nova")], { carregandoAuth: true });

    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    // Irmã de presença: a tela diz o que de fato está acontecendo.
    expect(screen.getByText("Carregando Demandas...")).toBeTruthy();
  });

  it("resolvida a sessão, o link abre o card sem a pessoa clicar de novo", async () => {
    // O link chega ANTES do token: o que se prova aqui é que ele não se perde
    // no caminho, e que a abertura acontece quando as Demandas chegam.
    chegarPor("?demanda=d1");
    servidorCom([demanda("d1", "Uma nova")]);
    const { rerender } = render(<QuadroHospedado carregandoAuth />);

    expect(screen.queryByRole("dialog")).toBeNull();

    rerender(<QuadroHospedado carregandoAuth={false} />);

    const modal = await screen.findByRole("dialog");
    expect((within(modal).getByLabelText("Título") as HTMLInputElement).value).toBe("Uma nova");
  });

  it("sem sessão, o link não vira 'não está no Quadro'", async () => {
    // Duas causas diferentes, duas frases: sem token o Quadro nem foi lido, e
    // dizer que a Demanda não está nele afirmaria um fato não verificado.
    chegarPor("?demanda=d1");
    montar([demanda("d1", "Uma nova")], { token: null });

    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("a sessão não está ativa");
    expect(screen.queryByRole("status")).toBeNull();
  });
});
