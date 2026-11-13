/**
 * @vitest-environment jsdom
 */

/**
 * O cabeçalho fixo das colunas do Quadro da Tecnologia (issue #1642, ADR 0090,
 * decisão 3).
 *
 * O `<main>` do AppShell tem `overflow-auto` e cresce com o conteúdo: quem rola
 * é a página, e não ele. Um `sticky` dentro de uma caixa assim fica preso a
 * ela e some na rolagem da página. Com o Quadro na tela, o `globals.css` troca
 * o `overflow` do `<main>` por `clip` na horizontal, que corta o que sobra sem
 * virar caixa de rolagem, e o cabeçalho de cada coluna passa a ficar no topo.
 *
 * O teste lê a regra do `globals.css` real e confere em quem ela pega.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

const CSS = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

/** As regras do arquivo que falam do `<main>`, sem as camadas e o `@theme` do Tailwind. */
const REGRAS_DO_MAIN = CSS.match(/^main[^{]*\{[^}]*\}/gm) ?? [];

beforeAll(() => {
  const estilo = document.createElement("style");
  estilo.textContent = REGRAS_DO_MAIN.join("\n");
  document.head.appendChild(estilo);
});

afterEach(() => {
  document.body.innerHTML = "";
});

function main(conteudo: string): HTMLElement {
  document.body.innerHTML = `<main class="flex-1 p-4 md:p-8 overflow-auto">${conteudo}</main>`;
  return document.querySelector("main") as HTMLElement;
}

describe("O main da página com o Quadro (issue #1642)", () => {
  it("o globals.css tem a regra", () => {
    // O piso: sem ele, uma leitura errada do arquivo passaria vazia.
    expect(REGRAS_DO_MAIN.length).toBeGreaterThan(0);
  });

  it("com o Quadro, corta a sobra na horizontal sem virar caixa de rolagem", () => {
    const estilo = getComputedStyle(main('<div><section data-quadro=""></section></div>'));

    expect(estilo.overflowX).toBe("clip");
    expect(estilo.overflowY).toBe("visible");
  });

  it("sem o Quadro, o main fica como era", () => {
    const estilo = getComputedStyle(main("<section></section>"));

    expect(estilo.overflowX).not.toBe("clip");
  });
});
