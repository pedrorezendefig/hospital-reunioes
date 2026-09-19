/**
 * O que os gráficos de Dados do Google decidem antes de desenhar (issue #817).
 *
 * Regras puras, sem `recharts`: quais dias ganham rótulo no eixo (poucos, para
 * caber no celular), quando a linha do período anterior entra, e a cor de cada
 * série, que é sempre um token do app.
 */

import { describe, expect, it } from "vitest";

import { COR_DO_DISPOSITIVO, marcasDoEixo, temAnterior } from "./graficos";

describe("marcasDoEixo", () => {
  it("no máximo 4 rótulos no eixo, com o primeiro e o último dia", () => {
    expect(marcasDoEixo(7)).toEqual([0, 2, 4, 6]);
    expect(marcasDoEixo(28)).toEqual([0, 9, 18, 27]);
    expect(marcasDoEixo(90)).toEqual([0, 30, 59, 89]);
  });

  it("série curta rotula todos os dias", () => {
    expect(marcasDoEixo(1)).toEqual([0]);
    expect(marcasDoEixo(2)).toEqual([0, 1]);
    expect(marcasDoEixo(3)).toEqual([0, 1, 2]);
  });

  it("sem dia nenhum, sem rótulo", () => {
    expect(marcasDoEixo(0)).toEqual([]);
  });
});

describe("temAnterior", () => {
  it("a linha do período anterior só entra quando ele teve visita", () => {
    expect(temAnterior([{ visitantes_anterior: 0 }, { visitantes_anterior: 12 }])).toBe(true);
    expect(temAnterior([{ visitantes_anterior: 0 }, { visitantes_anterior: 0 }])).toBe(false);
    expect(temAnterior([])).toBe(false);
  });
});

describe("COR_DO_DISPOSITIVO", () => {
  it("cada dispositivo tem a sua cor, e toda cor é um token do app", () => {
    const cores = Object.values(COR_DO_DISPOSITIVO);

    expect(new Set(cores).size).toBe(3);
    for (const cor of cores) expect(cor).toMatch(/^var\(--color-[a-z-]+\)$/);
  });
});
