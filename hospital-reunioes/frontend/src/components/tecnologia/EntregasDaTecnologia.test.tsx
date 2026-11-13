/**
 * @vitest-environment jsdom
 */

/**
 * A aba Entregas (issue #1556; ritmo semanal na issue #1701, PRD #1689,
 * ADR 0092).
 *
 * Quem conta, filtra e corta o que não foi entregue é o servidor (os testes
 * dele estão em `test_tecnologia_entregas.py`). Aqui se cobra o que a tela faz
 * com isso: os dois números com a variação e a composição no hover, o gráfico
 * das 12 semanas com a prévia da semana, o movimento reduzido, a lista com as
 * datas e o Responsável, os filtros que viram a consulta, e o clique que abre o
 * Documento do card.
 *
 * O jsdom não mede layout, e o `ResponsiveContainer` do `recharts` não desenha
 * nada nele. Como no teste do gráfico de Visitantes por dia, só ele é trocado
 * por um de tamanho fixo; o resto do `recharts` roda de verdade.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SEM_O_QUE_MUDA, TITULO_DOCUMENTO } from "./DocumentoDoCard";
import { EntregasDaTecnologia } from "./EntregasDaTecnologia";

vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
      cloneElement(children, { width: 600, height: 240 }),
  };
});

const URL_DAS_ENTREGAS = "/api/admin/tecnologia/entregas";

const INICIOS = [
  "2026-08-24",
  "2026-08-31",
  "2026-09-07",
  "2026-09-14",
  "2026-09-21",
  "2026-09-28",
  "2026-10-05",
  "2026-10-12",
  "2026-10-19",
  "2026-10-26",
  "2026-11-02",
  "2026-11-09",
];

function semanas() {
  return INICIOS.map((inicio) =>
    inicio === "2026-11-09"
      ? {
          inicio,
          pedidos: 3,
          g: 1,
          m: 1,
          p: 0,
          entregas: [
            { titulo: "Aviso quando a ata sair", tamanho: "M" },
            { titulo: "Painel da diretoria", tamanho: "G" },
          ],
        }
      : { inicio, pedidos: 1, g: 0, m: 0, p: 1, entregas: [{ titulo: `Ajuste de ${inicio}`, tamanho: "P" }] },
  );
}

/** Uma entrega da lista, no formato da lista do chat, sem O que muda nem Demonstração. */
function entrega(id: string, titulo: string) {
  return {
    id,
    titulo,
    etapa: "em_producao",
    tem_vinculo: true,
    o_que_muda: null,
    partes: [],
    fechada_em: null,
    em_producao_em: null,
    versao: null,
    responsavel: "Pedro Rib",
    classificacao: "melhoria",
    origem: "vitta",
    demonstracao_url: null,
  };
}

function resposta() {
  return {
    topo: {
      pedidos: { total: 12, anteriores: 8, bugs: 3, melhorias: 9 },
      entregas: { total: 7, anteriores: 9, g: 1, m: 2, p: 4 },
    },
    semanas: semanas(),
    grupos: [
      {
        inicio: "2026-11-09",
        entregas: [
          {
            ...entrega("e-1", "Aviso quando a ata sair"),
            numero: 42,
            tamanho: "G",
            classificacao: "melhoria",
            versao: "v0.285.0",
            fechada_em: "2026-11-12T15:00:00Z",
            o_que_muda: "**O que muda:** o aviso chega quando a ata sai.",
            demonstracao_url: "https://manual-hsm.vercel.app/demonstracao/aviso",
          },
          {
            ...entrega("e-2", "Botão de responder sumiu"),
            tamanho: "P",
            classificacao: "bug",
            etapa: "entregue",
            fechada_em: "2026-11-10T12:00:00Z",
          },
          { ...entrega("e-3", "Filtro por setor"), tamanho: "P", fechada_em: "2026-11-09T12:00:00Z" },
        ],
      },
      {
        inicio: "2026-11-02",
        entregas: [{ ...entrega("e-4", "Relatório por setor"), tamanho: "M", fechada_em: "2026-11-03T12:00:00Z" }],
      },
    ],
    responsaveis: [
      { valor: "P4", nome: "Pedro Rib" },
      { valor: "P1", nome: "Pedro Vitta" },
    ],
  };
}

