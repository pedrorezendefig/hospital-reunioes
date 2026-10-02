/**
 * @vitest-environment jsdom
 */

/**
 * O ranking das Áreas do site na tela Dados do Google (issue #818).
 *
 * Porte do teste do ranking da Central antiga (`BranchRanking.test.tsx`), com
 * o nome novo. O ranking chega pronto do backend, na ordem, com a variação já
 * calculada: a tela só escreve e desenha as barras.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RankingAreasDoSite, type AreaDoPayload } from "./RankingAreasDoSite";

afterEach(cleanup);

const AREAS: AreaDoPayload[] = [
  {
    chave: "maternidade",
    nome: "Maternidade",
    descricao: "Estrutura, preparativos, amamentação",
    visitas: 9842,
    visitas_anterior: 9267,
    variacao: 0.062,
  },
  {
    chave: "emergencia",
    nome: "Emergência 24h",
    descricao: "Adulto, pediátrica, obstétrica, ortopédica",
    visitas: 7610,
    visitas_anterior: 7381,
    variacao: 0.031,
  },
  {
    chave: "centro-de-imagem",
    nome: "Centro de Imagem",
    descricao: "Diagnóstico por imagem",
    visitas: 5230,
    visitas_anterior: 5283,
    variacao: -0.01,
  },
];

function area(parcial: Partial<AreaDoPayload>): AreaDoPayload {
  return {
    chave: "laboratorio",
    nome: "Laboratório",
    descricao: "Exames e resultados",
    visitas: 100,
    visitas_anterior: 100,
    variacao: 0,
    ...parcial,
  };
}

const itens = () => within(screen.getByRole("list", { name: "Áreas do site por Visitas" })).getAllByRole("listitem");

/** O texto que o leitor de tela lê do trecho: tudo, menos o que está escondido dele (`aria-hidden`). */
function lidoPeloLeitorDeTela(elemento: HTMLElement): string {
  const copia = elemento.cloneNode(true) as HTMLElement;
  copia.querySelectorAll('[aria-hidden="true"]').forEach((escondido) => escondido.remove());
  return (copia.textContent ?? "").replace(/\s+/g, " ").trim();
}

describe("RankingAreasDoSite", () => {
  it("lista as Áreas na ordem recebida, com o nome e o que cada uma reúne", () => {
    render(<RankingAreasDoSite areas={AREAS} />);

    expect(itens()).toHaveLength(3);
    expect(within(itens()[0]).getByText("Maternidade")).toBeTruthy();
    expect(within(itens()[0]).getByText("Estrutura, preparativos, amamentação")).toBeTruthy();
    expect(within(itens()[2]).getByText("Centro de Imagem")).toBeTruthy();
  });

  it("mostra as Visitas de cada Área em pt-BR", () => {
    render(<RankingAreasDoSite areas={AREAS} />);

    expect(within(itens()[0]).getByText("9.842")).toBeTruthy();
    expect(within(itens()[1]).getByText("7.610")).toBeTruthy();
  });

  it("a barra da líder fica cheia e as outras, na proporção dela", () => {
    render(<RankingAreasDoSite areas={AREAS} />);

    const barras = itens().map((item) => within(item).getByTestId("barra").style.width);
    // 7.610 de 9.842 é 77,32%; 5.230 de 9.842 é 53,14%.
    expect(barras).toEqual(["100%", "77.32%", "53.14%"]);
  });

  it("as barras têm as cores dos tokens do app", () => {
    render(<RankingAreasDoSite areas={AREAS} />);

    const barra = within(itens()[0]).getByTestId("barra");
    expect(barra.style.backgroundColor).toBe("var(--color-primary)");
    expect((barra.parentElement as HTMLElement).style.backgroundColor).toBe("var(--color-border)");
  });

  it("marca alta com a seta para cima e queda com a seta para baixo", () => {
    render(<RankingAreasDoSite areas={AREAS} />);

    expect(within(itens()[0]).getByText("↑ 6,2%")).toBeTruthy();
    expect(within(itens()[1]).getByText("↑ 3,1%")).toBeTruthy();
    expect(within(itens()[2]).getByText("↓ 1,0%")).toBeTruthy();
  });

  it("o leitor de tela anuncia o sentido da variação de cada Área, e não a seta", () => {
    // Revisão do PR #833 (#834): o `aria-label` num `<p>` não é anunciado (a
    // ARIA 1.2 proíbe nome acessível em parágrafo), e o leitor lia só "6,2%",
    // sem dizer se subiu ou caiu. O sentido vai no texto que ele lê.
    const { container } = render(<RankingAreasDoSite areas={AREAS} />);

    expect(lidoPeloLeitorDeTela(itens()[0])).toContain("subiu 6,2% em relação ao período anterior");
    expect(lidoPeloLeitorDeTela(itens()[1])).toContain("subiu 3,1% em relação ao período anterior");
    expect(lidoPeloLeitorDeTela(itens()[2])).toContain("caiu 1,0% em relação ao período anterior");
    expect(itens().map(lidoPeloLeitorDeTela).join(" ")).not.toMatch(/↑|↓/);
    expect(container.querySelectorAll("p[aria-label]")).toHaveLength(0);
  });

  it("sem visita no período anterior, não mostra variação", () => {
    render(<RankingAreasDoSite areas={[area({ visitas: 100, visitas_anterior: 0, variacao: null })]} />);

    expect(screen.queryByText(/↑|↓/)).toBeNull();
  });

  it("estável (variação zero), não mostra seta", () => {
    render(<RankingAreasDoSite areas={[area({ visitas: 500, visitas_anterior: 500, variacao: 0 })]} />);

    expect(screen.queryByText(/↑|↓/)).toBeNull();
  });

  it("todas sem visita: as barras ficam vazias, sem dividir por zero", () => {
    render(
      <RankingAreasDoSite
        areas={[area({ chave: "maternidade", visitas: 0 }), area({ chave: "laboratorio", visitas: 0 })]}
      />,
    );

    expect(itens().map((item) => within(item).getByTestId("barra").style.width)).toEqual(["0%", "0%"]);
    expect(itens().map((item) => within(item).getByText("0").textContent)).toEqual(["0", "0"]);
  });

  it("sem Área nenhuma, diz que não há dado em vez de uma lista vazia", () => {
    render(<RankingAreasDoSite areas={[]} />);

    expect(screen.getByText("Sem dados de Áreas do site para este período.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
