import { describe, expect, it } from "vitest";

import { calcularFit } from "./fit";

describe("calcularFit", () => {
  it("SVG mais largo que o container: reduz até caber na largura, centrado", () => {
    // Diagrama de 1600x400 num palco de 800x600: a largura manda (800/1600).
    const fit = calcularFit({ largura: 1600, altura: 400 }, { largura: 800, altura: 600 });
    expect(fit.escala).toBe(0.5);
    expect(fit.pan).toEqual({ x: 0, y: 0 });
  });

  it("SVG mais alto que o container: reduz até caber na altura", () => {
    // Diagrama de 600x1200 num palco de 800x600: a altura manda (600/1200).
    const fit = calcularFit({ largura: 600, altura: 1200 }, { largura: 800, altura: 600 });
    expect(fit.escala).toBe(0.5);
    expect(fit.pan).toEqual({ x: 0, y: 0 });
  });

  it("SVG menor que o container: não amplia além de 100%", () => {
    const fit = calcularFit({ largura: 400, altura: 300 }, { largura: 800, altura: 600 });
    expect(fit.escala).toBe(1);
    expect(fit.pan).toEqual({ x: 0, y: 0 });
  });

  it("container degenerado (sem medida útil): mantém 100% centrado", () => {
    // Palco ainda sem layout (medida zero) ou medida inválida não pode zerar a
    // escala nem produzir NaN: o fit neutro é 100% na origem.
    const svg = { largura: 600, altura: 400 };
    for (const container of [
      { largura: 0, altura: 600 },
      { largura: 800, altura: 0 },
      { largura: NaN, altura: 600 },
      { largura: -10, altura: 600 },
    ]) {
      expect(calcularFit(svg, container)).toEqual({ escala: 1, pan: { x: 0, y: 0 } });
    }
  });
});
