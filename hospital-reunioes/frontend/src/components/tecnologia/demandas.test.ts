/**
 * O Markdown simples do "O que muda", do lado da tela (issue #676, ADR 0054).
 *
 * As contas da Conversa e das menções saíram com a Conversa da Demanda na
 * issue #1386 (ADR 0077).
 */

import { describe, expect, it } from "vitest";

import { blocosDoTextoSimples } from "./demandas";

describe("O Markdown simples do O que muda", () => {
  it("separa parágrafo de lista", () => {
    const blocos = blocosDoTextoSimples("O card ganha a seção.\n\n- Vem do planejamento.\n- Ninguém reescreve.");

    expect(blocos.map((b) => b.lista)).toEqual([false, true]);
    expect(blocos[1].linhas.map((linha) => linha[0].texto)).toEqual(["Vem do planejamento.", "Ninguém reescreve."]);
  });

  it("linha em branco fecha o parágrafo", () => {
    // Sem isso os dois parágrafos virariam um só, e o texto sairia grudado.
    const blocos = blocosDoTextoSimples("Primeiro.\n\nSegundo.");

    expect(blocos).toHaveLength(2);
    expect(blocos.every((b) => b.linhas.length === 1)).toBe(true);
  });

  it("o negrito vira pedaço forte e o asterisco some", () => {
    const pedacos = blocosDoTextoSimples("**O que muda:** o card ganha a seção.")[0].linhas[0];

    expect(pedacos).toEqual([
      { texto: "O que muda:", forte: true },
      { texto: " o card ganha a seção.", forte: false },
    ]);
  });

  it("link do Markdown continua sendo texto", () => {
    // Nada que venha do GitHub vira elemento clicável na tela do diretor: o que
    // o parser não conhece fica como está, e não como um link.
    const pedacos = blocosDoTextoSimples("Veja [a issue](https://exemplo).")[0].linhas[0];

    expect(pedacos).toEqual([{ texto: "Veja [a issue](https://exemplo).", forte: false }]);
  });

  it("texto vazio ou nulo não vira bloco nenhum", () => {
    expect(blocosDoTextoSimples(null)).toEqual([]);
    expect(blocosDoTextoSimples("   \n  ")).toEqual([]);
  });
});
