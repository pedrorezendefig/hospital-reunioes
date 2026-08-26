import { describe, expect, it } from "vitest";
import {
  ehSigilosoPorNatureza,
  LABEL_TIPO,
  rotuloDoTipo,
  sigiloResultante,
  TIPOS_MANIFESTACAO,
} from "./taxonomia";

describe("taxonomia da manifestação (issue #372)", () => {
  it("a lista é fechada e tem os cinco tipos do ADR 0034", () => {
    expect(TIPOS_MANIFESTACAO).toEqual([
      "denuncia",
      "reclamacao",
      "sugestao",
      "elogio",
      "relato_de_conduta",
    ]);
    expect(Object.keys(LABEL_TIPO).sort()).toEqual([...TIPOS_MANIFESTACAO].sort());
  });

  it("denúncia e relato de conduta são sigilosos por natureza", () => {
    expect(ehSigilosoPorNatureza("denuncia")).toBe(true);
    expect(ehSigilosoPorNatureza("relato_de_conduta")).toBe(true);
    expect(ehSigilosoPorNatureza("elogio")).toBe(false);
    expect(ehSigilosoPorNatureza("reclamacao")).toBe(false);
  });

  it("caso ainda não classificado é tratado como sigiloso", () => {
    // Fail-closed: é assim que o caso do QR e o da Ana entram, e a tela precisa
    // mostrar o cadeado antes de alguém classificar.
    expect(ehSigilosoPorNatureza(null)).toBe(true);
  });

  it("a marca de sigilo do tipo sigiloso não pode ser desligada pela tela", () => {
    expect(sigiloResultante("denuncia", false)).toBe(true);
    expect(sigiloResultante("relato_de_conduta", false)).toBe(true);
  });

  it("nos demais tipos vale o que o ouvidor marcou", () => {
    expect(sigiloResultante("reclamacao", true)).toBe(true);
    expect(sigiloResultante("reclamacao", false)).toBe(false);
  });

  it("o caso sem tipo aparece como não classificado, não em branco", () => {
    expect(rotuloDoTipo(null)).toBe("Não classificada");
    expect(rotuloDoTipo("relato_de_conduta")).toBe("Relato de conduta");
  });
});
