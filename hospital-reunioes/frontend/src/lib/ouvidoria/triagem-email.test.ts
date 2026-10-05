/**
 * As regras puras da Triagem de e-mail (issue #648, PRD #646, ADR 0051).
 *
 * Quem vê a porta, como o remetente e a chegada aparecem, e as marcas do item.
 * O gate de verdade é o backend (403); aqui só não se oferece o caminho que
 * terminaria nele.
 */

import { describe, expect, it } from "vitest";

import {
  avisoDosExcedentes,
  chegadaParaCampoLocal,
  formatarChegada,
  formularioDaPreCarga,
  marcasDoEmail,
  nomeDoRemetente,
  podeVerTriagemDeEmail,
  rotuloDoEstado,
  rotuloDosAnexos,
} from "./triagem-email";

describe("quem vê a Triagem de e-mail", () => {
  it("os dois perfis da Ouvidoria veem", () => {
    expect(podeVerTriagemDeEmail("ouvidor")).toBe(true);
    expect(podeVerTriagemDeEmail("diretoria_executiva")).toBe(true);
  });

  it("quem está fora da Ouvidoria não vê, e Super admin também fica de fora", () => {
    expect(podeVerTriagemDeEmail(null)).toBe(false);
    expect(podeVerTriagemDeEmail(undefined)).toBe(false);
    expect(podeVerTriagemDeEmail("")).toBe(false);
    expect(podeVerTriagemDeEmail("secretaria")).toBe(false);
    expect(podeVerTriagemDeEmail("super_admin")).toBe(false);
  });
});

describe("como o e-mail aparece na lista", () => {
  it("o remetente aparece pelo nome, e pelo endereço quando não há nome", () => {
    expect(nomeDoRemetente({ remetente_nome: "Joana da Silva", remetente_endereco: "joana@gmail.com" })).toBe(
      "Joana da Silva"
    );
    expect(nomeDoRemetente({ remetente_nome: null, remetente_endereco: "joana@gmail.com" })).toBe(
      "joana@gmail.com"
    );
    expect(nomeDoRemetente({ remetente_nome: "  ", remetente_endereco: "joana@gmail.com" })).toBe(
      "joana@gmail.com"
    );
  });

  it("a chegada sai no fuso do hospital", () => {
    // 14h02 em UTC são 11h02 no horário de Brasília.
    expect(formatarChegada("2026-09-10T14:02:10.000Z")).toBe("10/09/2026 11:02");
  });

  it("a contagem de anexos em palavras", () => {
    expect(rotuloDosAnexos(0)).toBe("Sem anexo");
    expect(rotuloDosAnexos(1)).toBe("1 anexo");
    expect(rotuloDosAnexos(3)).toBe("3 anexos");
  });

  it("os anexos além do teto de quantidade viram um aviso só, com o motivo", () => {
    const motivo = "passa de 20 anexos por e-mail, o original está na caixa ouvidoria@";
    expect(avisoDosExcedentes({})).toBeNull();
    expect(avisoDosExcedentes({ anexos_excedentes: 0, motivo_dos_excedentes: null })).toBeNull();
    expect(avisoDosExcedentes({ anexos_excedentes: 980, motivo_dos_excedentes: motivo })).toBe(
      `Mais 980 anexos: ${motivo}`
    );
    expect(avisoDosExcedentes({ anexos_excedentes: 1, motivo_dos_excedentes: motivo })).toBe(
      `Mais 1 anexo: ${motivo}`
    );
  });

  it("as marcas do item: interno e incompleto", () => {
    expect(marcasDoEmail({ interno: false, incompleto: false })).toEqual([]);
    expect(marcasDoEmail({ interno: true, incompleto: false })).toEqual(["Interno"]);
    expect(marcasDoEmail({ interno: true, incompleto: true })).toEqual(["Interno", "Incompleto"]);
  });
});

describe("a pré-carga de virar manifestação (issue #650)", () => {
  const PRE_CARGA = {
    email_recebido_id: "e1",
    canal: "email" as const,
    contato_em: "2026-09-10T14:02:10.000Z",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "joana.silva@gmail.com",
    resumo: "",
    relato_integral: "Esperei três horas na recepção sem informação nenhuma.",
    anexos: [],
  };

  it("a chegada em UTC vira a hora de Brasília do campo, com os segundos", () => {
    // 14h02 em UTC é 11h02 em Brasília. Os segundos ficam: o T0 é a chegada
    // exata, e não o minuto arredondado.
    expect(chegadaParaCampoLocal("2026-09-10T14:02:10.000Z")).toBe("2026-09-10T11:02:10");
  });

  it("a chegada de madrugada em UTC cai no dia anterior em Brasília", () => {
    expect(chegadaParaCampoLocal("2026-09-11T01:30:00+00:00")).toBe("2026-09-10T22:30:00");
  });

  it("o formulário nasce com o e-mail e deixa tipo, setor e resumo para o ouvidor", () => {
    const form = formularioDaPreCarga(PRE_CARGA);

    expect(form.canal).toBe("email");
    expect(form.contatoEm).toBe("2026-09-10T11:02:10");
    expect(form.manifestanteNome).toBe("Joana da Silva");
    expect(form.manifestanteContato).toBe("joana.silva@gmail.com");
    expect(form.relatoIntegral).toBe("Esperei três horas na recepção sem informação nenhuma.");
    expect(form.resumo).toBe("");
    expect(form.tipoManifestacao).toBe("");
    expect(form.setor).toBe("");
    expect(form.anonimo).toBe(false);
  });
});

describe("o estado do item na lista", () => {
  it("pendente não tem marca; os decididos dizem o que viraram", () => {
    expect(rotuloDoEstado("pendente")).toBeNull();
    expect(rotuloDoEstado("virou_manifestacao")).toBe("Virou manifestação");
    expect(rotuloDoEstado("juntado")).toBe("Juntado a um caso");
    expect(rotuloDoEstado("descartado")).toBe("Descartado");
  });
});
