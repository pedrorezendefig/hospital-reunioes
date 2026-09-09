import { describe, expect, it } from "vitest";

import { autorDoApagamento, estaApagado, podeApagar } from "./apagamento";
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

describe("quem pode apagar, e quando (issue #595, ADR 0047)", () => {
  it("a Diretoria apaga o caso encerrado que ainda tem Dossiê", () => {
    expect(podeApagar("diretoria_executiva", "encerrado", null)).toBe(true);
  });

  it("o ouvidor não apaga, nem no caso em que a Diretoria apagaria", () => {
    // Apagar não tem volta, então fica com quem responde pelo hospital: o
    // ouvidor sozinho não some com o relato de um caso sobre a própria equipe.
    expect(podeApagar("ouvidor", "encerrado", null)).toBe(false);
    // Quem não tem perfil na Ouvidoria também não, e o super admin cai aqui.
    expect(podeApagar(null, "encerrado", null)).toBe(false);
    expect(podeApagar(undefined, "encerrado", null)).toBe(false);
  });

  it("caso em andamento não apaga, em nenhum estado", () => {
    // Caso vivo tem prazo correndo e área esperando. Quem recusa de verdade é
    // o servidor, com 409; aqui a tela só não oferece o caminho.
    for (const status of ["em_classificacao", "aguardando_area", "aguardando_manifestante", "respondido"] as const) {
      expect(podeApagar("diretoria_executiva", status, null)).toBe(false);
    }
  });

  it("caso já apagado não apaga de novo", () => {
    expect(podeApagar("diretoria_executiva", "encerrado", APAGADO_EM)).toBe(false);
  });
});
