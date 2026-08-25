import { describe, expect, it } from "vitest";
import { agruparPorStatus, LABEL_STATUS, ORDEM_DA_FILA } from "./fila";
import type { StatusManifestacao } from "./prazo";

function manifestacao(numero: number, status: StatusManifestacao) {
  return { id: `uuid-${numero}`, numero, status };
}

describe("fila do painel de ouvidoria (issue #320)", () => {
  it("a fila comeca pelo que espera o ouvidor e termina no que ja fechou", () => {
    expect(ORDEM_DA_FILA).toEqual([
      "novo",
      "em_classificacao",
      "aguardando_area",
      "aguardando_manifestante",
      "respondido",
      "encerrado",
    ]);
  });

  it("cada estado tem um nome em portugues para a tela", () => {
    expect(LABEL_STATUS.em_classificacao).toBe("Em classificação");
    expect(LABEL_STATUS.aguardando_area).toBe("Aguardando área");
    expect(LABEL_STATUS.aguardando_manifestante).toBe("Aguardando manifestante");
    expect(ORDEM_DA_FILA.every((s) => typeof LABEL_STATUS[s] === "string")).toBe(true);
  });

  it("agrupa as manifestacoes por estado, na ordem da fila", () => {
    const grupos = agruparPorStatus([
      manifestacao(1, "encerrado"),
      manifestacao(2, "em_classificacao"),
      manifestacao(3, "aguardando_area"),
      manifestacao(4, "em_classificacao"),
    ]);

    expect(grupos.map((g) => g.status)).toEqual([
      "novo",
      "em_classificacao",
      "aguardando_area",
      "aguardando_manifestante",
      "respondido",
      "encerrado",
    ]);
    expect(grupos[1].itens.map((m) => m.numero)).toEqual([2, 4]);
    expect(grupos[0].itens).toEqual([]);
  });

  it("conta quantas manifestacoes esperam acao da ouvidoria", () => {
    const grupos = agruparPorStatus([
      manifestacao(1, "novo"),
      manifestacao(2, "em_classificacao"),
      manifestacao(3, "respondido"),
    ]);

    const esperando = grupos
      .filter((g) => g.status === "novo" || g.status === "em_classificacao")
      .reduce((total, g) => total + g.itens.length, 0);

    expect(esperando).toBe(2);
  });
});