let pedidos: string[] = [];

/** O servidor de mentira: por padrão, a mesma resposta para toda consulta. */
function montar(responder: (url: string) => object = () => resposta()) {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      return { ok: true, status: 200, json: async () => responder(url) } as unknown as Response;
    }),
  );
  return render(<EntregasDaTecnologia token="token-de-teste" />);
}

/** Quem pede menos movimento: o `matchMedia` que o jsdom não tem, dublado. */
function comMovimentoReduzido() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((consulta: string) => ({
      matches: consulta === "(prefers-reduced-motion: reduce)",
      media: consulta,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

/** A consulta do último pedido, sem a ordem dos parâmetros. */
function ultimaConsulta(): Record<string, string> {
  const ultima = pedidos[pedidos.length - 1];
  return Object.fromEntries(new URL(ultima, "http://x").searchParams.entries());
}

const numero = (rotulo: "Pedidos" | "Entregas") => screen.findByRole("button", { name: new RegExp(`^${rotulo}`) });

const barras = (container: HTMLElement, serie: string) => [
  ...container.querySelectorAll<SVGRectElement>(`rect[data-serie="${serie}"]`),
];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Os dois números do topo", () => {
  it("mostram pedidos e entregas das últimas 4 semanas, com a variação em texto", async () => {
    comMovimentoReduzido();
    montar();

    const pedidosDoTopo = await numero("Pedidos");
    expect(within(pedidosDoTopo).getByText("12")).toBeTruthy();
    expect(within(pedidosDoTopo).getByText("+4 contra as 4 anteriores")).toBeTruthy();
    const entregas = await numero("Entregas");
    expect(within(entregas).getByText("7")).toBeTruthy();
    expect(within(entregas).getByText("-2 contra as 4 anteriores")).toBeTruthy();
    expect(pedidos[0].startsWith(URL_DAS_ENTREGAS)).toBe(true);
  });

  it("o hover num número abre a composição depois de 150 ms, e a saída fecha 180 ms depois", async () => {
    comMovimentoReduzido();
    montar();
    const pedidosDoTopo = await numero("Pedidos");
    vi.useFakeTimers();

    fireEvent.mouseEnter(pedidosDoTopo);
    act(() => vi.advanceTimersByTime(149));
    expect(screen.queryByRole("region", { name: "Composição dos pedidos" })).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    const composicao = screen.getByRole("region", { name: "Composição dos pedidos" });
    expect(within(composicao).getByText("3 bugs")).toBeTruthy();
    expect(within(composicao).getByText("9 melhorias")).toBeTruthy();
    expect(pedidosDoTopo.getAttribute("aria-expanded")).toBe("true");

    fireEvent.mouseLeave(pedidosDoTopo);
    act(() => vi.advanceTimersByTime(179));
    expect(screen.getByRole("region", { name: "Composição dos pedidos" })).toBeTruthy();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("region", { name: "Composição dos pedidos" })).toBeNull();
  });

  it("o clique fixa a composição, e o segundo toque fecha", async () => {
    comMovimentoReduzido();
    montar();
    const entregas = await numero("Entregas");
    vi.useFakeTimers();

    fireEvent.click(entregas);
    const composicao = screen.getByRole("region", { name: "Composição das entregas" });
    expect(within(composicao).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "1 G (6 partes ou mais)",
      "2 M (de 2 a 5 partes)",
      "4 P (até 1 parte)",
    ]);
    fireEvent.mouseLeave(entregas);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("region", { name: "Composição das entregas" })).toBeTruthy();

    fireEvent.click(entregas);
    expect(screen.queryByRole("region", { name: "Composição das entregas" })).toBeNull();
  });

  it("sem pedido de menos movimento, o número sobe contando de 0 até o valor", async () => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
    montar();
    const pedidosDoTopo = await numero("Pedidos");
    expect(within(pedidosDoTopo).getByText("0")).toBeTruthy();

    act(() => vi.advanceTimersByTime(1000));

    expect(within(pedidosDoTopo).getByText("12")).toBeTruthy();
  });
});

