/**
 * @vitest-environment jsdom
 */

/**
 * A página de Contas médicas do manual desenha o fluxograma dela (issue
 * #1724): o bloco do Markdown de verdade, lido do disco, vira o desenho do
 * Fluxograma, do envio à análise concluída, sem a mensagem de erro de bloco.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { carregarPaginasDoManual } from "@/lib/manual/carregar";
import { MarkdownDoManual } from "./MarkdownDoManual";

afterEach(() => {
  cleanup();
});

describe("a página de Contas médicas no manual", () => {
  it("desenha o fluxograma do caminho da conta, do envio à análise concluída, sem erro de bloco", () => {
    const contas = carregarPaginasDoManual().find((p) => p.modulo === "contas-medicas")!;

    const { container } = render(<MarkdownDoManual pasta={contas.pasta}>{contas.corpo}</MarkdownDoManual>);

    expect(container.querySelector('[data-fluxograma] [data-passo="envio"]')).not.toBeNull();
    expect(container.querySelector('[data-fluxograma] [data-passo="concluida"]')).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
