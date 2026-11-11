/**
 * @vitest-environment jsdom
 */

/**
 * A aba Entregas (issue #1556, PRD #1548, ADR 0084, decisão 8).
 *
 * Quem conta, filtra e corta o que não foi entregue é o servidor (os testes
 * dele estão em `test_tecnologia_entregas.py`). Aqui se cobra o que a tela faz
 * com isso: a contagem por período, a lista com as datas e o Responsável, os
 * filtros que viram a consulta, e o clique que abre o Documento do card.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TITULO_DOCUMENTO } from "./DocumentoDoCard";
import { EntregasDaTecnologia } from "./EntregasDaTecnologia";

const URL_DAS_ENTREGAS = "/api/admin/tecnologia/entregas";

function resposta(agrupar: "semana" | "mes" = "semana") {
  return {
    agrupar,
    periodos:
      agrupar === "mes"
        ? [{ inicio: "2026-11-01", total: 3 }]
        : [
            { inicio: "2026-11-02", total: 2 },
            { inicio: "2026-10-26", total: 1 },
          ],
    entregas: [
      {
        id: "e-1",
        titulo: "Aviso quando a ata sair",
        etapa: "em_producao",
        tem_vinculo: true,
        o_que_muda: "**O que muda:** o aviso chega quando a ata sai.",
        partes: [],
        fechada_em: "2026-11-03T12:00:00Z",
        em_producao_em: "2026-11-04T15:00:00Z",
        responsavel: "Pedro Rib",
        classificacao: "melhoria",
        origem: "vitta",
      },
      {
        id: "e-2",
        titulo: "Botão de responder sumiu",
        etapa: "entregue",
        tem_vinculo: true,
        o_que_muda: null,
        partes: [],
        fechada_em: "2026-11-02T12:00:00Z",
        em_producao_em: null,
        responsavel: "Pedro Vitta",
        classificacao: "bug",
        origem: "diretor",
      },
    ],
    responsaveis: [
      { valor: "P4", nome: "Pedro Rib" },
      { valor: "P1", nome: "Pedro Vitta" },
    ],
  };
}

let pedidos: string[] = [];

function montar() {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      const agrupar = new URL(url, "http://x").searchParams.get("agrupar") === "mes" ? "mes" : "semana";
      return { ok: true, status: 200, json: async () => resposta(agrupar) } as unknown as Response;
    }),
  );
  render(<EntregasDaTecnologia token="token-de-teste" />);
}

/** A consulta do último pedido, sem a ordem dos parâmetros. */
function ultimaConsulta(): Record<string, string> {
  const ultima = pedidos[pedidos.length - 1];
  return Object.fromEntries(new URL(ultima, "http://x").searchParams.entries());
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A contagem por período", () => {
  it("mostra quantos cards foram entregues em cada semana", async () => {
    montar();

    const contagem = await screen.findByRole("list", { name: "Entregues por período" });
    const linhas = within(contagem).getAllByRole("listitem").map((li) => li.textContent);
    expect(linhas).toEqual(["Semana de 02/11/2026: 2", "Semana de 26/10/2026: 1"]);
    expect(pedidos[0].startsWith(URL_DAS_ENTREGAS)).toBe(true);
  });

  it("troca para a contagem por mês", async () => {
    montar();
    await screen.findByRole("list", { name: "Entregues por período" });

    fireEvent.click(screen.getByRole("button", { name: "Por mês" }));

    await waitFor(() => expect(ultimaConsulta().agrupar).toBe("mes"));
    const contagem = await screen.findByRole("list", { name: "Entregues por período" });
    await waitFor(() =>
      expect(within(contagem).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
        "Novembro de 2026: 3",
      ]),
    );
  });
});

describe("A lista dos entregues", () => {
  it("mostra a data de entrega, a data em produção e o Responsável", async () => {
    montar();

    const lista = await screen.findByRole("list", { name: "Cards entregues" });
    const [primeiro, segundo] = within(lista).getAllByRole("listitem");
    expect(within(primeiro).getByText("Aviso quando a ata sair")).toBeTruthy();
    expect(within(primeiro).getByText("Entregue em 03/11/2026")).toBeTruthy();
    expect(within(primeiro).getByText("Em produção em 04/11/2026")).toBeTruthy();
    expect(within(primeiro).getByText("Responsável: Pedro Rib")).toBeTruthy();
    // A entrega que ainda não subiu não ganha a linha de produção.
    expect(within(segundo).getByText("Entregue em 02/11/2026")).toBeTruthy();
    expect(within(segundo).queryByText(/Em produção em/)).toBeNull();
  });

  it("o clique num card abre o Documento do card", async () => {
    montar();
    const lista = await screen.findByRole("list", { name: "Cards entregues" });
    expect(screen.queryByRole("region", { name: TITULO_DOCUMENTO })).toBeNull();

    fireEvent.click(within(lista).getByRole("button", { name: /Aviso quando a ata sair/ }));

    const documento = screen.getByRole("region", { name: TITULO_DOCUMENTO });
    expect(within(documento).getByText("o aviso chega quando a ata sai.")).toBeTruthy();
  });
});

describe("Os filtros combinam", () => {
  it("período, tipo, Origem e Responsável vão juntos na consulta", async () => {
    montar();
    await screen.findByRole("list", { name: "Cards entregues" });

    fireEvent.change(screen.getByLabelText("De"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "2026-10-31" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Tipo" })).getByRole("button", { name: "Melhoria" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Vitta" }));
    fireEvent.click(
      within(screen.getByRole("group", { name: "Responsável" })).getByRole("button", { name: "Pedro Rib" }),
    );

    await waitFor(() =>
      expect(ultimaConsulta()).toEqual({
        agrupar: "semana",
        de: "2026-10-01",
        ate: "2026-10-31",
        tipo: "melhoria",
        origem: "vitta",
        responsavel: "P4",
      }),
    );
  });

  it("clicar de novo num filtro marcado o desliga", async () => {
    montar();
    await screen.findByRole("list", { name: "Cards entregues" });
    const origem = within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Vitta" });

    fireEvent.click(origem);
    await waitFor(() => expect(ultimaConsulta().origem).toBe("vitta"));
    fireEvent.click(origem);

    await waitFor(() => expect(ultimaConsulta()).toEqual({ agrupar: "semana" }));
  });
});