describe("O gráfico das 12 semanas", () => {
  it("mostra a barra de pedidos ao lado da de entregas, empilhada em G, M e P", async () => {
    comMovimentoReduzido();
    const { container } = montar();
    expect(await screen.findByRole("figure", { name: "Pedidos e entregas das últimas 12 semanas" })).toBeTruthy();

    for (const serie of ["pedidos", "g", "m", "p"]) expect(barras(container, serie)).toHaveLength(12);
    // Na semana de 09/11: o G embaixo, o M em cima dele, e os pedidos ao lado.
    const [g, m, pedidosDaSemana] = ["g", "m", "pedidos"].map((serie) => barras(container, serie)[11]);
    const y = (barra: SVGRectElement, atributo: "y" | "height") => Number(barra.getAttribute(atributo));
    expect(y(m, "y") + y(m, "height")).toBeCloseTo(y(g, "y"));
    expect(Number(pedidosDaSemana.getAttribute("x"))).toBeLessThan(Number(g.getAttribute("x")));
    // Do mais escuro para o mais claro da marca.
    expect(g.getAttribute("fill")).toBe("var(--color-primary-dark)");
    expect(m.getAttribute("fill")).toBe("var(--color-primary)");
    expect(barras(container, "p")[0].getAttribute("fill")).toBe("var(--color-primary-light)");
  });

  it("o hover numa semana mostra os títulos e o tamanho do que saiu", async () => {
    comMovimentoReduzido();
    const { container } = montar();
    await screen.findByRole("figure", { name: "Pedidos e entregas das últimas 12 semanas" });

    // 600 px: o eixo dos números ocupa os primeiros 32 e a margem os últimos 8;
    // a última semana fica entre 513 e 592.
    fireEvent.mouseMove(container.querySelector(".recharts-wrapper")!, { clientX: 560, clientY: 100 });

    expect(screen.getByText("Semana de 09/11")).toBeTruthy();
    expect(screen.getByText("3 pedidos, 2 entregas")).toBeTruthy();
    const saiu = screen.getByRole("list", { name: "O que saiu na semana" });
    expect(within(saiu).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "M Aviso quando a ata sair",
      "G Painel da diretoria",
    ]);
  });
});

describe("Com movimento reduzido", () => {
  it("os números aparecem prontos e nada anima", async () => {
    comMovimentoReduzido();
    const quadro = vi.spyOn(window, "requestAnimationFrame");
    const { container } = montar();

    const pedidosDoTopo = await numero("Pedidos");

    expect(within(pedidosDoTopo).getByText("12")).toBeTruthy();
    expect(within(screen.getByRole("button", { name: /^Entregas/ })).getByText("7")).toBeTruthy();
    expect(barras(container, "pedidos")).toHaveLength(12);
    expect(container.querySelectorAll(".barra-do-ritmo")).toHaveLength(0);
    expect(quadro).not.toHaveBeenCalled();
  });

  it("sem ele, as barras crescem escalonadas, semana a semana", async () => {
    const { container } = montar();
    await screen.findByRole("figure", { name: "Pedidos e entregas das últimas 12 semanas" });

    const atrasos = barras(container, "pedidos").map((barra) => barra.style.animationDelay);
    expect(barras(container, "pedidos").every((barra) => barra.classList.contains("barra-do-ritmo"))).toBe(true);
    expect(atrasos[0]).toBe("0ms");
    expect(new Set(atrasos).size).toBe(12);
  });
});

const lista = () => screen.findByRole("region", { name: "O que foi entregue" });

/** A linha da entrega pelo título: o botão que a recolhe e abre. */
async function linha(titulo: string) {
  return within(await lista()).getByRole("button", { name: new RegExp(titulo) });
}

