import { describe, expect, it } from "vitest";
import {
  ehSigilosoPorNatureza,
  LABEL_TIPO,
  rotuloDoTipo,
  sigiloResultante,
  TIPOS_MANIFESTACAO,
} from "./taxonomia";

describe("taxonomia da manifestação (issue #372)", () => {
  it("a lista é fechada e tem os seis tipos do ADR 0040", () => {
    expect(TIPOS_MANIFESTACAO).toEqual([
      "denuncia",
      "reclamacao",
      "sugestao",
      "elogio",
      "relato_de_conduta",
      "informacao",
    ]);
    expect(Object.keys(LABEL_TIPO).sort()).toEqual([...TIPOS_MANIFESTACAO].sort());
  });

  it("informação é o sexto tipo, com rótulo próprio (issue #490)", () => {
    // O cartaz do ponto de escuta promete a natureza informação a quem lê o
    // QR (RN-88). Sem ela na lista da tela, o seletor da Validação e o da
    // Classificação do Dossiê não têm como oferecê-la.
    expect(TIPOS_MANIFESTACAO).toContain("informacao");
    expect(LABEL_TIPO.informacao).toBe("Informação");
    expect(rotuloDoTipo("informacao")).toBe("Informação");
  });

  it("informação não é sigilosa por natureza, e os dois sigilosos não mudam", () => {
    // A mutação que isto pega: acrescentar "informacao" a TIPOS_SIGILOSOS ao
    // mexer na lista, ou tirar um dos dois de lá para dar lugar ao tipo novo.
    expect(ehSigilosoPorNatureza("informacao")).toBe(false);
    expect(sigiloResultante("informacao", false)).toBe(false);
    expect(ehSigilosoPorNatureza("denuncia")).toBe(true);
    expect(ehSigilosoPorNatureza("relato_de_conduta")).toBe(true);
  });

  it("relato de conduta não é renomeado (ADR 0040, decisão 2)", () => {
    expect(TIPOS_MANIFESTACAO).toContain("relato_de_conduta");
    expect(TIPOS_MANIFESTACAO).not.toContain("relato_conduta");
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
