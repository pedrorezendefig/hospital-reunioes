/**
 * A régua da Manifestação guiada (issue #1620, ADR 0086 decisão 6).
 *
 * O que o passo a passo decide antes de falar com o servidor: se cada passo
 * já pode seguir e o que vai no envio. A mesma régua vale de novo no backend.
 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  AVISO_SO_TELEFONE,
  EXPECTATIVAS,
  PERIODOS,
  montarEnvio,
  oQueOPassoAPassoContou,
  passoCompleto,
  precisaDoAvisoDoEmail,
  type FormularioPublico,
} from "./publico";

/** O passo a passo inteiro respondido, por quem se identifica e deixa e-mail. */
function respondido(mudancas: Partial<FormularioPublico> = {}): FormularioPublico {
  return {
    anonimo: false,
    natureza: null,
    sobre: "mim",
    dataOcorrencia: "2026-11-10",
    periodo: "tarde",
    horaAprox: "",
    local: "Emergência adulta",
    localEhAla: false,
    quarto: "",
    relato: "Esperei duas horas na emergência.",
    profissionais: "",
    pacienteNome: "",
    pacienteNascimento: "",
    expectativa: "resposta",
    nome: "Maria Souza",
    telefone: "",
    contato: "maria@exemplo.com",
    p: null,
    ...mudancas,
  };
}

describe("as listas fechadas do passo a passo", () => {
  it("oferece os quatro períodos do anexo, na ordem do dia", () => {
    expect(PERIODOS.map((p) => p.rotulo)).toEqual(["Manhã", "Tarde", "Noite", "Madrugada"]);
    expect(PERIODOS.map((p) => p.valor)).toEqual(["manha", "tarde", "noite", "madrugada"]);
  });

  it("oferece as três expectativas do anexo", () => {
    expect(EXPECTATIVAS.map((e) => e.rotulo)).toEqual([
      "Uma resposta",
      "Uma providência",
      "Só registrar",
    ]);
    expect(EXPECTATIVAS.map((e) => e.valor)).toEqual(["resposta", "providencia", "registro"]);
  });
});

describe("cada passo só segue com o obrigatório", () => {
  it("passo 2 pede de quem é o relato, e a natureza é opcional", () => {
    expect(passoCompleto(2, respondido({ sobre: null }))).toBe(false);
    expect(passoCompleto(2, respondido({ natureza: null }))).toBe(true);
  });

  it("passo 3 pede data, período e lugar, e a hora e o quarto são opcionais", () => {
    expect(passoCompleto(3, respondido({ dataOcorrencia: "" }))).toBe(false);
    expect(passoCompleto(3, respondido({ periodo: null }))).toBe(false);
    expect(passoCompleto(3, respondido({ local: "" }))).toBe(false);
    expect(passoCompleto(3, respondido({ horaAprox: "", quarto: "" }))).toBe(true);
  });

  it("passo 4 pede o relato e o que a pessoa espera, e o resto é opcional", () => {
    expect(passoCompleto(4, respondido({ relato: "   " }))).toBe(false);
    expect(passoCompleto(4, respondido({ expectativa: null }))).toBe(false);
    expect(passoCompleto(4, respondido({ profissionais: "", pacienteNascimento: "" }))).toBe(true);
  });

  it("passo 5 de quem se identifica pede o nome e um telefone ou e-mail", () => {
    expect(passoCompleto(5, respondido({ nome: " " }))).toBe(false);
    expect(passoCompleto(5, respondido({ contato: "", telefone: "" }))).toBe(false);
    expect(passoCompleto(5, respondido({ contato: "", telefone: "(21) 99999-0000" }))).toBe(true);
    expect(passoCompleto(5, respondido({ contato: "maria@exemplo.com", telefone: "" }))).toBe(true);
  });

  it("passo 5 não aceita e-mail que não é e-mail nem telefone sem número", () => {
    expect(passoCompleto(5, respondido({ contato: "maria", telefone: "" }))).toBe(false);
    expect(passoCompleto(5, respondido({ contato: "", telefone: "não tenho" }))).toBe(false);
  });

  // Os mesmos casos que o pytest manda pela rota (backend/tests/
  // emails_do_passo_a_passo.json): o e-mail que a tela libera e o servidor
  // recusa volta como 422, e quem se identifica fica sem canal.
  const { casos } = JSON.parse(
    readFileSync(
      new URL("../../../../backend/tests/emails_do_passo_a_passo.json", import.meta.url),
      "utf8"
    )
  ) as { casos: { email: string; aceito: boolean }[] };

  it.each(casos)("passo 5 concorda com o servidor sobre $email", ({ email, aceito }) => {
    expect(passoCompleto(5, respondido({ contato: email, telefone: "" }))).toBe(aceito);
  });

  it("passo 5 do anônimo segue sem campo nenhum", () => {
    expect(passoCompleto(5, respondido({ anonimo: true, nome: "", contato: "", telefone: "" }))).toBe(
      true
    );
  });
});

