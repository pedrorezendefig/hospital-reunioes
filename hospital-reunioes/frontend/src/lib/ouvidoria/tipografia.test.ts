/**
 * A regra da caixa alta da Ouvidoria (issue #489, PRD #471, RN-76, D-19).
 *
 * Aqui se trava só a régua. Quem a aplica nas telas é a varredura de
 * `app/ouvidoria/tipografia.test.tsx`, que renderiza a fila e o Dossiê e passa
 * por esta função tudo o que sai em maiúscula.
 */

import { describe, expect, it } from "vitest";

import { TETO_DO_ROTULO_CURTO, ehRotuloCurto } from "./tipografia";

describe("o que pode ir para caixa alta (RN-76)", () => {
  it("rótulo de botão, de campo e de seção passa", () => {
    for (const rotulo of [
      "Encerrar",
      "Validar e acionar",
      "Abrir manifestação",
      "Classificação e sigilo",
      "Notificações enviadas",
      "Respostas anteriores (3)",
      // O maior rótulo do módulo hoje, e a razão do teto ser onde ele está.
      "Aguardando seu encerramento",
    ]) {
      expect(ehRotuloCurto(rotulo)).toBe(true);
    }
  });

  it("texto corrido não passa", () => {
    for (const texto of [
      "Paciente relata espera de mais de três horas na recepção do ambulatório.",
      "O prazo da área para de correr. Na volta, o tempo parado é devolvido.",
      "As manifestações chegam pelo atendimento da Ana e pelo registro da ouvidoria.",
    ]) {
      expect(ehRotuloCurto(texto)).toBe(false);
    }
  });

  it("rótulo com nome e data grudados vira texto corrido", () => {
    // É o caso que abriu a issue no Dossiê: o crédito da resposta morava dentro
    // do título da seção, e "RESPOSTA DA ÁREA (JOANA DA SILVA, 20/08/2026
    // 16:00)" saía inteiro em maiúscula, nome próprio e tudo.
    expect(ehRotuloCurto("Resposta da área")).toBe(true);
    expect(ehRotuloCurto("Resposta da área (Joana da Silva, 20/08/2026 16:00)")).toBe(false);
  });

  it("frase curta continua sendo frase", () => {
    // Só o comprimento não basta: o ponto final denuncia a frase que caberia
    // no teto e mesmo assim grita.
    const curta = "Ninguém respondeu ainda.";
    expect(curta.length).toBeLessThanOrEqual(TETO_DO_ROTULO_CURTO);
    expect(ehRotuloCurto(curta)).toBe(false);
    expect(ehRotuloCurto("Cartaz A5")).toBe(true);
  });

  it("o teto é de caractere, não de palavra", () => {
    // Três palavras compridas passam do teto; seis palavras curtas não.
    expect(ehRotuloCurto("Reabertura circunstanciada do caso")).toBe(false);
    expect(ehRotuloCurto("Ir ao topo da fila já")).toBe(true);
  });

  it("quebra de linha e espaço sobrando não contam como texto", () => {
    // O `textContent` do JSX indentado vem com as quebras do código dentro.
    expect(ehRotuloCurto("\n              Resumo\n            ")).toBe(true);
    expect(ehRotuloCurto("")).toBe(true);
    expect(ehRotuloCurto(null)).toBe(true);
  });
});
