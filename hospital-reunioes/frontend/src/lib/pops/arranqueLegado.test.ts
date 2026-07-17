import { describe, it, expect } from "vitest";
import { PROMPT_ARRANQUE_LEGADO, exibirArranqueLegado } from "./arranqueLegado";

// Mensagem de boas-vindas do assistente: presente em toda conversa nova.
const boasVindas = { role: "assistant" as const };
const mensagemUsuario = { role: "user" as const };

describe("exibirArranqueLegado (issue #234)", () => {
  it("aparece com material anexado e conversa vazia (só boas-vindas)", () => {
    expect(exibirArranqueLegado(1, [boasVindas])).toBe(true);
    expect(exibirArranqueLegado(3, [boasVindas])).toBe(true);
  });

  it("não aparece sem material anexado", () => {
    expect(exibirArranqueLegado(0, [boasVindas])).toBe(false);
  });

  it("não aparece depois que o Elaborador enviou mensagem", () => {
    expect(exibirArranqueLegado(1, [boasVindas, mensagemUsuario])).toBe(false);
    expect(exibirArranqueLegado(1, [boasVindas, mensagemUsuario, boasVindas])).toBe(false);
  });
});

describe("PROMPT_ARRANQUE_LEGADO (issue #234)", () => {
  it("pede a nova versão a partir do material, mantendo estrutura e conteúdo", () => {
    const prompt = PROMPT_ARRANQUE_LEGADO.toLowerCase();
    expect(prompt).toContain("material anexado");
    expect(prompt).toContain("estrutura");
    expect(prompt).toContain("conteúdo");
  });

  it("é texto visível ao usuário sem travessão nem meia-risca (ADR 0013)", () => {
    const travessao = String.fromCharCode(0x2014);
    const meiaRisca = String.fromCharCode(0x2013);
    expect(PROMPT_ARRANQUE_LEGADO).not.toContain(travessao);
    expect(PROMPT_ARRANQUE_LEGADO).not.toContain(meiaRisca);
  });
});
