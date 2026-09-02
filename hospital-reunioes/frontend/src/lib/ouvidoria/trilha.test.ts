import { describe, expect, it } from "vitest";

import {
  descreverTempoDesdeOMarco,
  SEM_CONFIRMACAO_DO_CALENDARIO,
  type EventoDaTrilha,
} from "./trilha";

function evento(overrides: Partial<EventoDaTrilha> = {}): EventoDaTrilha {
  return {
    ocorrido_em: "2026-08-26T17:00:00+00:00",
    autor: "Carlos Titular",
    sistema: false,
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

describe("o tempo entre marcos da linha do tempo (issue #485)", () => {
  it("diz o tempo em dias e horas úteis e de onde ele conta", () => {
    // 540 minutos de expediente são exatamente um dia útil (9 horas).
    expect(descreverTempoDesdeOMarco(evento(), true)).toBe("1 dia útil desde a etapa Validação");
  });

  it("evento que não fecha marco não recebe tempo nenhum", () => {
    // O lembrete automático acontece DENTRO de um trecho: dar tempo a ele
    // quebraria a leitura de onde o caso emperrou.
    const lembrete = evento({ marco: null, desde_marco: null, desde_marco_rotulo: null, minutos_uteis: null });
    expect(descreverTempoDesdeOMarco(lembrete, true)).toBeNull();
  });

  it("o primeiro marco do caso não inventa tempo decorrido", () => {
    // Antes da entrada não houve caso, e zero ali diria que a Ouvidoria
    // recebeu e despachou no mesmo instante.
    const entrada = evento({ marco: "T0", desde_marco: null, desde_marco_rotulo: null, minutos_uteis: null });
    expect(descreverTempoDesdeOMarco(entrada, true)).toBeNull();
  });

  it("sem calendário confirmado o número sai da tela em vez de sair errado", () => {
    expect(descreverTempoDesdeOMarco(evento(), false)).toBe(SEM_CONFIRMACAO_DO_CALENDARIO);
  });

  it("menos de uma hora útil não vira zero", () => {
    expect(descreverTempoDesdeOMarco(evento({ minutos_uteis: 20 }), true)).toBe(
      "menos de uma hora útil desde a etapa Validação"
    );
  });
});