const aberta = (titulo: string) => screen.queryByRole("region", { name: `O que mudou: ${titulo}` });

describe("A lista por semana", () => {
  it("agrupa por semana, a mais nova em cima, com o cabeçalho de quantas e de que tamanho", async () => {
    montar();

    const semanas = within(await lista()).getAllByRole("heading");
    expect(semanas.map((h) => h.textContent)).toEqual([
      "Semana de 09/11: 3 entregas (1 G, 2 P)",
      "Semana de 02/11: 1 entrega (1 M)",
    ]);
  });

  it("a linha recolhida mostra tamanho, título, tipo, versão e data", async () => {
    montar();

    const recolhida = await linha("Aviso quando a ata sair");
    for (const texto of ["G", "Aviso quando a ata sair", "Melhoria", "v0.285.0", "12/11/2026"]) {
      expect(within(recolhida).getByText(texto)).toBeTruthy();
    }
    expect(recolhida.getAttribute("aria-expanded")).toBe("false");
    expect(within(await linha("Botão de responder sumiu")).getByText("Bug")).toBeTruthy();
  });

  it("o ícone de vídeo só aparece quando há Demonstração, e abre em outra aba", async () => {
    montar();

    // Pelo rótulo, e não pelo papel: um <a> sem endereço perde o papel de link e sumiria da contagem.
    const videos = within(await lista()).getAllByLabelText("Assistir à demonstração");
    expect(videos).toHaveLength(1);
    expect(videos[0].getAttribute("href")).toBe("https://manual-hsm.vercel.app/demonstracao/aviso");
    expect(videos[0].getAttribute("target")).toBe("_blank");
    expect(videos[0].closest("li")?.textContent).toContain("Aviso quando a ata sair");
  });

  it("o mouse 150 ms em cima abre a linha, e a saída fecha 180 ms depois", async () => {
    comMovimentoReduzido();
    montar();
    const recolhida = await linha("Aviso quando a ata sair");
    const item = recolhida.closest("li")!;
    vi.useFakeTimers();

    fireEvent.mouseEnter(item);
    act(() => vi.advanceTimersByTime(149));
    expect(aberta("Aviso quando a ata sair")).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    const texto = aberta("Aviso quando a ata sair")!;
    expect(within(texto).getByText("o aviso chega quando a ata sai.")).toBeTruthy();
    expect(within(texto).getByRole("button", { name: "Abrir o card" })).toBeTruthy();
    expect(within(texto).getByRole("button", { name: "Copiar link" })).toBeTruthy();
    expect(recolhida.getAttribute("aria-expanded")).toBe("true");

    fireEvent.mouseLeave(item);
    act(() => vi.advanceTimersByTime(179));
    expect(aberta("Aviso quando a ata sair")).not.toBeNull();
    act(() => vi.advanceTimersByTime(1));
    expect(aberta("Aviso quando a ata sair")).toBeNull();
  });

  it("o clique fixa a linha, e abrir outra fecha a anterior", async () => {
    comMovimentoReduzido();
    montar();
    const primeira = await linha("Aviso quando a ata sair");
    const segunda = await linha("Relatório por setor");
    const terceira = await linha("Filtro por setor");
    vi.useFakeTimers();

    fireEvent.click(primeira);
    fireEvent.mouseLeave(primeira.closest("li")!);
    act(() => vi.advanceTimersByTime(1000));
    expect(aberta("Aviso quando a ata sair")).not.toBeNull();

    fireEvent.click(segunda);
    expect(aberta("Relatório por setor")).not.toBeNull();
    expect(aberta("Aviso quando a ata sair")).toBeNull();

    // Pelo mouse também: solta a fixa e passa por outra linha.
    fireEvent.click(segunda);
    fireEvent.mouseEnter(primeira.closest("li")!);
    act(() => vi.advanceTimersByTime(150));
    fireEvent.mouseLeave(primeira.closest("li")!);
    fireEvent.mouseEnter(terceira.closest("li")!);
    act(() => vi.advanceTimersByTime(150));
    expect(aberta("Filtro por setor")).not.toBeNull();
    expect(aberta("Aviso quando a ata sair")).toBeNull();
  });

  it("o botão Demonstração só existe quando o card tem link, e abre em outra aba", async () => {
    comMovimentoReduzido();
    montar();

    fireEvent.click(await linha("Aviso quando a ata sair"));
    const demonstracao = within(aberta("Aviso quando a ata sair")!).getByRole("link", { name: "Demonstração" });
    expect(demonstracao.getAttribute("href")).toBe("https://manual-hsm.vercel.app/demonstracao/aviso");
    expect(demonstracao.getAttribute("target")).toBe("_blank");

    fireEvent.click(await linha("Botão de responder sumiu"));
    expect(within(aberta("Botão de responder sumiu")!).queryByText("Demonstração")).toBeNull();
  });

  it("Abrir o card abre o Documento do card no painel, e o X fecha", async () => {
    comMovimentoReduzido();
    montar();
    fireEvent.click(await linha("Aviso quando a ata sair"));
    expect(screen.queryByRole("region", { name: TITULO_DOCUMENTO })).toBeNull();

    fireEvent.click(within(aberta("Aviso quando a ata sair")!).getByRole("button", { name: "Abrir o card" }));

    const painel = screen.getByRole("complementary", { name: "Pedido aberto" });
    const documento = within(painel).getByRole("region", { name: TITULO_DOCUMENTO });
    expect(within(documento).getByText("Demanda 42")).toBeTruthy();
    fireEvent.click(within(painel).getByRole("button", { name: "Fechar o pedido" }));
    expect(screen.queryByRole("complementary", { name: "Pedido aberto" })).toBeNull();
  });

  it("Copiar link copia o Link da Demanda", async () => {
    comMovimentoReduzido();
    const escrever = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: escrever } });
    montar();
    fireEvent.click(await linha("Aviso quando a ata sair"));

    fireEvent.click(within(aberta("Aviso quando a ata sair")!).getByRole("button", { name: "Copiar link" }));

    await waitFor(() =>
      expect(escrever).toHaveBeenCalledWith(
        `Demanda 42: Aviso quando a ata sair\n${window.location.origin}/admin/tecnologia?demanda=e-1`,
      ),
    );
  });

  it("o card sem O que muda mostra Descrição em preparação", async () => {
    comMovimentoReduzido();
    montar();

    fireEvent.click(await linha("Relatório por setor"));

    expect(within(aberta("Relatório por setor")!).getByText(SEM_O_QUE_MUDA)).toBeTruthy();
  });

  it("a linha abre com o deslize curto, e sem ele com movimento reduzido", async () => {
    montar();
    fireEvent.click(await linha("Aviso quando a ata sair"));
    expect(aberta("Aviso quando a ata sair")!.classList.contains("animate-fade-in-up")).toBe(true);
    cleanup();

    comMovimentoReduzido();
    montar();
    fireEvent.click(await linha("Aviso quando a ata sair"));
    expect(aberta("Aviso quando a ata sair")!.classList.contains("animate-fade-in-up")).toBe(false);
  });
});

