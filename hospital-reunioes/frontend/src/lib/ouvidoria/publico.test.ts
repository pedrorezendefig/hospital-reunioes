import { describe, expect, it } from "vitest";
import { montarEnvio, relatoEstaVazio } from "./publico";

describe("relatoEstaVazio", () => {
  it("recusa relato vazio ou só com espaços antes de gastar a ida ao servidor", () => {
    expect(relatoEstaVazio("")).toBe(true);
    expect(relatoEstaVazio("   ")).toBe(true);
    expect(relatoEstaVazio("\n\t ")).toBe(true);
  });

  it("aceita relato com conteúdo", () => {
    expect(relatoEstaVazio("Esperei duas horas na recepção.")).toBe(false);
  });
});

describe("montarEnvio", () => {
  it("manda nome e contato de quem se identifica", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "Maria Souza",
      contato: "maria@exemplo.com",
      anonimo: false,
      setor: null,
      ponto: null,
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
      setor: null,
      ponto: null,
    });

    expect(envio.anonimo).toBe(true);
    expect(envio.nome).toBeUndefined();
    expect(envio.contato).toBeUndefined();
  });

  it("carrega o setor e o ponto que vieram do QR", () => {
    const envio = montarEnvio({
      relato: "Esperei duas horas.",
      nome: "",
      contato: "",
      anonimo: false,
      setor: "Recepção",
      ponto: "Poltrona 12",
    });

    expect(envio.setor).toBe("Recepção");
    expect(envio.ponto).toBe("Poltrona 12");
  });

  it("omite os campos em branco em vez de mandar string vazia", () => {
    const envio = montarEnvio({
      relato: "  Esperei duas horas.  ",
      nome: "   ",
      contato: "",
      anonimo: false,
      setor: null,
      ponto: null,
    });

    expect(envio.relato).toBe("Esperei duas horas.");
    expect("nome" in envio).toBe(false);
    expect("contato" in envio).toBe(false);
    expect("setor" in envio).toBe(false);
    expect("ponto" in envio).toBe(false);
  });
});
