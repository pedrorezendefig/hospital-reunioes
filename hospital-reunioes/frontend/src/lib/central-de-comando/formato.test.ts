/**
 * Como a Central de Comando escreve os números (issue #814, ADR 0058).
 *
 * Porte de `formatInt` e `formatPercent` de `src/lib/format.test.ts` do
 * repositório antigo: são os dois que a Visão Geral usa nesta fatia. A conta é
 * do backend; aqui só se escreve o número do jeito que o hospital lê.
 */

import { describe, expect, it } from "vitest";

import {
  formatarData,
  formatarDiaCurto,
  formatarDiaLongo,
  formatarFatia,
  formatarHora,
  formatarInteiro,
  formatarInteiroCompacto,
  formatarPercentual,
  formatarQuando,
} from "./formato";

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

/**
 * Porte de `formatClock` (`src/lib/format.test.ts` do repositório antigo, issue
 * #815): a hora do "Mostrando os números de 13h45". Lá era o fuso do
 * navegador; aqui é o do hospital, como no resto do app. Os instantes entram em
 * UTC, e a hora sai em Brasília: numa máquina em UTC, ler no fuso da máquina
 * daria 16h45 e o teste acusaria.
 */
describe("formatarHora", () => {
  it("escreve o instante como hora do hospital, 'HhMM'", () => {
    expect(formatarHora(Date.parse("2026-06-21T16:45:00Z"))).toBe("13h45");
  });

  it("preenche os minutos com zero à esquerda, e a hora não", () => {
    expect(formatarHora(Date.parse("2026-06-21T12:05:00Z"))).toBe("9h05");
  });

  it("meia-noite é 0h", () => {
    expect(formatarHora(Date.parse("2026-06-21T03:10:00Z"))).toBe("0h10");
  });
});

/**
 * De quando é o último número bom, no aviso da barra de frescor (issue #815):
 * a hora quando é de hoje, o dia e a hora quando não é. "Hoje" é o dia do
 * hospital, e não o do UTC: 22h em Brasília já é o dia seguinte em UTC.
 */
describe("formatarQuando", () => {
  const AGORA = Date.parse("2026-09-18T16:50:00Z"); // 13h50 em Brasília

  it("número de hoje: só a hora", () => {
    expect(formatarQuando(Date.parse("2026-09-18T16:45:00Z"), AGORA)).toBe("13h45");
  });

  it("número de outro dia: o dia e a hora", () => {
    expect(formatarQuando(Date.parse("2026-09-17T16:45:00Z"), AGORA)).toBe("17/09/2026 às 13h45");
  });

  it("o dia é o do hospital: 22h de ontem em Brasília é ontem, mesmo sendo hoje em UTC", () => {
    expect(formatarQuando(Date.parse("2026-09-18T01:00:00Z"), AGORA)).toBe("17/09/2026 às 22h00");
  });
});

/**
 * Os rótulos dos gráficos de Dados do Google (issue #817). Porte de
 * `formatDayShort`, `formatDayLong` e `formatShare` (`src/lib/format.test.ts`
 * do repositório antigo). As datas saem do texto do backend, e não de um
 * `Date` no fuso do navegador, como no `formatarData`.
 */
describe("formatarDiaCurto", () => {
  it("escreve a data ISO como 'dia mês' abreviado", () => {
    expect(formatarDiaCurto("2026-06-16")).toBe("16 jun");
    expect(formatarDiaCurto("2026-09-01")).toBe("1 set");
  });
});

describe("formatarDiaLongo", () => {
  it("acrescenta o dia da semana abreviado", () => {
    expect(formatarDiaLongo("2026-06-16")).toBe("ter, 16 jun");
    expect(formatarDiaLongo("2026-09-13")).toBe("dom, 13 set");
  });
});

describe("formatarFatia", () => {
  it("escreve os pontos percentuais inteiros que o backend mandou", () => {
    expect(formatarFatia(71)).toBe("71%");
    expect(formatarFatia(100)).toBe("100%");
  });

  it("fatia com visita e menos de 1% é '<1%', e não zero", () => {
    expect(formatarFatia(0)).toBe("<1%");
  });
});

describe("formatarInteiroCompacto", () => {
  it("encurta os milhares para caber no eixo do gráfico no celular", () => {
    // O Intl separa o número do "mil" com espaço que não quebra (U+00A0).
    expect(formatarInteiroCompacto(950)).toBe("950");
    expect(formatarInteiroCompacto(1200)).toBe("1,2 mil");
    expect(formatarInteiroCompacto(38412)).toBe("38 mil");
  });
});
