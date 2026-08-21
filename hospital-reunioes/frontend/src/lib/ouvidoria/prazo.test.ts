import { describe, expect, it } from "vitest";
import { classificarPrazo, EM_ANDAMENTO } from "./prazo";

describe("classificarPrazo (destaque do painel de ouvidoria, issues #292 e #320)", () => {
  const hoje = "2026-08-14";

  it("manifestacao em classificacao com prazo estourado e destacada", () => {
    expect(classificarPrazo("2026-08-13", "em_classificacao", hoje)).toBe("estourado");
  });

  it("manifestacao aguardando a area vencendo em ate 2 dias fica perto do prazo", () => {
    expect(classificarPrazo("2026-08-14", "aguardando_area", hoje)).toBe("perto");
    expect(classificarPrazo("2026-08-16", "aguardando_area", hoje)).toBe("perto");
  });

  it("manifestacao com folga fica normal", () => {
    expect(classificarPrazo("2026-08-17", "em_classificacao", hoje)).toBe("normal");
  });

  it("manifestacao nova ainda conta prazo: o relogio corre desde a entrada", () => {
    expect(classificarPrazo("2026-08-13", "novo", hoje)).toBe("estourado");
  });

  it("respondida e encerrada nao recebem destaque, mesmo com prazo passado", () => {
    expect(classificarPrazo("2026-08-01", "respondido", hoje)).toBe("respondido");
    expect(classificarPrazo("2026-08-01", "encerrado", hoje)).toBe("respondido");
  });

  it("os estados em andamento sao os tres antes da resposta da area", () => {
    expect([...EM_ANDAMENTO].sort()).toEqual(["aguardando_area", "em_classificacao", "novo"]);
  });
});
