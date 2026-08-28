import { describe, expect, it } from "vitest";
import { descreverOrigem, QR_NAO_PROVA_PRESENCA } from "./origem";

describe("origem do caso no Dossiê (issue #375, itens 10 e 11)", () => {
  it("mostra de qual cartaz o caso veio", () => {
    // Item 11: `canal_setor` e `canal_ponto` eram gravados e nunca lidos.
    const origem = descreverOrigem({
      canal: "qr",
      canal_setor: "Recepção",
      canal_ponto: "Poltrona 12",
    });

    expect(origem?.titulo).toContain("QR");
    expect(origem?.detalhe).toBe("Recepção, Poltrona 12");
  });

  it("avisa que ler o QR não prova que a pessoa esteve no lugar", () => {
    // Item 10, decisão 4: qualquer pessoa monta a URL do formulário com
    // `?setor=Recepção&ponto=Poltrona 12`. Se o ouvidor ler "qr + Poltrona 12"
    // como evidência de presença física, lê errado.
    const origem = descreverOrigem({
      canal: "qr",
      canal_setor: "Recepção",
      canal_ponto: "Poltrona 12",
    });

    expect(origem?.aviso).toBe(QR_NAO_PROVA_PRESENCA);
  });

  it("caso do QR sem ponto mostra só o setor do cartaz", () => {
    // É o que acontece com caso anônimo desde a decisão 5: o ponto não é
    // gravado, e a linha não pode ficar com uma vírgula solta no fim.
    const origem = descreverOrigem({
      canal: "qr",
      canal_setor: "Recepção",
      canal_ponto: null,
    });

    expect(origem?.detalhe).toBe("Recepção");
  });

  it("caso anônimo não mostra o ponto do cartaz, mesmo se ele estiver gravado", () => {
    // Defesa dupla da decisão 5. A rota pública parou de gravar e a migration
    // 084 limpou o que já estava lá, mas a tela é a última porta: em sala
    // pequena, "Poltrona 12" em tal dia reidentifica quem pediu anonimato,
    // cruzando com o registro de atendimento do hospital.
    const origem = descreverOrigem({
      canal: "qr",
      canal_setor: "Recepção",
      canal_ponto: "Poltrona 12",
      anonimo: true,
    });

    expect(origem?.detalhe).toBe("Recepção");
  });

  it("caso do site não fala de cartaz nenhum e não leva o aviso do QR", () => {
    const origem = descreverOrigem({
      canal: "site",
      canal_setor: null,
      canal_ponto: null,
    });

    expect(origem?.titulo).toContain("site");
    expect(origem?.detalhe).toBeNull();
    expect(origem?.aviso).toBeNull();
  });

  it("caso registrado pela ouvidoria não vira bloco de origem de cartaz", () => {
    expect(descreverOrigem({ canal: "telefone", canal_setor: null, canal_ponto: null })?.aviso).toBeNull();
  });

  it("caso sem canal nenhum não desenha bloco", () => {
    expect(descreverOrigem({ canal: null, canal_setor: null, canal_ponto: null })).toBeNull();
  });
});