describe("o aviso de quem deixa só o telefone", () => {
  it("aparece para quem se identifica com telefone e sem e-mail", () => {
    expect(precisaDoAvisoDoEmail(respondido({ contato: "", telefone: "21999990000" }))).toBe(true);
  });

  it("não aparece com e-mail, nem no anônimo", () => {
    expect(precisaDoAvisoDoEmail(respondido({ telefone: "21999990000" }))).toBe(false);
    expect(
      precisaDoAvisoDoEmail(respondido({ anonimo: true, contato: "", telefone: "21999990000" }))
    ).toBe(false);
  });

  it("diz que as respostas saem por e-mail", () => {
    expect(AVISO_SO_TELEFONE).toBe(
      "As respostas da Ouvidoria saem por e-mail. Só com o telefone, você não recebe o aviso de que a manifestação chegou nem a resposta final."
    );
  });
});

describe("o envio do passo a passo", () => {
  it("leva quando, onde e o que a pessoa espera", () => {
    const envio = montarEnvio(respondido({ horaAprox: "14:30" }));

    expect(envio).toMatchObject({
      sobre: "mim",
      data_ocorrencia: "2026-11-10",
      periodo: "tarde",
      hora_aprox: "14:30",
      local_informado: "Emergência adulta",
      expectativa: "resposta",
      contato: "maria@exemplo.com",
    });
    expect(envio).not.toHaveProperty("telefone");
    expect(envio).not.toHaveProperty("quarto");
  });

  it("leva o quarto só quando o lugar é ala de internação", () => {
    expect(montarEnvio(respondido({ quarto: "Apto 204", localEhAla: true })).quarto).toBe(
      "Apto 204"
    );
    // Quem digitou o quarto e trocou para um lugar que não é ala não leva o
    // quarto do lugar de antes.
    expect(montarEnvio(respondido({ quarto: "Apto 204", localEhAla: false }))).not.toHaveProperty(
      "quarto"
    );
  });

  it("leva o telefone de quem se identifica, e nunca o do anônimo", () => {
    expect(montarEnvio(respondido({ telefone: "21999990000" })).telefone).toBe("21999990000");
    expect(
      montarEnvio(respondido({ anonimo: true, telefone: "21999990000" }))
    ).not.toHaveProperty("telefone");
  });

  it("leva os profissionais citados", () => {
    expect(montarEnvio(respondido({ profissionais: "Enfermeira da noite" })).profissionais).toBe(
      "Enfermeira da noite"
    );
  });

  it("leva o nascimento do paciente quando o relato é sobre outra pessoa, mesmo no anônimo", () => {
    const envio = montarEnvio(
      respondido({
        anonimo: true,
        sobre: "outra_pessoa",
        pacienteNome: "José Souza",
        pacienteNascimento: "1948-03-02",
      })
    );

    expect(envio).toMatchObject({ paciente_nome: "José Souza", paciente_nascimento: "1948-03-02" });
  });

  it("leva a data de nascimento de quem fala de si e se identificou", () => {
    expect(montarEnvio(respondido({ pacienteNascimento: "1980-01-15" })).paciente_nascimento).toBe(
      "1980-01-15"
    );
  });

  it("não leva a data de nascimento do anônimo que fala de si", () => {
    expect(
      montarEnvio(respondido({ anonimo: true, pacienteNascimento: "1980-01-15" }))
    ).not.toHaveProperty("paciente_nascimento");
  });
});

describe("o que o passo a passo contou, para o Dossiê", () => {
  it("diz quando, onde, quem atendeu, o nascimento, o telefone e o que a pessoa espera", () => {
    expect(
      oQueOPassoAPassoContou({
        data_ocorrencia: "2026-11-10",
        periodo: "noite",
        hora_aprox: "22:15:00",
        local_informado: "Internação · Ala 2A",
        quarto: "Apto 204",
        profissionais: "Enfermeira do plantão",
        paciente_nascimento: "1948-03-02",
        expectativa: "providencia",
        manifestante_telefone: "(21) 98888-7777",
      })
    ).toEqual([
      { rotulo: "Quando", valor: "10/11/2026, noite, por volta das 22:15" },
      { rotulo: "Onde", valor: "Internação · Ala 2A, quarto Apto 204" },
      { rotulo: "Profissionais citados", valor: "Enfermeira do plantão" },
      { rotulo: "Nascimento do paciente", valor: "02/03/1948" },
      { rotulo: "O que espera", valor: "Uma providência" },
      { rotulo: "Telefone", valor: "(21) 98888-7777" },
    ]);
  });

  it("o que não foi informado não vira linha", () => {
    expect(
      oQueOPassoAPassoContou({
        data_ocorrencia: "2026-11-10",
        periodo: "tarde",
        local_informado: "Emergência adulta",
        expectativa: "registro",
      })
    ).toEqual([
      { rotulo: "Quando", valor: "10/11/2026, tarde" },
      { rotulo: "Onde", valor: "Emergência adulta" },
      { rotulo: "O que espera", valor: "Só registrar" },
    ]);
  });

  it("o caso de antes do passo a passo não tem nada a contar", () => {
    expect(oQueOPassoAPassoContou({})).toEqual([]);
  });
});
