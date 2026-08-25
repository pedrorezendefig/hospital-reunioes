import { describe, expect, it } from "vitest";
import {
  descricaoDeDesfechoValida,
  estaVigente,
  podeEncerrar,
  podeGerirResponsaveis,
  podeValidar,
  setorTemTitularVigente,
  type Responsavel,
} from "./validacao";

const TITULAR: Responsavel = {
  id: "r1",
  setor: "Recepção",
  papel: "titular",
  nome: "Carlos Titular",
  email: "carlos@hsm.br",
  vigencia_inicio: "2026-01-01",
  vigencia_fim: null,
};

describe("validação e acionamento (issue #325)", () => {
  it("só o caso em classificação oferece o botão de validar", () => {
    expect(podeValidar("em_classificacao")).toBe(true);
    expect(podeValidar("aguardando_area")).toBe(false);
    expect(podeValidar("encerrado")).toBe(false);
  });

  it("quem mantem o cadastro de responsaveis e a diretoria executiva", () => {
    expect(podeGerirResponsaveis("diretoria_executiva")).toBe(true);
    expect(podeGerirResponsaveis("ouvidor")).toBe(false);
    expect(podeGerirResponsaveis(null)).toBe(false);
  });
});

describe("encerramento com desfecho (issue #326)", () => {
  it("caso respondido ou aguardando area oferece o botao de encerrar", () => {
    expect(podeEncerrar("respondido")).toBe(true);
    expect(podeEncerrar("aguardando_area")).toBe(true);
    expect(podeEncerrar("em_classificacao")).toBe(true);
    expect(podeEncerrar("encerrado")).toBe(false);
    expect(podeEncerrar("novo")).toBe(false);
  });

  it("encerramento sem descricao e bloqueado ja na tela", () => {
    expect(descricaoDeDesfechoValida("A area corrigiu o protocolo.")).toBe(true);
    expect(descricaoDeDesfechoValida("   ")).toBe(false);
    expect(descricaoDeDesfechoValida("")).toBe(false);
  });
});

describe("vigencia do responsavel", () => {
  it("vigencia aberta responde hoje", () => {
    expect(estaVigente(TITULAR, "2026-08-25")).toBe(true);
  });

  it("quem sai no dia 31 ainda responde no dia 31", () => {
    const saindo = { ...TITULAR, vigencia_fim: "2026-08-25" };

    expect(estaVigente(saindo, "2026-08-25")).toBe(true);
    expect(estaVigente(saindo, "2026-08-26")).toBe(false);
  });

  it("quem ainda nao entrou no papel nao responde", () => {
    expect(estaVigente({ ...TITULAR, vigencia_inicio: "2026-09-01" }, "2026-08-25")).toBe(false);
  });

  it("setor sem titular vigente aparece como nao acionavel", () => {
    const gestor: Responsavel = { ...TITULAR, id: "r2", papel: "gestor", nome: "Regina" };
    const titularVencido = { ...TITULAR, vigencia_fim: "2026-07-31" };

    expect(setorTemTitularVigente([titularVencido, gestor], "2026-08-25")).toBe(false);
    expect(setorTemTitularVigente([TITULAR, gestor], "2026-08-25")).toBe(true);
  });
});
