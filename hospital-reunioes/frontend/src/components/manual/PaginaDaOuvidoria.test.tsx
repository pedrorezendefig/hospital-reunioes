/**
 * @vitest-environment jsdom
 */

/**
 * A página de Ouvidoria do manual desenha o fluxograma dela (issue #1723): o
 * bloco do Markdown de verdade, lido do disco, vira o desenho do Fluxograma,
 * sem a mensagem de erro de bloco no lugar.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { carregarPaginasDoManual } from "@/lib/manual/carregar";
import { MarkdownDoManual } from "./MarkdownDoManual";

afterEach(() => {
  cleanup();
});

describe("a página de Ouvidoria no manual", () => {
  it("desenha o fluxograma do caminho da manifestação, da chegada ao encerramento, sem erro de bloco", () => {
    const ouvidoria = carregarPaginasDoManual().find((p) => p.modulo === "ouvidoria")!;

    const { container } = render(
      <MarkdownDoManual pasta={ouvidoria.pasta}>{ouvidoria.corpo}</MarkdownDoManual>
    );

    expect(container.querySelector('[data-fluxograma] [data-passo="chega"]')).not.toBeNull();
    expect(container.querySelector('[data-fluxograma] [data-passo="encerrar"]')).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
