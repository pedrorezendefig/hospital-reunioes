import { describe, expect, it } from "vitest";
import { CANAIS, montarRegistro, type FormularioRegistro } from "./registro";

const FORMULARIO: FormularioRegistro = {
  canal: "telefone",
  contatoEm: "2026-08-14T16:50",
  categoria: "Demora no atendimento",
  setor: "Recepção",
  resumo: "Espera acima de duas horas.",
  relatoIntegral: "Cheguei às 8h com minha mãe e só fomos atendidos às 10h30.",
  manifestanteNome: "Joana da Silva",
  manifestanteContato: "(31) 99999-0000",
  manifestanteVinculo: "acompanhante",
  anonimo: false,
};

describe("registro manual da ouvidoria (issue #321)", () => {
  it("manda o T0 informado pelo ouvidor, e nao o momento do clique", () => {
    expect(montarRegistro(FORMULARIO).contato_em).toBe("2026-08-14T16:50");
  });

  it("manifestacao anonima vai sem nome, sem contato e sem vinculo", () => {
    const registro = montarRegistro({ ...FORMULARIO, anonimo: true });

    expect(registro.anonimo).toBe(true);
    expect(registro.manifestante_nome).toBeNull();
    expect(registro.manifestante_contato).toBeNull();
    expect(registro.manifestante_vinculo).toBeNull();
    expect(registro.relato_integral).toContain("Cheguei às 8h");
  });

  it("campo de identificacao em branco vira ausente, e nao string vazia", () => {
    const registro = montarRegistro({ ...FORMULARIO, manifestanteContato: "   " });

    expect(registro.manifestante_contato).toBeNull();
    expect(registro.manifestante_nome).toBe("Joana da Silva");
  });

  it("os canais oferecidos sao os do registro manual", () => {
    expect(CANAIS.map((c) => c.valor)).toEqual(["telefone", "presencial", "email"]);
  });
});
