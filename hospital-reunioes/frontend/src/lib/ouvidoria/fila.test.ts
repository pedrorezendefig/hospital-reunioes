import { describe, expect, it } from "vitest";
import {
  agruparPorStatus,
  LABEL_STATUS,
  classeDoStatus,
  ORDEM_DA_FILA,
  rotuloDoStatus,
} from "./fila";
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

describe("estado que a tela ainda não conhece (issue #375, item 15)", () => {
  // O enum do frontend é a lista que ESTA versão da tela conhece. O caso deste
  // bloco é justamente o estado que ela não conhece, então ele entra por um
  // apelido tipado: fingir que "em_recurso" está no enum é o que deixaria o
  // `tsc` avaliar as comparações como impossíveis.
  const DESCONHECIDO = "em_recurso" as StatusManifestacao;

  it("manifestação com status fora do enum aparece, em grupo próprio", () => {
    // Backend novo com frontend velho, ou estado criado por migration antes
    // do deploy da tela: o caso sumia da fila em silêncio, e um caso com prazo
    // estourado ficava invisível para o ouvidor. Sumir é o pior desfecho.
    const grupos = agruparPorStatus([
      manifestacao(1, "aguardando_area"),
      manifestacao(2, DESCONHECIDO),
    ]);

    const desconhecido = grupos.find((g) => g.status === DESCONHECIDO);
    expect(desconhecido).toBeDefined();
    expect(desconhecido?.itens.map((m) => m.numero)).toEqual([2]);
  });

  it("o estado desconhecido entra no fim, sem mexer na ordem do trabalho", () => {
    const grupos = agruparPorStatus([manifestacao(1, DESCONHECIDO)]);

    expect(grupos.map((g) => g.status)).toEqual([...ORDEM_DA_FILA, DESCONHECIDO]);
  });

  it("dois casos no mesmo estado desconhecido viram um grupo só", () => {
    const grupos = agruparPorStatus([
      manifestacao(1, DESCONHECIDO),
      manifestacao(2, DESCONHECIDO),
    ]);

    expect(grupos.filter((g) => g.status === DESCONHECIDO)).toHaveLength(1);
  });

  it("nenhum caso desconhecido não cria grupo nenhum a mais", () => {
    const grupos = agruparPorStatus([manifestacao(1, "novo")]);

    expect(grupos.map((g) => g.status)).toEqual(ORDEM_DA_FILA);
  });

  it("o rótulo do estado desconhecido é o próprio código, e não um vazio", () => {
    // A tela lê LABEL_STATUS[status]. Sem isto, o cabeçalho do grupo sairia em
    // branco e o ouvidor não saberia nem o que está olhando.
    expect(rotuloDoStatus(DESCONHECIDO)).toBe("em_recurso");
    expect(rotuloDoStatus("aguardando_area")).toBe("Aguardando área");
  });
});

describe("cor do selo de status (issue #375, item 15)", () => {
  const DESCONHECIDO = "em_recurso" as StatusManifestacao;

  it("cada estado conhecido tem a sua cor", () => {
    expect(classeDoStatus("aguardando_area")).toContain("amber");
    expect(classeDoStatus("encerrado")).toContain("slate");
  });

  it("estado desconhecido ganha cor neutra, e não a string undefined", () => {
    // As telas interpolam a classe direto no `className`. Com o mapa indexado
    // sem guarda, o estado novo que o item 15 passou a EXIBIR saía com
    // `className="... undefined"`: selo sem fundo nem cor de texto.
    const classe = classeDoStatus(DESCONHECIDO);

    expect(classe).not.toContain("undefined");
    expect(classe.trim()).not.toBe("");
  });
});
