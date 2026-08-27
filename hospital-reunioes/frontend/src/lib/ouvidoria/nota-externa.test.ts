import { describe, expect, it } from "vitest";
import {
  ESCALA,
  ROTULO_FONTE,
  formatarNota,
  podeRegistrarNotaExterna,
  validarNota,
} from "./nota-externa";

describe("validarNota (issue #347): cada fonte tem a sua regua", () => {
  it("aceita a nota dentro da escala da fonte", () => {
    expect(validarNota("google", "4,3")).toEqual({ ok: true, valor: 4.3 });
    expect(validarNota("reclame_aqui", "7.8")).toEqual({ ok: true, valor: 7.8 });
  });

  it("recusa 8 no Google e aceita 8 no Reclame Aqui", () => {
    // A prova de que a regua e por fonte: um teto unico de 10 aceitaria as
    // duas, e o relatorio imprimiria "8,0 de 5".
    expect(validarNota("google", "8").ok).toBe(false);
    expect(validarNota("reclame_aqui", "8").ok).toBe(true);
  });

  it("recusa nota negativa e texto que nao e numero", () => {
    expect(validarNota("google", "-1").ok).toBe(false);
    expect(validarNota("google", "otima").ok).toBe(false);
    expect(validarNota("google", "").ok).toBe(false);
  });

  it("o motivo da recusa cita a escala da fonte", () => {
    const recusa = validarNota("google", "8");
    expect(recusa.ok).toBe(false);
    if (!recusa.ok) expect(recusa.erro).toContain("0 a 5");
  });
});

describe("formatarNota: o numero nunca sai sem a regua", () => {
  it("mostra a nota com a escala ao lado", () => {
    expect(formatarNota(4.3, ESCALA.google)).toBe("4,3 de 5");
    expect(formatarNota(7.8, ESCALA.reclame_aqui)).toBe("7,8 de 10");
  });

  it("nota ausente diz que nao ha registro, e nunca zero", () => {
    expect(formatarNota(null, ESCALA.google)).toBe("sem registro");
  });
});

describe("podeRegistrarNotaExterna: so os dois perfis da Ouvidoria", () => {
  it("ouvidor e diretoria executiva registram", () => {
    expect(podeRegistrarNotaExterna("ouvidor")).toBe(true);
    expect(podeRegistrarNotaExterna("diretoria_executiva")).toBe(true);
  });

  it("quem nao tem perfil de ouvidoria nao registra", () => {
    expect(podeRegistrarNotaExterna(null)).toBe(false);
    expect(podeRegistrarNotaExterna(undefined)).toBe(false);
    expect(podeRegistrarNotaExterna("secretaria")).toBe(false);
  });
});

describe("ROTULO_FONTE: o nome que o humano le", () => {
  it("traduz as duas fontes", () => {
    expect(ROTULO_FONTE.google).toBe("Google");
    expect(ROTULO_FONTE.reclame_aqui).toBe("Reclame Aqui");
  });
});
