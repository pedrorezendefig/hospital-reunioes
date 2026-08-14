import { describe, expect, it } from "vitest";
import { classificarPrazo } from "./prazo";

describe("classificarPrazo (destaque do painel de ouvidoria, issue #292)", () => {
  const hoje = "2026-08-14";

  it("protocolo aberto com prazo estourado é destacado como estourado", () => {
    expect(classificarPrazo("2026-08-13", "aberto", hoje)).toBe("estourado");
  });

  it("protocolo aberto vencendo hoje ou em ate 2 dias fica perto do prazo", () => {
    expect(classificarPrazo("2026-08-14", "aberto", hoje)).toBe("perto");
    expect(classificarPrazo("2026-08-16", "aberto", hoje)).toBe("perto");
  });

  it("protocolo aberto com folga fica normal", () => {
    expect(classificarPrazo("2026-08-17", "aberto", hoje)).toBe("normal");
  });

  it("protocolo respondido nunca recebe destaque, mesmo com prazo passado", () => {
    expect(classificarPrazo("2026-08-01", "respondido", hoje)).toBe("respondido");
  });
});
