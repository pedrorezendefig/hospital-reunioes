/**
 * @vitest-environment jsdom
 */

/**
 * A seção "O que muda" na tela (issue #676, PRD #673, ADR 0054).
 *
 * Pelo componente: desde a issue #1386 quem a usa é a conversa que já virou
 * card, na lista do chat (o uso por lá está em `ConversasDaTecnologia.test.tsx`).
 *
 * O que se cobra aqui é o que o diretor VÊ. O que ele não pode ver (número,
 * link, título de fatia) é provado pelo marcador positivo: o texto da parte
 * está na tela e não há link nenhum na seção, em vez de procurar a ausência da
 * string "674", que seria cega a qualquer outra forma de escrever o número.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OQueMudaDaDemanda, SEM_O_QUE_MUDA, TITULO_O_QUE_MUDA } from "./OQueMudaDaDemanda";
import { Demanda, ETAPA_ROTULO, ParteDaEntrega } from "./demandas";

const PARTES: ParteDaEntrega[] = [
  // Como o backend as manda ao diretor: sem número.
  { o_que_muda: "O selo aparece no card.", situacao: "entregue" },
  { o_que_muda: "A seção mostra as partes.", situacao: "em_desenvolvimento" },
];

function demanda(extra: Partial<Demanda> = {}): Demanda {
  return {
    id: "d-1",
    titulo: "Levar o selo ao card",
    criado_em: new Date().toISOString(),
    ...extra,
  };
}

const VINCULADA = demanda({
  etapa: "em_desenvolvimento",
  partes_entregues: 1,
  partes_total: 2,
  o_que_muda: "O card passa a mostrar o que muda.",
  partes: PARTES,
});

afterEach(() => {
  cleanup();
});

function montar(d: Demanda) {
  return render(<OQueMudaDaDemanda demanda={d} />);
}

function secao(): HTMLElement {
  return screen.getByRole("region", { name: TITULO_O_QUE_MUDA });
}

describe("A seção O que muda", () => {
  it("mostra o texto da raiz para o diretor", () => {
    montar(VINCULADA);

    expect(within(secao()).getByText("O card passa a mostrar o que muda.")).toBeTruthy();
  });

  it("mostra cada parte com o texto e o selo de situação", () => {
    montar(VINCULADA);

    const bloco = secao();
    expect(within(bloco).getByText("O selo aparece no card.")).toBeTruthy();
    expect(within(bloco).getByText("A seção mostra as partes.")).toBeTruthy();
    expect(within(bloco).getByText(ETAPA_ROTULO.entregue)).toBeTruthy();
    expect(within(bloco).getByText(ETAPA_ROTULO.em_desenvolvimento)).toBeTruthy();
  });

  it("não mostra título de parte, número nem link", () => {
    montar(VINCULADA);

    const bloco = secao();
    // O par de presença está nos dois testes acima: os textos das partes ESTÃO
    // na tela. O que se cobra aqui é que nada técnico veio junto.
    expect(within(bloco).queryAllByRole("link")).toHaveLength(0);
    expect(bloco.textContent).not.toMatch(/[0-9]/);
    expect(bloco.textContent).not.toContain("#");
  });

  it("diz que a descrição está em preparação quando falta o bloco da raiz", () => {
    montar(demanda({ etapa: "planejada", o_que_muda: null, partes: [] }));

    expect(within(secao()).getByText(SEM_O_QUE_MUDA)).toBeTruthy();
  });

  it("some inteira quando a Demanda não tem Vínculo", () => {
    montar(demanda());

    expect(screen.queryByRole("region", { name: TITULO_O_QUE_MUDA })).toBeNull();
  });

  it("desenha o negrito e a lista do Markdown simples, sem asterisco cru", () => {
    montar(
      demanda({
        etapa: "planejada",
        o_que_muda: "**O que muda:** o card ganha a seção.\n\n- Vem do planejamento.\n- Ninguém reescreve no app.",
        partes: [],
      }),
    );

    const bloco = secao();
    expect(within(bloco).getByText("O que muda:").tagName).toBe("STRONG");
    expect(within(bloco).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Vem do planejamento.",
      "Ninguém reescreve no app.",
    ]);
    expect(bloco.textContent).not.toContain("**");
  });

  it("mostra a parte sem texto com o selo dela e a frase de preparação", () => {
    /** A parte existe e o diretor precisa saber em que pé ela está, mesmo antes
     * de alguém escrever o que ela muda. */
    montar(
      demanda({
        etapa: "planejada",
        o_que_muda: "O card ganha a seção.",
        partes: [{ o_que_muda: null, situacao: "planejada" }],
      }),
    );

    const item = within(secao()).getAllByRole("listitem")[0];
    expect(item.textContent).toContain(ETAPA_ROTULO.planejada);
    expect(item.textContent).toContain(SEM_O_QUE_MUDA);
  });
});
