import { describe, expect, it } from "vitest";
import { NATUREZAS_INFORMADAS, montarEnvio, relatoEstaVazio } from "./publico";

describe("relatoEstaVazio", () => {
  it("recusa relato vazio ou só com espaços antes de gastar a ida ao servidor", () => {
    expect(relatoEstaVazio("")).toBe(true);
    expect(relatoEstaVazio("   ")).toBe(true);
    expect(relatoEstaVazio("\n\t ")).toBe(true);
  });

  it("aceita relato com conteúdo", () => {
    expect(relatoEstaVazio("Esperei duas horas na recepção.")).toBe(false);
  });

  it("recusa relato só de emoji ou pontuação, que o servidor recusaria com 422", () => {
    expect(relatoEstaVazio("😡😡😡")).toBe(true);
    expect(relatoEstaVazio("!!!...")).toBe(true);
  });
});

describe("montarEnvio", () => {
  it("manda nome e contato de quem se identifica", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "Maria Souza",
      contato: "maria@exemplo.com",
      anonimo: false,
      p: null,
      natureza: null,
    });

    expect(envio.nome).toBe("Maria Souza");
    expect(envio.contato).toBe("maria@exemplo.com");
    expect(envio.anonimo).toBe(false);
  });

  it("não leva identificação quando o manifestante escolheu ser anônimo", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "Maria Souza",
      contato: "maria@exemplo.com",
      anonimo: true,
      p: null,
      natureza: null,
    });

    expect(envio.anonimo).toBe(true);
    expect(envio.nome).toBeUndefined();
    expect(envio.contato).toBeUndefined();
  });

  it("não carrega mais setor nem ponto por extenso", () => {
    // ADR 0036, decisão 10: a origem passou a ser o código do cartaz, e o
    // servidor resolve o resto. Texto de origem não sai mais do cliente.
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      p: "AB2CD3",
      natureza: null,
    }) as unknown as Record<string, unknown>;

    expect(envio.setor).toBeUndefined();
    expect(envio.ponto).toBeUndefined();
  });

  it("omite os campos em branco em vez de mandar string vazia", () => {
    const envio = montarEnvio({
      relato: "  Esperei duas horas.  ",
      nome: "   ",
      contato: "",
      anonimo: false,
      p: null,
      natureza: null,
    });

    expect(envio.relato).toBe("Esperei duas horas.");
    expect("nome" in envio).toBe(false);
    expect("contato" in envio).toBe(false);
    expect("setor" in envio).toBe(false);
    expect("ponto" in envio).toBe(false);
  });
});

describe("o envio com o código do cartaz (issue #378, ADR 0036)", () => {
  it("leva só o código, e não o setor nem o ponto por extenso", () => {
    // Decisão 10: nenhum texto de origem vem mais do cliente. O servidor
    // resolve o código contra o cadastro.
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      p: "AB2CD3",
      natureza: null,
    });

    expect(envio.p).toBe("AB2CD3");
    expect(envio).not.toHaveProperty("setor");
    expect(envio).not.toHaveProperty("ponto");
  });

  it("sem código, o envio não carrega origem nenhuma", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      p: null,
      natureza: null,
    });

    expect(envio).not.toHaveProperty("p");
  });

  it("código só de espaço não vira origem", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      p: "   ",
      natureza: null,
    });

    expect(envio).not.toHaveProperty("p");
  });

  it("caso anônimo continua levando o código", () => {
    // Quem decide o que fazer com o anonimato é o servidor: ele grava o setor
    // e omite o ponto (decisão 5 da #375). A página não precisa saber disso.
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "Joana",
      contato: "joana@exemplo.com",
      anonimo: true,
      p: "AB2CD3",
      natureza: null,
    });

    expect(envio.p).toBe("AB2CD3");
    expect(envio).not.toHaveProperty("nome");
  });
});

describe("a natureza informada pelo manifestante (issue #473, RN-88)", () => {
  it("oferece as quatro naturezas do cartaz, com o elogio primeiro", () => {
    // A ordem é a promessa do papel: o canal também serve para elogiar, e o
    // elogio abre a lista para quem chega achando que ouvidoria é só queixa.
    expect(NATUREZAS_INFORMADAS.map((n) => n.valor)).toEqual([
      "elogio",
      "reclamacao",
      "sugestao",
      "informacao",
    ]);
    expect(NATUREZAS_INFORMADAS.map((n) => n.rotulo)).toEqual([
      "Elogio",
      "Reclamação",
      "Sugestão",
      "Informação",
    ]);
  });

  it("leva a natureza escolhida no envio", () => {
    const envio = montarEnvio({
      relato: "Fui muito bem atendida na recepção.",
      nome: "",
      contato: "",
      anonimo: false,
      p: null,
      natureza: "elogio",
    });

    expect(envio.natureza_informada).toBe("elogio");
  });

  it("sem escolha, o envio não carrega natureza nenhuma", () => {
    // A escolha é opcional: mandar string vazia faria o servidor receber um
    // campo que ninguém preencheu.
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      p: null,
      natureza: null,
    });

    expect(envio).not.toHaveProperty("natureza_informada");
  });

  it("caso anônimo leva a natureza do mesmo jeito", () => {
    const envio = montarEnvio({
      relato: "Sugiro senhas por ordem de chegada.",
      nome: "",
      contato: "",
      anonimo: true,
      p: null,
      natureza: "sugestao",
    });

    expect(envio.natureza_informada).toBe("sugestao");
    expect(envio.anonimo).toBe(true);
  });
});
