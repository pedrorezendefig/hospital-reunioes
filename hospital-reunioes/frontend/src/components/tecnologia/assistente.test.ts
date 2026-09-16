import { describe, expect, it } from "vitest";

import {
  descricaoAoCriar,
  NAO_INFORMADO,
  podeCriar,
  RASCUNHO_VAZIO,
  respostaDoChatValida,
  ROTEIRO_POR_TIPO,
} from "./assistente";
import { TIPOS } from "./demandas";

describe("Roteiro por Tipo", () => {
  it("todos os sete Tipos têm entrada no roteiro", () => {
    // Um Tipo novo sem roteiro faria `descricaoAoCriar` estourar na hora de
    // criar, com o rascunho pronto na tela.
    expect(TIPOS.every((t) => Array.isArray(ROTEIRO_POR_TIPO[t]))).toBe(true);
  });

  it("Defeito, Novo/Ajuste, Informação/Consultoria e Terceiro têm rótulos diferentes entre si", () => {
    // O par de presença: um roteiro só, repetido nos sete, passaria no teste
    // acima sem que rótulo nenhum estivesse certo.
    expect(ROTEIRO_POR_TIPO.defeito).toEqual(["Onde", "O que aconteceu", "O que esperava", "Quando", "Como repetir"]);
    expect(ROTEIRO_POR_TIPO.novo).toEqual(["O que precisa", "Por quê", "Quem usa", "Hoje é assim"]);
    expect(ROTEIRO_POR_TIPO.ajuste).toEqual(ROTEIRO_POR_TIPO.novo);
    expect(ROTEIRO_POR_TIPO.informacao).toEqual(["Pergunta", "Contexto", "O que já sei"]);
    expect(ROTEIRO_POR_TIPO.consultoria).toEqual(ROTEIRO_POR_TIPO.informacao);
    expect(ROTEIRO_POR_TIPO.terceiro).toEqual(["Quem de fora", "O que falta dele"]);
    expect(ROTEIRO_POR_TIPO.decisao).toEqual([]);
  });
});

describe("descricaoAoCriar", () => {
  it("rótulo sem resposta sai como não informado, na ordem do roteiro", () => {
    const saida = descricaoAoCriar("terceiro", "O que falta dele: o acesso ao relatório");

    expect(saida).toBe(["Quem de fora: " + NAO_INFORMADO, "O que falta dele: o acesso ao relatório"].join("\n"));
  });

  it("o rótulo respondido não vira não informado", () => {
    // O par do teste acima: uma função que escrevesse "não informado" em tudo
    // passaria naquele sozinha.
    const saida = descricaoAoCriar("terceiro", "Quem de fora: a Global Health\nO que falta dele: o acesso");

    expect(saida).not.toContain(NAO_INFORMADO);
  });

  it("resposta de várias linhas fica com o rótulo dela", () => {
    const saida = descricaoAoCriar("terceiro", "Quem de fora: a MV\nfalei com o analista ontem");

    expect(saida).toBe(["Quem de fora: a MV", "falei com o analista ontem", "O que falta dele: " + NAO_INFORMADO].join("\n"));
  });

  it("descrição vazia vira o roteiro inteiro em branco", () => {
    expect(descricaoAoCriar("informacao", "")).toBe(
      ["Pergunta: " + NAO_INFORMADO, "Contexto: " + NAO_INFORMADO, "O que já sei: " + NAO_INFORMADO].join("\n"),
    );
  });

  it("Decisão não ganha rótulo nenhum", () => {
    expect(descricaoAoCriar("decisao", "escolher entre mensal e trimestral")).toBe(
      "escolher entre mensal e trimestral",
    );
  });

  it("o que a pessoa escreveu fora dos rótulos é preservado", () => {
    const saida = descricaoAoCriar("terceiro", "contexto solto\nQuem de fora: a MV\nO que falta dele: o acesso");

    expect(saida.split("\n")[0]).toBe("contexto solto");
  });
});

describe("podeCriar", () => {
  it("o rascunho vazio não cria", () => {
    expect(podeCriar(RASCUNHO_VAZIO)).toBe(false);
  });

  it("título sem Produto não cria", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "Alguma coisa" })).toBe(false);
  });

  it("Produto sem título não cria", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, produto_id: "prod-1" })).toBe(false);
  });

  it("título e Produto criam, mesmo sem Tipo, descrição nem prazo", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "Alguma coisa", produto_id: "prod-1" })).toBe(true);
  });

  it("título só de espaço não conta como título", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "   ", produto_id: "prod-1" })).toBe(false);
  });
});

describe("O rascunho vazio", () => {
  it("nasce sem Tipo e sem Produto", () => {
    // Um Tipo de partida seria preservado pelo prompt e a Demanda nasceria com
    // o Tipo errado, calada.
    expect(RASCUNHO_VAZIO.tipo).toBeNull();
    expect(RASCUNHO_VAZIO.produto_id).toBeNull();
  });

  it("nasce com prioridade Normal", () => {
    expect(RASCUNHO_VAZIO.prioridade).toBe("normal");
  });
});

describe("respostaDoChatValida", () => {
  const BOA = {
    reply: "Entendi.",
    rascunho: {
      titulo: "Ana não responde",
      tipo: "defeito",
      produto_id: "prod-1",
      prioridade: "normal",
      prazo: null,
      descricao: "Onde: no WhatsApp",
    },
  };

  it("aceita o contrato inteiro", () => {
    expect(respostaDoChatValida(BOA)).toBe(true);
  });

  it("aceita os campos que podem ser nulos", () => {
    expect(respostaDoChatValida({ ...BOA, rascunho: { ...BOA.rascunho, tipo: null, produto_id: null } })).toBe(true);
  });

  // Os quatro primeiros são os corpos que quebravam a tela: `null` levantava no
  // meio do encerramento e congelava o painel, e os outros chegavam ao render.
  it.each([
    ["null", null],
    ["lista", []],
    ["objeto vazio", {}],
    ["sem rascunho", { reply: "oi" }],
    ["rascunho pela metade", { reply: "oi", rascunho: {} }],
    ["rascunho nulo", { reply: "oi", rascunho: null }],
    ["reply que não é texto", { ...BOA, reply: 42 }],
    ["titulo que não é texto", { ...BOA, rascunho: { ...BOA.rascunho, titulo: 42 } }],
    ["descricao ausente", { ...BOA, rascunho: { ...BOA.rascunho, descricao: undefined } }],
    ["prioridade ausente", { ...BOA, rascunho: { ...BOA.rascunho, prioridade: undefined } }],
    ["prazo que não é texto nem nulo", { ...BOA, rascunho: { ...BOA.rascunho, prazo: 7 } }],
  ])("recusa %s", (_nome, corpo) => {
    expect(respostaDoChatValida(corpo)).toBe(false);
  });
});
