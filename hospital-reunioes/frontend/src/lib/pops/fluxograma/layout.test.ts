import { describe, expect, it } from "vitest";

import { calcularLayout } from "./layout";
import type { FluxogramaEstrutura } from "./tipos";
import { fluxogramaValido } from "./validar";

// Fluxo de punção venosa periférica: o mesmo do gabarito visual do PRD #210
// (passos, duas decisões binárias com desvio lateral e retorno a um nó anterior).
const PUNCAO: FluxogramaEstrutura = {
  nos: [
    { id: "n1", tipo: "passo", texto: "Higienizar as mãos" },
    { id: "n2", tipo: "passo", texto: "Reunir o material de punção" },
    {
      id: "n3",
      tipo: "decisao",
      texto: "Material completo?",
      ramos: [
        { rotulo: "Não", desvio: { texto: "Solicitar reposição ao almoxarifado", retorna_para: "n2" } },
        { rotulo: "Sim" },
      ],
    },
    { id: "n4", tipo: "passo", texto: "Realizar a punção venosa" },
    {
      id: "n5",
      tipo: "decisao",
      texto: "Punção bem-sucedida?",
      ramos: [
        { rotulo: "Não", desvio: { texto: "Trocar o dispositivo e repetir", retorna_para: "n4" } },
        { rotulo: "Sim" },
      ],
    },
    { id: "n6", tipo: "passo", texto: "Fixar e identificar o acesso" },
    { id: "n7", tipo: "passo", texto: "Registrar no prontuário" },
  ],
};

describe("calcularLayout", () => {
  it("é determinístico: mesma estrutura, mesmas posições e trajetos", () => {
    const a = calcularLayout(PUNCAO);
    const b = calcularLayout(PUNCAO);
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });

  it("posiciona a coluna, os desvios, as setas e os chips (snapshot)", () => {
    expect(calcularLayout(PUNCAO)).toMatchSnapshot();
  });

  it("numera passos e desvios em ordem de fluxo; decisões recebem badge de decisão", () => {
    const { cards } = calcularLayout(PUNCAO);
    const numeros = cards.filter((c) => c.badge.tipo === "numero").map((c) => c.badge.numero);
    // 7 cards numerados (5 passos + 2 desvios), sem repetição, cobrindo 1..7.
    expect([...numeros].sort((a, b) => (a ?? 0) - (b ?? 0))).toEqual([1, 2, 3, 4, 5, 6, 7]);
    // Ordem de fluxo: o desvio "Solicitar reposição" (após o passo 2) é o 3, o
    // passo "Realizar a punção" é o 4, e o desvio "Trocar o dispositivo" é o 5.
    const numeroDe = (trecho: string) =>
      cards.find((c) => c.linhas.some((l) => l.texto.includes(trecho)))?.badge.numero;
    expect(numeroDe("Higienizar")).toBe(1);
    expect(numeroDe("Solicitar")).toBe(3);
    expect(numeroDe("Realizar")).toBe(4);
    expect(numeroDe("Trocar")).toBe(5);
    expect(cards.filter((c) => c.tipo === "decisao").every((c) => c.badge.tipo === "decisao")).toBe(true);
  });

  it("chips de ramo carregam o tom por rótulo (Sim verde, Não vermelho)", () => {
    const { chips } = calcularLayout(PUNCAO);
    expect(chips.map((c) => c.tom).sort()).toEqual(["nao", "nao", "sim", "sim"]);
  });

  it("cresce a altura do card para caber texto longo, nunca corta em uma linha só", () => {
    const longo: FluxogramaEstrutura = {
      nos: [
        {
          id: "u1",
          tipo: "passo",
          texto:
            "Conferir a prescrição médica, checar identidade do paciente com dois identificadores e confirmar alergias antes de prosseguir",
        },
      ],
    };
    const card = calcularLayout(longo).cards[0];
    expect(card.linhas.length).toBeGreaterThan(1);
    // Altura acompanha o número de linhas (não fica presa no mínimo de 46).
    expect(card.h).toBeGreaterThan(46);
  });
});

describe("fluxogramaValido", () => {
  it("aceita a gramática válida", () => {
    expect(fluxogramaValido(PUNCAO)).toBe(true);
  });

  it("recusa decisão com menos de 2 ramos", () => {
    expect(
      fluxogramaValido({ nos: [{ id: "n1", tipo: "decisao", texto: "X?", ramos: [{ rotulo: "Sim" }] }] })
    ).toBe(false);
  });

  it("recusa desvio que retorna para id inexistente", () => {
    expect(
      fluxogramaValido({
        nos: [
          {
            id: "n1",
            tipo: "decisao",
            texto: "X?",
            ramos: [{ rotulo: "Não", desvio: { texto: "corrige", retorna_para: "zzz" } }, { rotulo: "Sim" }],
          },
        ],
      })
    ).toBe(false);
  });

  it("recusa nó sem texto e objeto que não é a estrutura", () => {
    expect(fluxogramaValido({ nos: [{ id: "n1", tipo: "passo", texto: "  " }] })).toBe(false);
    expect(fluxogramaValido("flowchart TD")).toBe(false);
    expect(fluxogramaValido({ nos: [] })).toBe(false);
  });
});
