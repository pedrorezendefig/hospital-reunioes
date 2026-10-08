/**
 * O texto de ajuda do Extrato para o setor contra o contrato (issue #769).
 *
 * O contrato `o-que-viaja-ao-setor.json` é travado contra a regra do backend
 * em `test_ouvidoria_o_que_viaja_contrato.py`. Aqui a outra metade: a variante
 * que a tela escolhe para cada combinação de marcas, e a frase de cada
 * variante, dizem o que o contrato diz.
 */

import { describe, expect, it } from "vitest";

import contrato from "./o-que-viaja-ao-setor.json";
import { AJUDA_DO_EXTRATO, varianteDoQueViaja, type VarianteDoQueViaja } from "./o-que-viaja";

// Como a frase nomeia cada coisa que vai à área. A frase pode dizer mais
// (o extrato, o que fazer), mas cada item do contrato aparece por este nome
// quando vai, e não aparece quando não vai.
const NOME_NA_FRASE: Record<string, string> = {
  resumo: "resumo",
  relato_integral: "relato integral",
  identificacao: "nome de quem manifestou",
  paciente: "Paciente do caso",
};

describe("o que vai à área além do extrato (issue #769)", () => {
  it.each(contrato.casos)(
    "sigilo $sigilo_reforcado e anônimo $anonimo é a variante $variante",
    ({ sigilo_reforcado, anonimo, variante }) => {
      expect(varianteDoQueViaja({ sigilo: sigilo_reforcado, anonimo })).toBe(variante);
    }
  );

  it.each(Object.entries(contrato.variantes))("a frase de %s nomeia o que vai, e só o que vai", (variante, vai) => {
    const frase = AJUDA_DO_EXTRATO[variante as VarianteDoQueViaja];
    for (const [item, nome] of Object.entries(NOME_NA_FRASE)) {
      if ((vai as string[]).includes(item)) {
        expect(frase, `${variante} deveria dizer que ${item} vai`).toContain(nome);
      } else {
        expect(frase, `${variante} não pode dizer que ${item} vai`).not.toContain(nome);
      }
    }
  });

  it("o contrato só nomeia o que a frase sabe dizer", () => {
    // Item novo no contrato sem nome aqui passaria pelo laço acima sem ser
    // conferido.
    const itens = new Set(Object.values(contrato.variantes).flat());
    expect([...itens].every((item) => item in NOME_NA_FRASE)).toBe(true);
    expect(itens.size).toBe(4);
  });

  it("nenhuma frase fora do sigilo diz que só o extrato vai", () => {
    for (const variante of ["comum", "anonimo"] as const) {
      expect(AJUDA_DO_EXTRATO[variante]).not.toMatch(/e só ele|não sai daqui|só este texto/);
    }
  });
});
