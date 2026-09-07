import { describe, expect, it } from "vitest";

import { autorDoApagamento, estaApagado } from "./apagamento";
import type { EventoDaTrilha } from "./trilha";

const APAGADO_EM = "2031-09-01T12:00:00+00:00";

function evento(overrides: Partial<EventoDaTrilha> = {}): EventoDaTrilha {
  return {
    ocorrido_em: "2026-08-26T17:00:00+00:00",
    autor: "Carlos Titular",
    sistema: false,
    apagamento: false,
    marco: "T2",
    marco_rotulo: "Resposta da área",
    descricao: "Resposta da área recebida",
    texto: "Revisamos a escala do plantao noturno.",
    desde_marco: "T1",
    desde_marco_rotulo: "Validação",
    minutos_uteis: 540,
    ...overrides,
  };
}

describe("o carimbo que diz que o caso foi apagado (issue #593)", () => {
  it("o caso com o carimbo está apagado", () => {
    expect(estaApagado(APAGADO_EM)).toBe(true);
  });

  it("o caso vivo não está apagado, tenha ele o carimbo nulo ou nenhum", () => {
    // Nulo é o caso que existe e não foi apagado; indefinido é o frontend
    // servido enquanto o backend ainda é o da versão anterior, e ele não pode
    // acusar de apagado um caso inteiro.
    expect(estaApagado(null)).toBe(false);
    expect(estaApagado(undefined)).toBe(false);
  });
});

describe("quem apagou o caso, segundo a trilha (issue #593)", () => {
  it("o crédito sai do movimento marcado como apagamento", () => {
    const trilha = [
      evento({ autor: "Marta Ouvidora" }),
      evento({ autor: "Sistema (retenção)", sistema: true, apagamento: true }),
    ];

    expect(autorDoApagamento(trilha)).toBe("Sistema (retenção)");
  });

  it("trilha sem apagamento não credita ninguém", () => {
    // O caso vivo e a trilha que não pôde ser lida caem os dois aqui: inventar
    // um autor faria a tela assinar um ato que ela não conhece.
    expect(autorDoApagamento([evento(), evento({ sistema: true })])).toBeNull();
    expect(autorDoApagamento([])).toBeNull();
  });
});
