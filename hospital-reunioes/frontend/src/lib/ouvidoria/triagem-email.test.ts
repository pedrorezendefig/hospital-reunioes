/**
 * As regras puras da Triagem de e-mail (issue #648, PRD #646, ADR 0051).
 *
 * Quem vê a porta, como o remetente e a chegada aparecem, e as marcas do item.
 * O gate de verdade é o backend (403); aqui só não se oferece o caminho que
 * terminaria nele.
 */

import { describe, expect, it } from "vitest";

import {
  formatarChegada,
  marcasDoEmail,
  nomeDoRemetente,
  podeVerTriagemDeEmail,
  rotuloDosAnexos,
} from "./triagem-email";

describe("quem vê a Triagem de e-mail", () => {
  it("os dois perfis da Ouvidoria veem", () => {
    expect(podeVerTriagemDeEmail("ouvidor")).toBe(true);
    expect(podeVerTriagemDeEmail("diretoria_executiva")).toBe(true);
  });

  it("quem está fora da Ouvidoria não vê, e Super admin também fica de fora", () => {
    expect(podeVerTriagemDeEmail(null)).toBe(false);
    expect(podeVerTriagemDeEmail(undefined)).toBe(false);
    expect(podeVerTriagemDeEmail("")).toBe(false);
    expect(podeVerTriagemDeEmail("secretaria")).toBe(false);
    expect(podeVerTriagemDeEmail("super_admin")).toBe(false);
  });
});

describe("como o e-mail aparece na lista", () => {
  it("o remetente aparece pelo nome, e pelo endereço quando não há nome", () => {
    expect(nomeDoRemetente({ remetente_nome: "Joana da Silva", remetente_endereco: "joana@gmail.com" })).toBe(
      "Joana da Silva"
    );
    expect(nomeDoRemetente({ remetente_nome: null, remetente_endereco: "joana@gmail.com" })).toBe(
      "joana@gmail.com"
    );
    expect(nomeDoRemetente({ remetente_nome: "  ", remetente_endereco: "joana@gmail.com" })).toBe(
      "joana@gmail.com"
    );
  });

  it("a chegada sai no fuso do hospital", () => {
    // 14h02 em UTC são 11h02 no horário de Brasília.
    expect(formatarChegada("2026-09-10T14:02:10.000Z")).toBe("10/09/2026 11:02");
  });

  it("a contagem de anexos em palavras", () => {
    expect(rotuloDosAnexos(0)).toBe("Sem anexo");
    expect(rotuloDosAnexos(1)).toBe("1 anexo");
    expect(rotuloDosAnexos(3)).toBe("3 anexos");
  });

  it("as marcas do item: interno e incompleto", () => {
    expect(marcasDoEmail({ interno: false, incompleto: false })).toEqual([]);
    expect(marcasDoEmail({ interno: true, incompleto: false })).toEqual(["Interno"]);
    expect(marcasDoEmail({ interno: true, incompleto: true })).toEqual(["Interno", "Incompleto"]);
  });
});
