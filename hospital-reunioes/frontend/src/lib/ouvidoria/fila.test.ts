import { describe, expect, it } from "vitest";
import {
  aguardandoSeuEncerramento,
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

describe("bloco aguardando seu encerramento (issue #486, RN-67)", () => {
  function caso(numero: number, status: StatusManifestacao, tem_novidade: boolean) {
    return { id: `uuid-${numero}`, numero, status, tem_novidade };
  }

  it("junta só o caso respondido que ainda tem novidade", () => {
    const bloco = aguardandoSeuEncerramento([
      caso(1, "respondido", true),
      caso(2, "respondido", false),
      caso(3, "aguardando_area", true),
      caso(4, "encerrado", true),
    ]);

    expect(bloco.map((m) => m.numero)).toEqual([1]);
  });

  it("caso respondido sem novidade fica de fora: o ouvidor já olhou", () => {
    expect(aguardandoSeuEncerramento([caso(2, "respondido", false)])).toEqual([]);
  });

  it("novidade em caso que ainda não voltou da área não espera encerramento", () => {
    expect(aguardandoSeuEncerramento([caso(3, "aguardando_area", true)])).toEqual([]);
  });

  it("preserva a ordem em que a fila chegou, que é a do servidor", () => {
    const bloco = aguardandoSeuEncerramento([
      caso(9, "respondido", true),
      caso(4, "respondido", true),
      caso(7, "respondido", true),
    ]);

    expect(bloco.map((m) => m.numero)).toEqual([9, 4, 7]);
  });

  it("é destaque, e não filtro: o caso do bloco continua no grupo dele", () => {
    // O bloco copia, nunca move. Se ele consumisse a lista, o caso respondido
    // sumiria do grupo "Respondida" ao ser destacado, e voltaria de lugar
    // assim que o ouvidor abrisse o caso.
    const fila = [caso(1, "respondido", true), caso(2, "respondido", false)];

    const bloco = aguardandoSeuEncerramento(fila);
    const respondidos = agruparPorStatus(fila).find((g) => g.status === "respondido");

    expect(bloco).toHaveLength(1);
    expect(respondidos?.itens.map((m) => m.numero)).toEqual([1, 2]);
    expect(fila).toHaveLength(2);
  });
});
