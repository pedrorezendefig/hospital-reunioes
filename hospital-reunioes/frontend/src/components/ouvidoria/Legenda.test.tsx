/**
 * @vitest-environment jsdom
 */

/**
 * A legenda dos estados da Ouvidoria (issue #1629, PRD #1527, regra T8 da
 * especificação da Diretoria): toda tela que mostra estado de caso diz o que
 * cada cor e cada estado querem dizer.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Legenda } from "./Legenda";

afterEach(cleanup);

function abrir() {
  render(<Legenda />);
  fireEvent.click(screen.getByRole("button", { name: "Legenda" }));
  return within(screen.getByRole("region", { name: "Legenda das cores e dos estados" }));
}

describe("a legenda das cores e dos estados", () => {
  it("nasce fechada, para não empurrar a lista todo dia", () => {
    render(<Legenda />);

    const botao = screen.getByRole("button", { name: "Legenda" });
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region", { name: "Legenda das cores e dos estados" })).toBeNull();
  });

  it("dá a cor e o significado de cada gravidade, nas cores do design system (seção 4.12)", () => {
    const legenda = abrir();

    const gravidades = within(legenda.getByRole("list", { name: "Gravidade" })).getAllByRole("listitem");
    expect(gravidades.map((item) => item.querySelector("strong")?.textContent)).toEqual([
      "Crítico",
      "Alto",
      "Médio",
      "Baixo",
    ]);
    expect(gravidades.map((item) => item.querySelector("[data-cor]")?.className)).toEqual([
      expect.stringContaining("bg-[#B3352B]"),
      expect.stringContaining("bg-[#C78A1A]"),
      expect.stringContaining("bg-[#1E4394]"),
      expect.stringContaining("bg-[#9BA1AB]"),
    ]);
    expect(gravidades[0].textContent).toContain("Risco à vida, à segurança ou à imagem.");
  });

  it("diz o que cada estado do caso quer dizer", () => {
    const legenda = abrir();

    const estados = within(legenda.getByRole("list", { name: "Estado do caso" })).getAllByRole("listitem");
    expect(estados.map((item) => item.querySelector("strong")?.textContent)).toEqual([
      "Nova",
      "Em classificação",
      "Aguardando área",
      "Aguardando manifestante",
      "Respondida",
      "Encerrada",
    ]);
    expect(estados[2].textContent).toContain("Enviado à área, com o prazo correndo.");
  });
});
