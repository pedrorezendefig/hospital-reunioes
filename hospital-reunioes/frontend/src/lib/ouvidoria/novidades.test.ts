/**
 * A régua do distintivo de novidades (issue #487, RN-69).
 *
 * O teste que importa aqui é o do meio: falha de leitura e ausência de
 * novidade desenham telas parecidas, e quem confundir as duas faz o menu
 * afirmar "nada novo" com uma contagem que nunca chegou.
 */

import { describe, expect, it } from "vitest";

import { distintivoDeNovidades } from "./novidades";

describe("distintivo de novidades", () => {
  it("mostra o total quando há casos com novidade", () => {
    expect(distintivoDeNovidades({ estado: "ok", total: 3 })?.texto).toBe("3");
  });

  it("some quando não há novidade nenhuma", () => {
    expect(distintivoDeNovidades({ estado: "ok", total: 0 })).toBeNull();
  });

  it("some enquanto a contagem não chegou", () => {
    expect(distintivoDeNovidades({ estado: "sem_contagem" })).toBeNull();
  });

  it("contagem que falhou não vira zero: o distintivo fica, sem número", () => {
    const distintivo = distintivoDeNovidades({ estado: "indisponivel" });

    expect(distintivo).not.toBeNull();
    expect(distintivo?.texto).not.toBe("0");
    expect(distintivo?.rotulo).toContain("Não foi possível contar");
  });

  it("o rótulo concorda no singular", () => {
    expect(distintivoDeNovidades({ estado: "ok", total: 1 })?.rotulo).toBe(
      "1 caso com novidade"
    );
  });

  it("o rótulo diz o total, e não o texto encurtado", () => {
    const distintivo = distintivoDeNovidades({ estado: "ok", total: 214 });

    expect(distintivo?.texto).toBe("99+");
    expect(distintivo?.rotulo).toBe("214 casos com novidade");
  });
});
