/**
 * @vitest-environment jsdom
 */

/**
 * Os títulos de uma página do manual saem em Caixa alta (issue #1718, ADR 0080).
 *
 * O jsdom não aplica o `@layer base`; a régua `apareceComoFoiEscrito` é a dos
 * testes de componente e segue a mesma lista de elementos da regra base.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { apareceComoFoiEscrito } from "@/lib/caixa-alta";
import { MarkdownDoManual } from "./MarkdownDoManual";

afterEach(() => {
  cleanup();
});

const PAGINA = [
  "# Reuniões e Pendências",
  "## Ver as reuniões do mês",
  "### Filtrar por setor",
  "Abra o calendário e escolha o mês.",
].join("\n\n");

describe("os títulos do Markdown do manual", () => {
  it.each([
    ["#", "Reuniões e Pendências"],
    ["##", "Ver as reuniões do mês"],
    ["###", "Filtrar por setor"],
  ])("o título %s sai em caixa alta", (_nivel, titulo) => {
    render(<MarkdownDoManual pasta="reunioes-e-pendencias">{PAGINA}</MarkdownDoManual>);

    const heading = screen.getByRole("heading", { name: titulo });
    expect(apareceComoFoiEscrito(heading)).toBe(false);
  });

  it("o texto corrido fica como foi escrito", () => {
    render(<MarkdownDoManual pasta="reunioes-e-pendencias">{PAGINA}</MarkdownDoManual>);

    expect(apareceComoFoiEscrito(screen.getByText("Abra o calendário e escolha o mês."))).toBe(true);
  });
});

describe("o bloco fluxograma da página", () => {
  it("vira o desenho do Fluxograma, e não o texto cru do bloco", () => {
    const pagina = [
      "O caminho:",
      "```fluxograma",
      "inicio criar 1,1: Criar o POP",
      "fim publicada 2,1: Versão publicada",
      "criar -> publicada",
      "```",
    ].join("\n");
    const { container } = render(<MarkdownDoManual pasta="pops">{pagina}</MarkdownDoManual>);

    expect(container.querySelector("[data-fluxograma] [data-passo=\"publicada\"]")).not.toBeNull();
    expect(container.querySelector("pre")).toBeNull();
  });
});
