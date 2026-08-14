// Selo discreto "N de M assinaram" no banner de ASSINADA (issue #275, ADR 0030).
// So aparece quando houve faltantes; com 100% ClickSign (ou contagem ausente,
// caso legado) o visual atual fica intacto.
import { describe, expect, it } from "vitest";

import { seloAssinaturas } from "./seloAssinaturas";

describe("seloAssinaturas", () => {
  it("mostra o selo quando houve faltantes", () => {
    expect(seloAssinaturas(1, 3)).toBe("1 de 3 assinaram");
  });

  it("fica invisivel com 100% de assinaturas", () => {
    expect(seloAssinaturas(3, 3)).toBeNull();
  });

  it("fica invisivel sem contagem (Reuniao legada)", () => {
    expect(seloAssinaturas(undefined, undefined)).toBeNull();
    expect(seloAssinaturas(1, undefined)).toBeNull();
    expect(seloAssinaturas(undefined, 3)).toBeNull();
  });

  it("ignora contagem invalida", () => {
    expect(seloAssinaturas(4, 3)).toBeNull();
    expect(seloAssinaturas(0, 0)).toBeNull();
  });
});
