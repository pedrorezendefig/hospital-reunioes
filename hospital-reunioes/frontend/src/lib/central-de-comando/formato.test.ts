/**
 * Como a Central de Comando escreve os números (issue #814, ADR 0058).
 *
 * Porte de `formatInt` e `formatPercent` de `src/lib/format.test.ts` do
 * repositório antigo: são os dois que a Visão Geral usa nesta fatia. A conta é
 * do backend; aqui só se escreve o número do jeito que o hospital lê.
 */

import { describe, expect, it } from "vitest";

import { formatarData, formatarInteiro, formatarPercentual } from "./formato";

describe("formatarInteiro", () => {
  it("usa o separador de milhar do pt-BR", () => {
    expect(formatarInteiro(38412)).toBe("38.412");
    expect(formatarInteiro(9120)).toBe("9.120");
  });

  it("escreve o zero como zero", () => {
    expect(formatarInteiro(0)).toBe("0");
  });
});

describe("formatarPercentual", () => {
  it("escreve a fração como porcentagem pt-BR com uma casa", () => {
    expect(formatarPercentual(0.124)).toBe("12,4%");
    expect(formatarPercentual(0.2345)).toBe("23,5%");
  });
});

describe("formatarData", () => {
  it("escreve a data ISO do backend como dia/mês/ano", () => {
    expect(formatarData("2026-08-21")).toBe("21/08/2026");
  });

  it("não passa pelo fuso do navegador: a data do backend é a data", () => {
    // Um `new Date("2026-09-01")` é meia-noite em UTC, que no Brasil ainda é o
    // dia anterior. A data sai do texto, e não do relógio.
    expect(formatarData("2026-09-01")).toBe("01/09/2026");
  });
});
