/**
 * @vitest-environment jsdom
 */

/**
 * A tela Como funciona a Ouvidoria (issue #1629, PRD #1527, regra T9 da
 * especificação da Diretoria): o caso do começo ao fim em cinco passos, para a
 * pessoa nova tratar um caso sem abrir o manual.
 *
 * Os textos esperados saem da seção 4.14 do anexo, escritos aqui à mão: o
 * teste não lê a constante que a tela usa, senão um passo trocado no código
 * passaria por construção.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ComoFuncionaPage from "./page";

afterEach(cleanup);

describe("a tela Como funciona a Ouvidoria", () => {
  it("mostra os cinco passos da seção 4.14, na ordem", () => {
    render(<ComoFuncionaPage />);

    const passos = within(screen.getByRole("list", { name: "Os cinco passos de um caso" })).getAllByRole(
      "listitem"
    );
    const titulos = passos.map((passo) => within(passo).getByRole("heading").textContent);

    expect(titulos).toEqual([
      "A manifestação chega",
      "Você confere tipo, setor e gravidade",
      "Se o sistema alertar, decide sobre o NSP",
      "Envia à área e acompanha o prazo",
      "Revisa a resposta e envia ao manifestante",
    ]);
  });

  it("abre com a frase do topo dizendo para que serve", () => {
    render(<ComoFuncionaPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Como funciona a Ouvidoria" })).toBeTruthy();
    expect(screen.getByText("O caminho de um caso, da chegada ao encerramento, em cinco passos.")).toBeTruthy();
  });

  it("cabe no celular com rolagem curta: cada passo tem uma linha de explicação, curta", () => {
    // jsdom não mede altura. O que segura a rolagem curta é o texto: um título
    // e uma frase por passo, e nada de parágrafo. 140 caracteres a 375 px dão
    // umas três linhas de `text-sm`, e cinco passos assim cabem numa tela e
    // meia.
    render(<ComoFuncionaPage />);

    const passos = within(screen.getByRole("list", { name: "Os cinco passos de um caso" })).getAllByRole(
      "listitem"
    );
    for (const passo of passos) {
      const frases = passo.querySelectorAll("p");
      expect(frases).toHaveLength(1);
      expect(frases[0].textContent!.length).toBeLessThanOrEqual(140);
    }
  });

  it("tem uma ação principal só, que leva à fila", () => {
    render(<ComoFuncionaPage />);

    const link = screen.getByRole("link", { name: "Ir para a fila" });
    expect(link.getAttribute("href")).toBe("/ouvidoria");
  });
});
