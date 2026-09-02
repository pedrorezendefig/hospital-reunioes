/**
 * A ação primária de cada estado na fila (issue #495, PRD #471, RN-74).
 *
 * A regra mora aqui, longe do JSX, porque ela é o que o ouvidor usa para
 * trabalhar sem procurar: uma ação por linha, sempre a mesma para o mesmo
 * estado. Um `if` solto no meio da linha faria o botão certo aparecer numa
 * tela e sumir na outra.
 */

import { describe, expect, it } from "vitest";

import {
  ROTULO_ACAO,
  acaoPrimariaDoStatus,
  acoesSecundariasDoStatus,
  type ChaveDeAcao,
} from "./acoes";

describe("a ação primária de cada estado (RN-74)", () => {
  it("caso em classificação é validado e acionado", () => {
    expect(acaoPrimariaDoStatus("em_classificacao")).toBe("validar");
  });

  it("caso com a área é cobrado", () => {
    expect(acaoPrimariaDoStatus("aguardando_area")).toBe("cobrar");
  });

  it("caso respondido é encerrado", () => {
    expect(acaoPrimariaDoStatus("respondido")).toBe("encerrar");
  });

  it("caso novo ainda não tem ato próprio na fila: abre", () => {
    expect(acaoPrimariaDoStatus("novo")).toBe("abrir");
  });

  it("caso em pausa abre, porque o próximo passo é falar com o manifestante", () => {
    expect(acaoPrimariaDoStatus("aguardando_manifestante")).toBe("abrir");
  });

  it("caso encerrado abre, e mais nada", () => {
    expect(acaoPrimariaDoStatus("encerrado")).toBe("abrir");
    expect(acoesSecundariasDoStatus("encerrado")).toEqual([]);
  });

  it("estado que a tela não conhece cai em abrir, e não em botão nenhum", () => {
    // Backend novo com tela velha (issue #375): a linha continua acionável.
    expect(acaoPrimariaDoStatus("estado_do_futuro" as never)).toBe("abrir");
  });
});

describe("o que sobra vai para o menu (issue #495)", () => {
  it("a primária nunca se repete no menu", () => {
    const estados = [
      "novo",
      "em_classificacao",
      "aguardando_area",
      "aguardando_manifestante",
      "respondido",
      "encerrado",
    ] as const;
    for (const status of estados) {
      expect(acoesSecundariasDoStatus(status)).not.toContain(acaoPrimariaDoStatus(status));
    }
  });

  it("cobrar o setor não tira o encerramento do alcance do ouvidor", () => {
    expect(acoesSecundariasDoStatus("aguardando_area")).toEqual(["encerrar", "abrir"]);
  });

  it("no caso em classificação o encerramento sem apuração continua possível", () => {
    expect(acoesSecundariasDoStatus("em_classificacao")).toEqual(["encerrar", "abrir"]);
  });

  it("o caso respondido guarda só o caminho do Dossiê", () => {
    expect(acoesSecundariasDoStatus("respondido")).toEqual(["abrir"]);
  });

  it("a pausa mantém o encerramento por abandono à mão", () => {
    expect(acoesSecundariasDoStatus("aguardando_manifestante")).toEqual(["encerrar"]);
  });

  it("cobrar só existe para o caso que está com a área", () => {
    // Cobrar é reenviar o acionamento: antes de acionar não há o que reenviar,
    // e depois da resposta a cobrança seria um email pedindo o que já chegou.
    const estados = [
      "novo",
      "em_classificacao",
      "aguardando_manifestante",
      "respondido",
      "encerrado",
    ] as const;
    for (const status of estados) {
      expect(acoesSecundariasDoStatus(status)).not.toContain("cobrar");
      expect(acaoPrimariaDoStatus(status)).not.toBe("cobrar");
    }
  });
});

describe("os rótulos da fila", () => {
  it("toda ação tem nome escrito, para o botão nunca sair em branco", () => {
    const chaves: ChaveDeAcao[] = ["validar", "cobrar", "encerrar", "abrir"];
    for (const chave of chaves) {
      expect(ROTULO_ACAO[chave].length).toBeGreaterThan(0);
    }
  });
});
