/**
 * O Markdown simples do "O que muda", do lado da tela (issue #676, ADR 0054).
 *
 * As contas da Conversa e das menções saíram com a Conversa da Demanda na
 * issue #1386 (ADR 0077).
 */

import { describe, expect, it } from "vitest";

import { blocosDoTextoSimples, iniciais, rotuloDaEtapa, textoDaAbertura } from "./demandas";

describe("A data de abertura do card (issues #1578 e #1580)", () => {
  const AGORA = new Date("2026-11-11T15:00:00Z");

  it("conta os dias pelo calendário do hospital, com a hora de Brasília", () => {
    expect(textoDaAbertura("2026-11-01T13:00:00Z", AGORA)).toBe("Aberto em 01/11 às 10:00, há 10 dias");
  });

  it("hoje e ontem têm nome, e também a hora", () => {
    expect(textoDaAbertura("2026-11-11T12:05:00Z", AGORA)).toBe("Aberto hoje às 09:05");
    expect(textoDaAbertura("2026-11-10T17:32:00Z", AGORA)).toBe("Aberto ontem às 14:32");
  });

  it("a virada do dia e a hora são as de Brasília, e não as de Greenwich", () => {
    // 01h30 em Greenwich no dia 11 ainda é 22h30 do dia 10 em Brasília.
    expect(textoDaAbertura("2026-11-11T01:30:00Z", AGORA)).toBe("Aberto ontem às 22:30");
  });

  it("sem data, ou com data inválida, não escreve nada", () => {
    expect(textoDaAbertura(null, AGORA)).toBe("");
    expect(textoDaAbertura("ontem", AGORA)).toBe("");
  });
});

describe("As iniciais de quem pediu e de quem cuida (issue #1578)", () => {
  it("são a primeira letra do primeiro e do último nome", () => {
    expect(iniciais("Felipe Malafaia")).toBe("FM");
    expect(iniciais("Ana de Souza Lima")).toBe("AL");
  });

  it("nome único vira uma letra, e espaço sobrando não conta", () => {
    expect(iniciais("  pedro  ")).toBe("P");
    expect(iniciais("")).toBe("");
  });
});

describe("O rótulo da Etapa no card (issue #1578)", () => {
  it("é o selo sem a contagem de partes, que o card mostra na barra", () => {
    expect(
      rotuloDaEtapa({ id: "d", titulo: "t", etapa: "em_desenvolvimento", partes_entregues: 2, partes_total: 5 }),
    ).toBe("Em desenvolvimento");
    expect(rotuloDaEtapa({ id: "d", titulo: "t", etapa: "em_producao", versao: "v0.223.0" })).toBe(
      "Em produção desde v0.223.0",
    );
  });

  it("a conversa sem card é Registrada", () => {
    expect(rotuloDaEtapa({ id: "d", titulo: "t", etapa: "registrada" })).toBe("Registrada");
    expect(rotuloDaEtapa({ id: "d", titulo: "t" })).toBe("Registrada");
  });
});

describe("O Markdown simples do O que muda", () => {
  it("separa parágrafo de lista", () => {
    const blocos = blocosDoTextoSimples("O card ganha a seção.\n\n- Vem do planejamento.\n- Ninguém reescreve.");

    expect(blocos.map((b) => b.lista)).toEqual([false, true]);
    expect(blocos[1].linhas.map((linha) => linha[0].texto)).toEqual(["Vem do planejamento.", "Ninguém reescreve."]);
  });

  it("linha em branco fecha o parágrafo", () => {
    // Sem isso os dois parágrafos virariam um só, e o texto sairia grudado.
    const blocos = blocosDoTextoSimples("Primeiro.\n\nSegundo.");

    expect(blocos).toHaveLength(2);
    expect(blocos.every((b) => b.linhas.length === 1)).toBe(true);
  });

  it("o negrito vira pedaço forte e o asterisco some", () => {
    const pedacos = blocosDoTextoSimples("**O que muda:** o card ganha a seção.")[0].linhas[0];

    expect(pedacos).toEqual([
      { texto: "O que muda:", forte: true },
      { texto: " o card ganha a seção.", forte: false },
    ]);
  });

  it("link do Markdown continua sendo texto", () => {
    // Nada que venha do GitHub vira elemento clicável na tela do diretor: o que
    // o parser não conhece fica como está, e não como um link.
    const pedacos = blocosDoTextoSimples("Veja [a issue](https://exemplo).")[0].linhas[0];

    expect(pedacos).toEqual([{ texto: "Veja [a issue](https://exemplo).", forte: false }]);
  });

  it("texto vazio ou nulo não vira bloco nenhum", () => {
    expect(blocosDoTextoSimples(null)).toEqual([]);
    expect(blocosDoTextoSimples("   \n  ")).toEqual([]);
  });
});
