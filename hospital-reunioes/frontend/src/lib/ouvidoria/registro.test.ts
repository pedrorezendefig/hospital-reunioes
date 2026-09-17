import { describe, expect, it } from "vitest";
import {
  CANAIS,
  CANAL_PADRAO,
  EXTENSOES_ACEITAS,
  montarRegistro,
  type FormularioRegistro,
} from "./registro";

const FORMULARIO: FormularioRegistro = {
  canal: "telefone",
  contatoEm: "2026-08-14T16:50",
  tipoManifestacao: "reclamacao",
  categoria: "Demora no atendimento",
  setor: "Recepção",
  resumo: "Espera acima de duas horas.",
  relatoIntegral: "Cheguei às 8h com minha mãe e só fomos atendidos às 10h30.",
  manifestanteNome: "Joana da Silva",
  manifestanteContato: "(31) 99999-0000",
  manifestanteVinculo: "acompanhante",
  pacienteNome: "",
  pacienteReferencia: "",
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

  it("manda o paciente do caso que o ouvidor anotou do telefonema", () => {
    // Issue #663, historia 14 do PRD #659: o caso do telefonema fica igual ao
    // do QR.
    const registro = montarRegistro({
      ...FORMULARIO,
      pacienteNome: "Maria Souza",
      pacienteReferencia: "Leito 12, dia 09/09",
    });

    expect(registro.paciente_nome).toBe("Maria Souza");
    expect(registro.paciente_referencia).toBe("Leito 12, dia 09/09");
  });

  it("registro sem paciente vai com os dois campos nulos, e nao em branco", () => {
    const registro = montarRegistro(FORMULARIO);

    expect(registro.paciente_nome).toBeNull();
    expect(registro.paciente_referencia).toBeNull();
  });

  it("manifestacao anonima preserva o paciente, que e outra pessoa", () => {
    // Decisao 3 do ADR 0052: o anonimato protege quem manifesta. Sem o
    // paciente, o caso do acompanhante anonimo chega inutil a area.
    const registro = montarRegistro({
      ...FORMULARIO,
      anonimo: true,
      pacienteNome: "Maria Souza",
      pacienteReferencia: "Leito 12",
    });

    expect(registro.paciente_nome).toBe("Maria Souza");
    expect(registro.paciente_referencia).toBe("Leito 12");
    expect(registro.manifestante_nome).toBeNull();
  });

  it("campo de identificacao em branco vira ausente, e nao string vazia", () => {
    const registro = montarRegistro({ ...FORMULARIO, manifestanteContato: "   " });

    expect(registro.manifestante_contato).toBeNull();
    expect(registro.manifestante_nome).toBe("Joana da Silva");
  });

  it("manda o tipo da lista fechada, e o rotulo humano so como texto", () => {
    // Issue #372: e o tipo que decide o sigilo. O rotulo continua indo, mas so
    // descreve o caso.
    const registro = montarRegistro({ ...FORMULARIO, tipoManifestacao: "relato_de_conduta" });

    expect(registro.tipo_manifestacao).toBe("relato_de_conduta");
    expect(registro.categoria).toBe("Demora no atendimento");
  });

  it("registro sem rotulo vai sem categoria, e nao com string vazia", () => {
    expect(montarRegistro({ ...FORMULARIO, categoria: "  " }).categoria).toBeNull();
  });

  it("os canais oferecidos sao os do registro manual, com WhatsApp na frente", () => {
    // Issue #721: a ordem e o que o ouvidor ve no select, e o primeiro da lista
    // e o padrao do formulario. WhatsApp vem primeiro porque e de onde mais
    // chega; `ana` e o canal aberto (`site`, `qr`) nao sao registro manual.
    expect(CANAIS.map((c) => c.valor)).toEqual([
      "whatsapp",
      "telefone",
      "presencial",
      "email",
      "instagram",
      "reclame_aqui",
      "google",
    ]);
    expect(CANAL_PADRAO).toBe("whatsapp");
  });

  it("o seletor de arquivo oferece so o que o backend aceita", () => {
    // Espelho de TIPOS_PERMITIDOS em app/services/ouvidoria_anexos.py: se as
    // listas divergirem, o ouvidor escolhe um arquivo que so e recusado depois
    // de o caso ja existir.
    expect(EXTENSOES_ACEITAS.split(",").sort()).toEqual(
      [
        ".doc",
        ".docx",
        ".heic",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mp3",
        ".odt",
        ".ogg",
        ".pdf",
        ".png",
        ".txt",
        ".wav",
        ".webp",
      ].sort()
    );
  });
});
