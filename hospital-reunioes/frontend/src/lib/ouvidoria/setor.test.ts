import { describe, expect, it } from "vitest";
import { mensagemDoPortal, montarFormularioDeResposta, respostaDoSetorValida } from "./setor";

describe("portal do setor (issue #326)", () => {
  it("a resposta precisa dizer o que foi feito: espaco em branco nao vale", () => {
    expect(respostaDoSetorValida("Conversamos com a equipe e corrigimos o fluxo.")).toBe(true);
    expect(respostaDoSetorValida("   ")).toBe(false);
    expect(respostaDoSetorValida("")).toBe(false);
  });

  it("token invalido ou expirado vira mensagem clara, sem vazar o caso", () => {
    expect(mensagemDoPortal(404, undefined)).toBe(
      "Este link não é válido. Confira se o endereço veio completo no email da Ouvidoria."
    );
    expect(mensagemDoPortal(410, "Este link expirou")).toBe("Este link expirou");
    expect(mensagemDoPortal(500, undefined)).toBe("Não foi possível carregar este link agora. Tente novamente.");
  });

  it("o formulario multipart leva a resposta e os anexos escolhidos", () => {
    const arquivo = new File(["conteudo"], "evidencia.pdf", { type: "application/pdf" });
    const form = montarFormularioDeResposta("  Fizemos a correção.  ", [arquivo]);

    expect(form.get("resposta")).toBe("Fizemos a correção.");
    expect(form.getAll("arquivos")).toHaveLength(1);
  });
});
