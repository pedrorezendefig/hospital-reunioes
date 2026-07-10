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

// Triagem com classificação de risco: decisão N-ária (3 ramos rotulados) com
// desvio lateral e salto (vai_para), o caso da fatia #222.
const TRIAGEM: FluxogramaEstrutura = {
  nos: [
    { id: "n1", tipo: "passo", texto: "Acolher o paciente" },
    {
      id: "n2",
      tipo: "decisao",
      texto: "Classificação de risco?",
      ramos: [
        { rotulo: "Verde" },
        { rotulo: "Amarelo", desvio: { texto: "Reavaliar em 30 minutos", retorna_para: "n2" } },
        { rotulo: "Vermelho", vai_para: "n4" },
      ],
    },
    { id: "n3", tipo: "passo", texto: "Encaminhar ao consultório" },
    { id: "n4", tipo: "passo", texto: "Iniciar atendimento imediato" },
  ],
};

// Decisão com dois ramos em desvio: a pilha lateral não pode sobrepor cards.
const DOIS_DESVIOS: FluxogramaEstrutura = {
  nos: [
    { id: "n1", tipo: "passo", texto: "Preparar" },
    {
      id: "n2",
      tipo: "decisao",
      texto: "Resultado do teste?",
      ramos: [
        { rotulo: "Normal" },
        { rotulo: "Alterado", desvio: { texto: "Repetir o teste", retorna_para: "n1" } },
        { rotulo: "Inconclusivo", desvio: { texto: "Coletar nova amostra" } },
      ],
    },
    { id: "n3", tipo: "passo", texto: "Registrar" },
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

describe("calcularLayout N-ário (#222)", () => {
  it("é determinístico e o snapshot cobre 3 ramos, desvio e salto", () => {
    const a = calcularLayout(TRIAGEM);
    const b = calcularLayout(TRIAGEM);
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    expect(a).toMatchSnapshot();
  });

  it("rótulos fora de Sim/Não ganham chip neutro, com largura para o texto", () => {
    const { chips } = calcularLayout(TRIAGEM);
    expect(chips.map((c) => c.tom)).toEqual(["neutro", "neutro", "neutro"]);
    const amarelo = chips.find((c) => c.rotulo === "Amarelo");
    expect(amarelo).toBeDefined();
    expect(amarelo!.w).toBeGreaterThan(44);
    // Sim e Não continuam com os tons semânticos (gabarito binário).
    const punc = calcularLayout(PUNCAO);
    expect(punc.chips.map((c) => c.tom).sort()).toEqual(["nao", "nao", "sim", "sim"]);
  });

  it("ramo com vai_para desenha seta ortogonal até o nó alvo", () => {
    const layout = calcularLayout(TRIAGEM);
    const alvo = layout.cards.find((c) => c.linhas.some((l) => l.texto.includes("Iniciar")));
    expect(alvo).toBeDefined();
    // A seta do salto termina entrando na borda esquerda do card alvo (x - 4).
    const entrada = `H ${alvo!.x - 4}`;
    expect(layout.setas.some((s) => s.d.endsWith(entrada))).toBe(true);
  });

  it("ramo com vai_para fim desenha seta até o terminal Fim", () => {
    const layout = calcularLayout({
      nos: [
        { id: "n1", tipo: "passo", texto: "Avaliar" },
        {
          id: "n2",
          tipo: "decisao",
          texto: "Grave?",
          ramos: [{ rotulo: "Sim", vai_para: "fim" }, { rotulo: "Não" }],
        },
        { id: "n3", tipo: "passo", texto: "Registrar" },
      ],
    });
    const fim = layout.terminais.find((t) => t.tipo === "fim");
    expect(fim).toBeDefined();
    expect(layout.setas.some((s) => s.d.endsWith(`H ${fim!.x - 4}`))).toBe(true);
  });

  it("empilha múltiplos desvios sem sobreposição e reserva espaço na coluna", () => {
    const layout = calcularLayout(DOIS_DESVIOS);
    const laterais = layout.cards.filter((c) => c.tipo === "desvio").sort((x, y) => x.y - y.y);
    expect(laterais).toHaveLength(2);
    const [a, b] = laterais;
    expect(a.y + a.h).toBeLessThanOrEqual(b.y);
    // A coluna principal continua legível: o próximo passo vem depois da pilha.
    const registrar = layout.cards.find((c) => c.linhas.some((l) => l.texto.includes("Registrar")));
    expect(registrar).toBeDefined();
    expect(registrar!.y).toBeGreaterThanOrEqual(b.y + b.h);
    // Desvios numerados em ordem de fluxo (Preparar 1, pilha 2 e 3, Registrar 4).
    expect([a.badge.numero, b.badge.numero]).toEqual([2, 3]);
    expect(registrar!.badge.numero).toBe(4);
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

  it("aceita decisão N-ária (3 ou mais ramos), desvios múltiplos e saltos", () => {
    expect(fluxogramaValido(TRIAGEM)).toBe(true);
    expect(fluxogramaValido(DOIS_DESVIOS)).toBe(true);
  });

  it("aceita vai_para para o fim", () => {
    expect(
      fluxogramaValido({
        nos: [
          { id: "n1", tipo: "passo", texto: "Avaliar" },
          {
            id: "n2",
            tipo: "decisao",
            texto: "Grave?",
            ramos: [{ rotulo: "Sim", vai_para: "fim" }, { rotulo: "Não" }],
          },
          { id: "n3", tipo: "passo", texto: "Registrar" },
        ],
      })
    ).toBe(true);
  });

  it("recusa vai_para para alvo inexistente", () => {
    expect(
      fluxogramaValido({
        nos: [
          {
            id: "n1",
            tipo: "decisao",
            texto: "Grave?",
            ramos: [{ rotulo: "Sim", vai_para: "fantasma" }, { rotulo: "Não" }],
          },
        ],
      })
    ).toBe(false);
  });

  it("recusa ramo com desvio e vai_para ao mesmo tempo", () => {
    expect(
      fluxogramaValido({
        nos: [
          { id: "n1", tipo: "passo", texto: "A" },
          {
            id: "n2",
            tipo: "decisao",
            texto: "Grave?",
            ramos: [{ rotulo: "Sim", vai_para: "fim", desvio: { texto: "X" } }, { rotulo: "Não" }],
          },
        ],
      })
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
