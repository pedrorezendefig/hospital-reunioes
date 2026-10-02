/**
 * Há quanto tempo, em português de gente (issue #815, ADR 0058).
 *
 * Porte de `src/lib/relative-time.test.ts` do repositório antigo, inteiro. O
 * "agora" entra como argumento: a regra é pura, e quem lê o relógio é a barra
 * de frescor.
 */

import { describe, expect, it } from "vitest";

import { tempoRelativo } from "./tempo-relativo";

const minutos = (n: number) => n * 60_000;

describe("tempoRelativo", () => {
  it("menos de 1 minuto vira 'agora mesmo'", () => {
    expect(tempoRelativo(0, 30_000)).toBe("agora mesmo");
  });

  it("1 minuto no singular", () => {
    expect(tempoRelativo(0, minutos(1))).toBe("há 1 minuto");
  });

  it("vários minutos no plural", () => {
    expect(tempoRelativo(0, minutos(12))).toBe("há 12 minutos");
  });

  it("vira horas a partir de 60 minutos, no singular", () => {
    expect(tempoRelativo(0, minutos(60))).toBe("há 1 hora");
  });

  it("várias horas no plural", () => {
    expect(tempoRelativo(0, minutos(150))).toBe("há 2 horas");
  });

  it("nunca mostra tempo negativo", () => {
    // Relógio do navegador atrasado em relação ao do servidor.
    expect(tempoRelativo(1000, 0)).toBe("agora mesmo");
  });
});
