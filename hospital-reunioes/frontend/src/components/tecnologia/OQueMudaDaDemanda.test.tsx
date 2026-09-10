/**
 * @vitest-environment jsdom
 */

/**
 * A seção "O que muda" na tela (issue #676, PRD #673, ADR 0054).
 *
 * Pelo MODAL, e não pelo componente isolado: o critério de aceite é "o modal da
 * Demanda vinculada mostra a seção", e um teste que montasse só o componente
 * provaria que ele sabe desenhar, não que o modal o usa. É a mesma escolha do
 * `VinculoDaDemanda.test.tsx`, e pelo mesmo motivo.
 *
 * O que se cobra aqui é o que o diretor VÊ. O que ele não pode ver (número,
 * link, título de fatia) é provado pelo marcador positivo: o texto da parte
 * está na tela e não há link nenhum na seção, em vez de procurar a ausência da
 * string "674", que seria cega a qualquer outra forma de escrever o número.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DemandaModal } from "./DemandaModal";
import { SEM_O_QUE_MUDA, TITULO_O_QUE_MUDA } from "./OQueMudaDaDemanda";
import { Demanda, ETAPA_ROTULO, EU_DESCONHECIDO, EuNaAba, ParteDaEntrega } from "./demandas";

const PRODUTOS = [{ id: "prod-1", nome: "Ana", ativo: true }];
const PESSOAS = [{ id: "P1", nome_completo: "Pedro Vitta" }];

const DIRETOR: EuNaAba = {
  id: "P2",
  nome_completo: "Diretor do Hospital",
  tem_github_login: false,
  integracao_configurada: true,
};

const PARTES: ParteDaEntrega[] = [
  // Como o backend as manda ao diretor: sem número.
  { numero: null, o_que_muda: "O selo aparece no card.", situacao: "entregue" },
  { numero: null, o_que_muda: "A seção mostra as partes.", situacao: "em_desenvolvimento" },
];

function demanda(extra: Partial<Demanda> = {}): Demanda {
  return {
    id: "d-1",
    titulo: "Levar o selo ao card",
    descricao: "O card precisa dizer o que muda.",
    tipo: "novo",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova",
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P1",
    prioridade: "normal",
    prazo: null,
    criado_em: new Date().toISOString(),
    concluida_em: null,
    cancelada_em: null,
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

function dublarFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function montarModal(d: Demanda, eu: EuNaAba = DIRETOR) {
  dublarFetch();
  return render(
    <DemandaModal
      demanda={d}
      produtos={PRODUTOS}
      pessoas={PESSOAS}
      token="token-de-teste"
      eu={eu}
      onFechar={() => {}}
      onMudou={() => {}}
    />,
  );
}

function secao(): HTMLElement {
  return screen.getByRole("region", { name: TITULO_O_QUE_MUDA });
}

describe("A seção O que muda", () => {
  it("mostra o texto da raiz para o diretor", () => {
    montarModal(VINCULADA);

    expect(within(secao()).getByText("O card passa a mostrar o que muda.")).toBeTruthy();
  });

  it("mostra cada parte com o texto e o selo de situação", () => {
    montarModal(VINCULADA);

    const bloco = secao();
    expect(within(bloco).getByText("O selo aparece no card.")).toBeTruthy();
    expect(within(bloco).getByText("A seção mostra as partes.")).toBeTruthy();
    expect(within(bloco).getByText(ETAPA_ROTULO.entregue)).toBeTruthy();
    expect(within(bloco).getByText(ETAPA_ROTULO.em_desenvolvimento)).toBeTruthy();
  });

  it("não mostra título de parte, número nem link", () => {
    montarModal(VINCULADA);

    const bloco = secao();
    // O par de presença está nos dois testes acima: os textos das partes ESTÃO
    // na tela. O que se cobra aqui é que nada técnico veio junto.
    expect(within(bloco).queryAllByRole("link")).toHaveLength(0);
    expect(bloco.textContent).not.toMatch(/[0-9]/);
    expect(bloco.textContent).not.toContain("#");
  });

  it("diz que a descrição está em preparação quando falta o bloco da raiz", () => {
    montarModal(demanda({ etapa: "planejada", o_que_muda: null, partes: [] }));

    expect(within(secao()).getByText(SEM_O_QUE_MUDA)).toBeTruthy();
  });

  it("some inteira quando a Demanda não tem Vínculo", () => {
    montarModal(demanda());

    expect(screen.queryByRole("region", { name: TITULO_O_QUE_MUDA })).toBeNull();
  });

  it("aparece igual para quem é da Vitta", () => {
    /** O texto é do diretor, mas não é SÓ dele: quem é da Vitta lê o mesmo. */
    montarModal(VINCULADA, { ...EU_DESCONHECIDO, tem_github_login: true, integracao_configurada: true });

    expect(within(secao()).getByText("O card passa a mostrar o que muda.")).toBeTruthy();
  });

  it("desenha o negrito e a lista do Markdown simples, sem asterisco cru", () => {
    montarModal(
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
    montarModal(
      demanda({
        etapa: "planejada",
        o_que_muda: "O card ganha a seção.",
        partes: [{ numero: null, o_que_muda: null, situacao: "planejada" }],
      }),
    );

    const item = within(secao()).getAllByRole("listitem")[0];
    expect(item.textContent).toContain(ETAPA_ROTULO.planejada);
    expect(item.textContent).toContain(SEM_O_QUE_MUDA);
  });
});
