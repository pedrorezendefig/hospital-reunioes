/**
 * As contas puras da Conversa (issue #638, PRD #634, ADR 0050).
 *
 * A janela de 10 minutos e a @menção são regras que a tela precisa saber para
 * desenhar (o botão "Corrigir", o autocomplete e o destaque da menção). Quem
 * recusa de verdade continua sendo o backend; o que se prova aqui é que a tela
 * não oferece um caminho que ela já sabe recusado, nem esconde um que vale.
 */

import { describe, expect, it } from "vitest";

import {
  aplicarMencao,
  mencoesNoTexto,
  pedacosDoTexto,
  pessoasDoAutocomplete,
  podeCorrigirAgora,
  termoDaMencao,
} from "./demandas";

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

const AGORA = new Date("2026-09-09T12:00:00Z");

describe("A janela de correção, do lado da tela", () => {
  it("o botão vale enquanto o limite não passou", () => {
    expect(podeCorrigirAgora("2026-09-09T12:00:30Z", AGORA)).toBe(true);
  });

  it("no instante exato do limite ainda vale", () => {
    // O backend usa limite inclusivo ("por até 10 minutos"): uma tela mais
    // rígida esconderia o botão de um clique que a API aceitaria.
    expect(podeCorrigirAgora("2026-09-09T12:00:00Z", AGORA)).toBe(true);
  });

  it("um segundo depois do limite o botão some", () => {
    expect(podeCorrigirAgora("2026-09-09T11:59:59Z", AGORA)).toBe(false);
  });

  it("sem limite não há botão", () => {
    // É o que o backend manda na linha de movimento e na resposta de outra
    // pessoa: `editavel_ate` nulo.
    expect(podeCorrigirAgora(null, AGORA)).toBe(false);
  });

  it("limite ilegível não vira botão eterno", () => {
    expect(podeCorrigirAgora("depois do almoço", AGORA)).toBe(false);
  });
});

describe("O autocomplete do @", () => {
  it("o termo é o que veio depois do último @", () => {
    expect(termoDaMencao("Oi @Só")).toBe("Só");
  });

  it("sem @ não há menção em aberto", () => {
    expect(termoDaMencao("Oi, tudo bem")).toBeNull();
  });

  it("o @ digitado sozinho abre a lista inteira", () => {
    expect(termoDaMencao("Oi @")).toBe("");
    expect(pessoasDoAutocomplete("", PESSOAS)).toHaveLength(2);
  });

  it("o @ de um parágrafo anterior não segue aberto", () => {
    expect(termoDaMencao("Falei com @Pedro Vitta\nE também isso")).toBeNull();
  });

  it("lista quem começa pelo termo, sem distinguir maiúsculas", () => {
    expect(pessoasDoAutocomplete("só", PESSOAS).map((p) => p.id)).toEqual(["P2"]);
    expect(pessoasDoAutocomplete("SÓ", PESSOAS).map((p) => p.id)).toEqual(["P2"]);
  });

  it("some quando a frase seguiu e ninguém mais casa", () => {
    // O par de presença está acima: com "só" a lista tem gente. Aqui a pessoa
    // continuou escrevendo, e o autocomplete sai da frente.
    expect(pessoasDoAutocomplete("Sócia Vitta consegue olhar?", PESSOAS)).toEqual([]);
  });

  it("escolher troca o termo em aberto pelo nome inteiro", () => {
    expect(aplicarMencao("Oi @Só", "Sócia Vitta")).toBe("Oi @Sócia Vitta ");
  });

  it("escolher sem @ nenhum ainda escreve a menção no fim", () => {
    expect(aplicarMencao("Oi", "Sócia Vitta")).toBe("Oi@Sócia Vitta ");
  });
});

describe("Da escolha à lista de menções", () => {
  it("manda só quem o texto ainda chama", () => {
    const texto = "@Sócia Vitta consegue olhar?";
    expect(mencoesNoTexto(texto, PESSOAS)).toEqual(["P2"]);
  });

  it("apagar o @Fulano do texto tira a menção", () => {
    // Senão a linha continuaria dizendo que chamou alguém que o texto não
    // chama mais, e o e-mail da fatia seguinte avisaria essa pessoa à toa.
    expect(mencoesNoTexto("Deixa comigo", PESSOAS)).toEqual([]);
  });

  it("as duas menções cabem na mesma resposta", () => {
    expect(mencoesNoTexto("@Pedro Vitta e @Sócia Vitta, olhem", PESSOAS)).toEqual(["P1", "P2"]);
  });

  it("nome que é começo de outro não entra de carona", () => {
    // A pessoa digita "@Ana", clica em "Ana Souza" por engano, apaga, digita de
    // novo e escolhe "Ana Souza Lima": as duas ficam na lista de escolhidas, e o
    // texto chama uma só. Com um `includes` por nome, a curta entrava junto, e o
    // erro era MUDO, porque o destaque marca só a longa. Na fatia do e-mail
    // viraria aviso para quem o texto não chamou.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];

    expect(mencoesNoTexto("@Ana Souza Lima decide", homonimas)).toEqual(["PB"]);
  });

  it("as duas homônimas entram quando o texto chama as duas", () => {
    // Par de presença do teste acima: uma regra que sempre ficasse com o nome
    // mais longo perderia a menção legítima à curta.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];

    expect(mencoesNoTexto("@Ana Souza e @Ana Souza Lima decidem", homonimas)).toEqual(["PA", "PB"]);
  });

  it("a lista gravada e o destaque contam a mesma história", () => {
    // Hoje as duas contas saem do mesmo `pedacosDoTexto`, então este caso é
    // verdadeiro por construção: ele não é prova independente, é a TRAVA contra
    // desacoplar os dois de novo. Foi assim que a menção fantasma nasceu, com o
    // destaque resolvendo o prefixo e a lista gravada não.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];
    const texto = "@Ana Souza Lima decide";

    const destacados = pedacosDoTexto(
      texto,
      homonimas.map((p) => p.nome_completo),
    )
      .filter((pedaco) => pedaco.mencao)
      .map((pedaco) => pedaco.texto.slice(1));
    const gravados = mencoesNoTexto(texto, homonimas).map(
      (id) => homonimas.find((p) => p.id === id)!.nome_completo,
    );

    expect(gravados).toEqual(destacados);
  });
});

describe("O destaque da menção no fio", () => {
  it("marca o @Nome e deixa o resto como texto comum", () => {
    const pedacos = pedacosDoTexto("Oi @Sócia Vitta, olha isso", ["Sócia Vitta"]);

    expect(pedacos).toEqual([
      { texto: "Oi ", mencao: false },
      { texto: "@Sócia Vitta", mencao: true },
      { texto: ", olha isso", mencao: false },
    ]);
  });

  it("sem menção nenhuma o texto sai inteiro e sem marca", () => {
    // Par de presença do teste acima: uma marcação cravada pintaria tudo.
    expect(pedacosDoTexto("Vou olhar hoje", [])).toEqual([{ texto: "Vou olhar hoje", mencao: false }]);
  });

  it("nome que é começo de outro não é marcado pela metade", () => {
    const pedacos = pedacosDoTexto("@Ana Maria decide", ["Ana", "Ana Maria"]);

    expect(pedacos[0]).toEqual({ texto: "@Ana Maria", mencao: true });
  });

  it("o nome escrito sem @ continua texto comum", () => {
    expect(pedacosDoTexto("Falei com Sócia Vitta ontem", ["Sócia Vitta"])).toEqual([
      { texto: "Falei com Sócia Vitta ontem", mencao: false },
    ]);
  });
});
