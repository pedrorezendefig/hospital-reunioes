import { describe, expect, it } from "vitest";

import {
  descreverPrazo,
  descreverTrecho,
  prazosVisiveis,
  PRAZO_NO_ACIONAMENTO,
  SEM_CONFIRMACAO_DO_CALENDARIO,
  type MarcoDoCaso,
  type PrazoDoCaso,
} from "./marcos";

function marco(overrides: Partial<MarcoDoCaso> = {}): MarcoDoCaso {
  return {
    chave: "T1",
    rotulo: "Validação",
    em: "2026-08-17T12:00:00+00:00",
    pendente: false,
    trecho: "Triagem da Ouvidoria",
    minutos_uteis: 120,
    em_curso: false,
    tramitacao_anterior_em: null,
    ...overrides,
  };
}

function prazo(overrides: Partial<PrazoDoCaso> = {}): PrazoDoCaso {
  return {
    chave: "conclusivo",
    rotulo: "Prazo conclusivo",
    em: "2026-08-25T20:00:00+00:00",
    situacao: "definido",
    rotulo_prazo: "vence em 2 dias úteis",
    estourado: false,
    nota: null,
    ...overrides,
  };
}

describe("o tempo decorrido de cada trecho (issue #480)", () => {
  it("diz o trecho e o tempo dele em dias e horas úteis", () => {
    // 600 minutos de expediente são 1 dia útil (9 horas) e 1 hora.
    expect(descreverTrecho(marco({ minutos_uteis: 600 }), true)).toBe(
      "Triagem da Ouvidoria: 1 dia útil e 1 hora útil"
    );
  });

  it("o trecho ainda aberto diz que o número é o de agora", () => {
    // Sem essa marca, o ouvidor leria o tempo de um trecho em andamento como
    // se ele já tivesse fechado com aquele número.
    expect(descreverTrecho(marco({ minutos_uteis: 120, em_curso: true }), true)).toBe(
      "Triagem da Ouvidoria: 2 horas úteis até agora"
    );
  });

  it("o trecho que nem começou não tem tempo, e não tem zero", () => {
    expect(descreverTrecho(marco({ minutos_uteis: null }), true)).toBeNull();
  });

  it("a entrada não fecha trecho nenhum", () => {
    expect(descreverTrecho(marco({ chave: "T0", trecho: null, minutos_uteis: null }), true)).toBeNull();
  });
});

describe("os dois prazos ao lado dos marcos (issue #480)", () => {
  it("mostra a contagem regressiva que veio do motor", () => {
    expect(descreverPrazo(prazo(), true)).toBe("vence em 2 dias úteis");
  });

  it("sem o calendário confirmado, a contagem sai da tela", () => {
    // A data do vencimento é dado persistido e continua na tela; a contagem é
    // conta feita no calendário útil, e feriado que não pôde ser lido conta
    // como dia trabalhado. Afirmar o número ao lado do aviso seria avisar por
    // educação (issue #449).
    expect(descreverPrazo(prazo(), false)).toBe(SEM_CONFIRMACAO_DO_CALENDARIO);
    expect(descreverTrecho(marco(), false)).toBe(
      `Triagem da Ouvidoria: ${SEM_CONFIRMACAO_DO_CALENDARIO}`
    );
  });

  it("sem calendário, o prazo que ainda vai nascer no despacho continua dizendo isso", () => {
    // Não é conta nenhuma: é o despacho que ainda não aconteceu.
    const naFila = prazo({ em: null, situacao: "aguardando_validacao", rotulo_prazo: null });

    expect(descreverPrazo(naFila, false)).toBe(PRAZO_NO_ACIONAMENTO);
  });

  it("prazo que ainda vai nascer no despacho continua na tela", () => {
    const naFila = prazo({ em: null, situacao: "aguardando_validacao", rotulo_prazo: null });

    expect(prazosVisiveis([naFila])).toHaveLength(1);
    expect(descreverPrazo(naFila, true)).toBe(PRAZO_NO_ACIONAMENTO);
  });

  it("gravidade sem aquele prazo não mostra a linha", () => {
    // O crítico não tem prazo conclusivo fixo (migration 065). A tela não
    // inventa número, e também não deixa uma linha vazia convidando alguém a
    // preencher (PRD #468, história 12).
    const critico = prazo({ em: null, situacao: "sem_prazo", rotulo_prazo: null });
    const daArea = prazo({ chave: "area", rotulo: "Prazo da área" });

    expect(prazosVisiveis([daArea, critico]).map((p) => p.chave)).toEqual(["area"]);
  });
});
