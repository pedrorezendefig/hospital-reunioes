import { describe, expect, it } from "vitest";
import { descreverNaturezaInformada, SUGESTAO_NAO_E_CLASSIFICACAO } from "./natureza-informada";

describe("a natureza informada pelo manifestante no Dossiê (issue #474)", () => {
  it("mostra a natureza que o manifestante marcou, com o rótulo humano dela", () => {
    const natureza = descreverNaturezaInformada({ natureza_informada: "reclamacao" });

    expect(natureza?.rotulo).toBe("Reclamação");
  });

  it("diz que quem informou foi o manifestante, e não a Ouvidoria", () => {
    // O ponto da issue: sem a origem escrita na linha, o ouvidor lê a palavra
    // como se o caso já estivesse classificado.
    const natureza = descreverNaturezaInformada({ natureza_informada: "elogio" });

    expect(natureza?.titulo).toContain("manifestante");
    expect(natureza?.titulo).toContain("Elogio");
  });

  it("avisa que é sugestão, não a classificação do caso", () => {
    const natureza = descreverNaturezaInformada({ natureza_informada: "sugestao" });

    expect(natureza?.aviso).toBe(SUGESTAO_NAO_E_CLASSIFICACAO);
  });

  it("caso sem natureza informada não desenha bloco nenhum", () => {
    expect(descreverNaturezaInformada({ natureza_informada: null })).toBeNull();
  });

  it("valor fora da lista fechada não desenha bloco", () => {
    // A lista é fechada na tela pública, na aplicação e no CHECK da migration
    // 090. Valor fora dela é linha corrompida, e imprimir texto cru do banco na
    // tela do ouvidor seria dar palanque a ele.
    expect(descreverNaturezaInformada({ natureza_informada: "denuncia" })).toBeNull();
  });
});