describe("Os filtros combinam", () => {
  it("tipo, Origem e Responsável vão juntos na consulta, sem período nem agrupamento", async () => {
    montar();
    await lista();
    expect(screen.queryByLabelText("De")).toBeNull();
    expect(screen.queryByRole("button", { name: "Por mês" })).toBeNull();

    fireEvent.click(within(screen.getByRole("group", { name: "Tipo" })).getByRole("button", { name: "Melhoria" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Vitta" }));
    fireEvent.click(
      within(screen.getByRole("group", { name: "Responsável" })).getByRole("button", { name: "Pedro Rib" }),
    );

    await waitFor(() => expect(ultimaConsulta()).toEqual({ tipo: "melhoria", origem: "vitta", responsavel: "P4" }));
  });

  it("clicar de novo num filtro marcado o desliga", async () => {
    montar();
    await lista();
    const origem = within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Vitta" });

    fireEvent.click(origem);
    await waitFor(() => expect(ultimaConsulta().origem).toBe("vitta"));
    fireEvent.click(origem);

    await waitFor(() => expect(ultimaConsulta()).toEqual({}));
  });
});

/**
 * O clique numa semana do gráfico (issue #1704, ADR 0092, decisão 4). 600 px:
 * o eixo dos números ocupa os primeiros 32 e a margem os últimos 8, e cada uma
 * das 12 semanas tem uns 47 px. A última (09/11) fica perto de 565, a de 26/10
 * (sem entrega na lista) perto de 475.
 */
const X_DA_SEMANA = { "2026-11-09": 565, "2026-10-26": 475 } as const;

function clicarNaSemana(container: HTMLElement, inicio: keyof typeof X_DA_SEMANA) {
  const grafico = container.querySelector(".recharts-wrapper")!;
  fireEvent.mouseMove(grafico, { clientX: X_DA_SEMANA[inicio], clientY: 100 });
  fireEvent.click(grafico, { clientX: X_DA_SEMANA[inicio], clientY: 100 });
}

const cabecalhos = async () => within(await lista()).queryAllByRole("heading").map((h) => h.textContent);

const marcadas = (container: HTMLElement) =>
  [...container.querySelectorAll<SVGRectElement>('rect[data-marcada="true"]')].map((barra) => barra.dataset.serie);

describe("O clique numa semana do gráfico", () => {
  it("filtra a lista para a semana, marca a barra e mostra o botão de desfazer", async () => {
    comMovimentoReduzido();
    const rolar = vi.fn();
    Element.prototype.scrollIntoView = rolar;
    const { container } = montar();
    await lista();

    clicarNaSemana(container, "2026-11-09");

    expect(await cabecalhos()).toEqual(["Semana de 09/11: 3 entregas (1 G, 2 P)"]);
    expect(within(await lista()).getByRole("button", { name: "Semana de 09/11, mostrar todas" })).toBeTruthy();
    expect(marcadas(container).sort()).toEqual(["g", "m", "p", "pedidos"]);
    expect(rolar).toHaveBeenCalled();
  });

  it("clicar de novo na barra volta à lista inteira", async () => {
    comMovimentoReduzido();
    Element.prototype.scrollIntoView = vi.fn();
    const { container } = montar();
    await lista();

    clicarNaSemana(container, "2026-11-09");
    clicarNaSemana(container, "2026-11-09");

    expect(await cabecalhos()).toEqual(["Semana de 09/11: 3 entregas (1 G, 2 P)", "Semana de 02/11: 1 entrega (1 M)"]);
    expect(screen.queryByRole("button", { name: /mostrar todas/ })).toBeNull();
    expect(marcadas(container)).toEqual([]);
  });

  it("o botão de desfazer volta à lista inteira", async () => {
    comMovimentoReduzido();
    Element.prototype.scrollIntoView = vi.fn();
    const { container } = montar();
    await lista();
    clicarNaSemana(container, "2026-11-09");

    fireEvent.click(within(await lista()).getByRole("button", { name: "Semana de 09/11, mostrar todas" }));

    expect(await cabecalhos()).toEqual(["Semana de 09/11: 3 entregas (1 G, 2 P)", "Semana de 02/11: 1 entrega (1 M)"]);
    expect(marcadas(container)).toEqual([]);
  });

  it("a semana sem entrega diz que nada saiu nela", async () => {
    comMovimentoReduzido();
    Element.prototype.scrollIntoView = vi.fn();
    const { container } = montar();
    await lista();

    clicarNaSemana(container, "2026-10-26");

    expect(await cabecalhos()).toEqual([]);
    expect(within(await lista()).getByText("Nenhuma entrega nesta semana.")).toBeTruthy();
    expect(within(await lista()).getByRole("button", { name: "Semana de 26/10, mostrar todas" })).toBeTruthy();
  });

  it("os filtros continuam valendo com a semana filtrada", async () => {
    comMovimentoReduzido();
    Element.prototype.scrollIntoView = vi.fn();
    const { container } = montar((url) => {
      const corpo = resposta();
      if (!url.includes("tipo=bug")) return corpo;
      return {
        ...corpo,
        grupos: [{ ...corpo.grupos[0], entregas: corpo.grupos[0].entregas.filter((e) => e.classificacao === "bug") }],
      };
    });
    await lista();
    clicarNaSemana(container, "2026-11-09");

    fireEvent.click(within(screen.getByRole("group", { name: "Tipo" })).getByRole("button", { name: "Bug" }));

    await waitFor(async () => expect(await cabecalhos()).toEqual(["Semana de 09/11: 1 entrega (1 P)"]));
    expect(ultimaConsulta()).toEqual({ tipo: "bug" });
    expect(within(await lista()).getByRole("button", { name: "Semana de 09/11, mostrar todas" })).toBeTruthy();
  });
});

/** O bloco das 12 semanas antes de 24/08, e o corte do bloco seguinte. */
function blocoAnterior(proximoCorte: string | null) {
  return {
    ...resposta(),
    grupos: [
      {
        inicio: "2026-08-10",
        entregas: [{ ...entrega("e-9", "Escala de agosto"), tamanho: "P", fechada_em: "2026-08-11T12:00:00Z" }],
      },
    ],
    proximo_corte: proximoCorte,
  };
}

describe("Ver semanas anteriores", () => {
  const verAnteriores = async () => within(await lista()).findByRole("button", { name: "Ver semanas anteriores" });

  it("carrega o bloco seguinte embaixo do que já está na tela, e some quando não há mais", async () => {
    comMovimentoReduzido();
    montar((url) => {
      const corte = new URL(url, "http://x").searchParams.get("corte");
      if (corte === "2026-08-24") return blocoAnterior("2026-06-01");
      if (corte === "2026-06-01") return { ...blocoAnterior(null), grupos: [] };
      return { ...resposta(), proximo_corte: "2026-08-24" };
    });

    fireEvent.click(await verAnteriores());

    await waitFor(async () =>
      expect(await cabecalhos()).toEqual([
        "Semana de 09/11: 3 entregas (1 G, 2 P)",
        "Semana de 02/11: 1 entrega (1 M)",
        "Semana de 10/08: 1 entrega (1 P)",
      ]),
    );
    expect(ultimaConsulta()).toEqual({ corte: "2026-08-24" });

    fireEvent.click(await verAnteriores());

    await waitFor(() => expect(ultimaConsulta()).toEqual({ corte: "2026-06-01" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Ver semanas anteriores" })).toBeNull());
    expect(await cabecalhos()).toHaveLength(3);
  });

  it("o botão não aparece quando não há entrega mais antiga", async () => {
    comMovimentoReduzido();
    montar(() => ({ ...resposta(), proximo_corte: null }));
    await lista();

    expect(screen.queryByRole("button", { name: "Ver semanas anteriores" })).toBeNull();
  });

  it("os filtros valem nos blocos carregados, e trocar o filtro recomeça das 12 semanas", async () => {
    comMovimentoReduzido();
    montar((url) =>
      new URL(url, "http://x").searchParams.get("corte")
        ? blocoAnterior(null)
        : { ...resposta(), proximo_corte: "2026-08-24" },
    );
    await lista();
    fireEvent.click(within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Vitta" }));
    await waitFor(() => expect(ultimaConsulta()).toEqual({ origem: "vitta" }));

    fireEvent.click(await verAnteriores());

    await waitFor(() => expect(ultimaConsulta()).toEqual({ origem: "vitta", corte: "2026-08-24" }));
    await waitFor(async () => expect(await cabecalhos()).toHaveLength(3));

    fireEvent.click(within(screen.getByRole("group", { name: "Tipo" })).getByRole("button", { name: "Melhoria" }));

    await waitFor(() => expect(ultimaConsulta()).toEqual({ origem: "vitta", tipo: "melhoria" }));
    await waitFor(async () => expect(await cabecalhos()).toHaveLength(2));
  });
});
