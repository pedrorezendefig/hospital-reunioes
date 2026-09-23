/**
 * @vitest-environment jsdom
 */

/**
 * As barras da Origem do público na tela Dados do Google (issue #818).
 *
 * Porte do teste da origem da Central antiga (`SourceBreakdown.test.tsx`). As
 * origens chegam prontas do backend: só as que tiveram Visita, na ordem, com
 * o rótulo gentil e a fatia em pontos percentuais, arredondada como lá.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BarrasOrigemDoPublico, type OrigemDoPayload } from "./BarrasOrigemDoPublico";

afterEach(cleanup);

// 8.640 Visitas, cada fatia arredondada sozinha: 65,97%, 20,83%, 9,26%, 3,47%
// e 0,46% (abaixo de 1%, 0 ponto).
const ORIGENS: OrigemDoPayload[] = [
  { chave: "busca", rotulo: "Busca no Google", visitas: 5700, percentual: 66 },
  { chave: "direto", rotulo: "Direto", visitas: 1800, percentual: 21 },
  { chave: "anuncios", rotulo: "Anúncios", visitas: 800, percentual: 9 },
  { chave: "outros", rotulo: "Outros", visitas: 300, percentual: 3 },
  { chave: "nao-identificado", rotulo: "Não identificado", visitas: 40, percentual: 0 },
];

const itens = () =>
  within(screen.getByRole("list", { name: "Visitas por Origem do público" })).getAllByRole("listitem");

describe("BarrasOrigemDoPublico", () => {
  it("mostra cada origem com o rótulo, a fatia e as Visitas", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(itens().map((item) => item.textContent)).toEqual([
      "Busca no Google66%5.700 visitas",
      "Direto21%1.800 visitas",
      "Anúncios9%800 visitas",
      "Outros3%300 visitas",
      "Não identificado<1%40 visitas",
    ]);
  });

  it("a barra de cada origem tem a largura da fatia", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(itens().map((item) => within(item).getByTestId("barra").style.width)).toEqual([
      "66%",
      "21%",
      "9%",
      "3%",
      "0%",
    ]);
  });

  it("o resto fica em cinza, atrás das origens, com as cores dos tokens do app", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(itens().map((item) => within(item).getByTestId("barra").style.backgroundColor)).toEqual([
      "var(--color-primary)",
      "var(--color-primary)",
      "var(--color-primary)",
      "var(--color-text-secondary)",
      "var(--color-text-secondary)",
    ]);
  });

  it("fatia de menos de 1% aparece como '<1%', e não zero", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(within(itens()[4]).getByText("<1%")).toBeTruthy();
    expect(within(itens()[4]).queryByText("0%")).toBeNull();
  });

  it("a Indicação é origem identificada: cor das origens e sem a nota do resto (#856)", () => {
    render(
      <BarrasOrigemDoPublico
        origens={[
          { chave: "busca", rotulo: "Busca no Google", visitas: 700, percentual: 70 },
          { chave: "indicacao", rotulo: "Indicação", visitas: 300, percentual: 30 },
        ]}
      />,
    );

    expect(itens()[1].textContent).toBe("Indicação30%300 visitas");
    expect(within(itens()[1]).getByTestId("barra").style.backgroundColor).toBe("var(--color-primary)");
    expect(screen.queryByText(/privacidade/)).toBeNull();
  });

  it("com Outros ou Não identificado, explica o que são", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(screen.getByText(/proteger a privacidade/)).toBeTruthy();
  });

  it("só com origens identificadas, não traz a explicação do resto", () => {
    render(<BarrasOrigemDoPublico origens={[{ chave: "busca", rotulo: "Busca no Google", visitas: 100, percentual: 100 }]} />);

    expect(screen.queryByText(/privacidade/)).toBeNull();
  });

  it("nunca mostra o termo cru da fonte", () => {
    render(<BarrasOrigemDoPublico origens={ORIGENS} />);

    expect(screen.queryByText(/not set|\(other\)|Unassigned/i)).toBeNull();
  });

  it("uma visita só, no singular", () => {
    render(<BarrasOrigemDoPublico origens={[{ chave: "direto", rotulo: "Direto", visitas: 1, percentual: 100 }]} />);

    expect(itens()[0].textContent).toBe("Direto100%1 visita");
  });

  it("sem origem nenhuma, diz que não há dado em vez de barras de zero", () => {
    render(<BarrasOrigemDoPublico origens={[]} />);

    expect(screen.getByText("Sem dados de Origem do público para este período.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
