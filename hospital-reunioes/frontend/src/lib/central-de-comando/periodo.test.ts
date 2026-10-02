/**
 * O período que a tela lê do endereço (issue #814, ADR 0058).
 *
 * Porte de `parsePeriod` e `PERIODS` de `src/lib/analytics/period.test.ts` do
 * repositório antigo. A conta das datas é do backend; aqui mora só a leitura
 * leniente do `?periodo=`: quem digita um período que não existe vê o de 28
 * dias, e não uma tela de erro.
 */

import { describe, expect, it } from "vitest";

import { PERIODOS, diasDoPeriodo, lerPeriodo } from "./periodo";

describe("lerPeriodo", () => {
  it("aceita os períodos válidos", () => {
    expect(lerPeriodo("7d")).toBe("7d");
    expect(lerPeriodo("28d")).toBe("28d");
    expect(lerPeriodo("90d")).toBe("90d");
  });

  it("cai no padrão (28 dias) para ausente ou inválido", () => {
    expect(lerPeriodo(undefined)).toBe("28d");
    expect(lerPeriodo(null)).toBe("28d");
    expect(lerPeriodo("")).toBe("28d");
    expect(lerPeriodo("xpto")).toBe("28d");
    expect(lerPeriodo("7")).toBe("28d");
  });

  it("com o parâmetro repetido no endereço, vale o primeiro", () => {
    expect(lerPeriodo(["7d", "90d"])).toBe("7d");
  });

  it("restringe à lista permitida quando passada (o Instagram não tem 90 dias)", () => {
    expect(lerPeriodo("90d", ["7d", "28d"])).toBe("28d");
    expect(lerPeriodo("7d", ["7d", "28d"])).toBe("7d");
  });
});

describe("PERIODOS", () => {
  it("lista os três períodos na ordem do seletor", () => {
    expect(PERIODOS).toEqual(["7d", "28d", "90d"]);
  });
});

describe("diasDoPeriodo", () => {
  it("mapeia os rótulos", () => {
    expect(diasDoPeriodo("7d")).toBe(7);
    expect(diasDoPeriodo("28d")).toBe(28);
    expect(diasDoPeriodo("90d")).toBe(90);
  });
});
