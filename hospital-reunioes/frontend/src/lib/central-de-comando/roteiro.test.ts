import { describe, expect, it } from "vitest";

import { ROTEIRO } from "./roteiro";

describe("O que vem por aí", () => {
  it("tem os quatro itens na ordem do CONTEXT.md", () => {
    expect(ROTEIRO.map((item) => item.titulo)).toEqual(["Blog", "Editor do Site", "Mapa de Calor", "Google Ads"]);
  });

  it("nenhum item promete data", () => {
    for (const item of ROTEIRO) {
      expect(item.descricao).not.toMatch(/\bchega em\b|dispon[ií]vel em|previsto para|\d/i);
    }
  });

  it("sem travessão nem meia-risca (tipografia da casa)", () => {
    for (const item of ROTEIRO) {
      expect(`${item.titulo} ${item.descricao}`).not.toMatch(/[—–]/);
    }
  });

  it("não chama Objetivo de meta (ADR 0058, decisão 7)", () => {
    // O nome antigo da Área do site é varrido no código-fonte da seção pelo
    // `vocabulario-da-central.test.ts`; aqui guardamos só o "meta".
    for (const item of ROTEIRO) {
      expect(`${item.titulo} ${item.descricao}`).not.toMatch(/\bmeta\b/i);
    }
  });
});
