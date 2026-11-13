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
import { carregarPaginasDoManual } from "@/lib/manual/carregar";
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

describe("o bloco fluxograma da página do manual", () => {
  it("a página de Ouvidoria desenha o fluxograma do caminho da manifestação, sem erro de bloco", () => {
    const ouvidoria = carregarPaginasDoManual().find((p) => p.modulo === "ouvidoria")!;

    const { container } = render(
      <MarkdownDoManual pasta={ouvidoria.pasta}>{ouvidoria.corpo}</MarkdownDoManual>
    );

    expect(container.querySelector("[data-fluxograma]")).not.toBeNull();
    expect(container.querySelector('[data-passo="chega"]')).not.toBeNull();
    expect(container.querySelector('[data-passo="encerrar"]')).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("outro bloco de código continua código", () => {
    const { container } = render(
      <MarkdownDoManual pasta="pops">{"```\nnpm run dev\n```"}</MarkdownDoManual>
    );

    expect(container.querySelector("[data-fluxograma]")).toBeNull();
    expect(container.querySelector("pre")?.textContent).toContain("npm run dev");
  });
});
