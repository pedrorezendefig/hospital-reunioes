/**
 * @vitest-environment jsdom
 */

/**
 * O Documento do card (issue #1552, PRD #1548, ADR 0084, decisão 7).
 *
 * Pelo componente: quem o usa é a conversa que já virou card, na lista do chat
 * (o uso por lá está em `ConversasDaTecnologia.test.tsx`).
 *
 * O que se cobra aqui é o que o diretor VÊ: Em uma frase, O que muda (até
 * cinco tópicos, o resto atrás do "Ver tudo"), Partes com a Etapa e a data, e
 * Datas. O que ele não pode ver (número, link, título de fatia) é provado pelo
 * marcador positivo: o texto da parte está na tela e não há link nenhum, em vez
 * de procurar a ausência da string "674", cega a qualquer outra forma de
 * escrever o número.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  ASSISTIR_A_DEMONSTRACAO,
  DocumentoDoCard,
  SEM_O_QUE_MUDA,
  TITULO_DATAS,
  TITULO_DEMONSTRACAO,
  TITULO_DOCUMENTO,
  TITULO_EM_UMA_FRASE,
  TITULO_O_QUE_MUDA,
  TITULO_PARTES,
  VER_TUDO,
} from "./DocumentoDoCard";
import { Demanda, ETAPA_ROTULO, ParteDaEntrega } from "./demandas";

const PARTES: ParteDaEntrega[] = [
  // Como o backend as manda ao diretor: sem número.
  { o_que_muda: "O selo aparece no card.", situacao: "entregue", fechada_em: "2026-11-05T14:00:00Z" },
  { o_que_muda: "A seção mostra as partes.", situacao: "em_desenvolvimento", fechada_em: null },
];

// O bloco "Para o diretor" no formato fixo da ADR 0084: a frase e os tópicos.
const BLOCO_COM_SETE = [
  "**O que muda:** cada pedido abre como um documento curto.",
  "",
  "**O que você precisa saber:**",
  "- Tópico um.",
  "- Tópico dois.",
  "- Tópico três.",
  "- Tópico quatro.",
  "- Tópico cinco.",
  "- Tópico seis.",
  "- Tópico sete.",
].join("\n");

function demanda(extra: Partial<Demanda> = {}): Demanda {
  return {
    id: "d-1",
    titulo: "Levar o selo ao card",
    criado_em: "2026-11-01T12:00:00Z",
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
  return render(<DocumentoDoCard demanda={d} />);
}

function documento(): HTMLElement {
  return screen.getByRole("region", { name: TITULO_DOCUMENTO });
}

/** O conteúdo que vem logo abaixo do título da seção, até o próximo título. */
function secao(titulo: string): HTMLElement {
  const cabecalho = within(documento()).getByRole("heading", { name: titulo });
  const bloco = cabecalho.nextElementSibling;
  if (!(bloco instanceof HTMLElement)) throw new Error(`a seção ${titulo} está vazia`);
  return bloco;
}

describe("O Documento do card", () => {
  it("mostra a frase e os cinco primeiros tópicos, e o Ver tudo abre os sete", () => {
    montar(demanda({ etapa: "planejada", o_que_muda: BLOCO_COM_SETE, partes: [] }));

    expect(secao(TITULO_EM_UMA_FRASE).textContent).toBe("cada pedido abre como um documento curto.");
    const topicos = () => within(secao(TITULO_O_QUE_MUDA)).getAllByRole("listitem").map((item) => item.textContent);
    expect(topicos()).toEqual(["Tópico um.", "Tópico dois.", "Tópico três.", "Tópico quatro.", "Tópico cinco."]);

    fireEvent.click(within(documento()).getByRole("button", { name: VER_TUDO }));

    expect(topicos()).toHaveLength(7);
    expect(topicos()[6]).toBe("Tópico sete.");
    expect(within(documento()).queryByRole("button", { name: VER_TUDO })).toBeNull();
  });

  it("com até cinco tópicos não há Ver tudo", () => {
    montar(demanda({ etapa: "planejada", o_que_muda: "**O que muda:** a frase.\n\n- Um.\n- Dois.", partes: [] }));

    expect(within(secao(TITULO_O_QUE_MUDA)).getAllByRole("listitem")).toHaveLength(2);
    expect(within(documento()).queryByRole("button", { name: VER_TUDO })).toBeNull();
  });

  it("o texto sem o formato fixo vira a frase, sem perder nada", () => {
    montar(VINCULADA);

    expect(secao(TITULO_EM_UMA_FRASE).textContent).toBe("O card passa a mostrar o que muda.");
  });

  it("diz que a descrição está em preparação quando falta o bloco da raiz", () => {
    montar(demanda({ etapa: "planejada", o_que_muda: null, partes: [] }));

    expect(secao(TITULO_EM_UMA_FRASE).textContent).toBe(SEM_O_QUE_MUDA);
    expect(within(documento()).queryByRole("heading", { name: TITULO_O_QUE_MUDA })).toBeNull();
  });

  it("mostra cada parte com o texto, a Etapa e a data de fechamento", () => {
    montar(VINCULADA);

    const itens = within(secao(TITULO_PARTES)).getAllByRole("listitem");
    expect(itens.map((item) => item.textContent)).toEqual([
      `${ETAPA_ROTULO.entregue}em 05/11/2026O selo aparece no card.`,
      `${ETAPA_ROTULO.em_desenvolvimento}A seção mostra as partes.`,
    ]);
  });

  it("mostra a parte sem texto com a Etapa dela e a frase de preparação", () => {
    /** A parte existe e o diretor precisa saber em que pé ela está, mesmo antes
     * de alguém escrever o que ela muda. */
    montar(demanda({ etapa: "planejada", o_que_muda: "O card ganha a seção.", partes: [{ o_que_muda: null, situacao: "planejada" }] }));

    const item = within(secao(TITULO_PARTES)).getAllByRole("listitem")[0];
    expect(item.textContent).toContain(ETAPA_ROTULO.planejada);
    expect(item.textContent).toContain(SEM_O_QUE_MUDA);
  });

  it("as Datas dizem dia e hora, em Brasília, de quando foi criado, entregue e posto em produção (issue #1580)", () => {
    montar(
      demanda({
        etapa: "em_producao",
        o_que_muda: "A frase.",
        fechada_em: "2026-11-06T18:00:00Z",
        em_producao_em: "2026-11-07T10:00:00-03:00",
      }),
    );

    expect(within(secao(TITULO_DATAS)).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Criado em 01/11/2026 às 09:00",
      "Entregue em 06/11/2026 às 15:00",
      "Em produção em 07/11/2026 às 10:00",
    ]);
  });

  it("perto da meia-noite de Greenwich, o dia e a hora são os de Brasília (issue #1580)", () => {
    montar(demanda({ etapa: "entregue", o_que_muda: "A frase.", fechada_em: "2026-11-07T01:30:00Z" }));

    expect(within(secao(TITULO_DATAS)).getByText("Entregue em 06/11/2026 às 22:30")).toBeTruthy();
  });

  it("antes da entrega as Datas só têm a criação", () => {
    montar(VINCULADA);

    expect(within(secao(TITULO_DATAS)).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Criado em 01/11/2026 às 09:00",
    ]);
  });

  it("data ilegível de entrega ou de produção some das Datas, sem quebrar o Documento (issue #1580)", () => {
    montar(demanda({ etapa: "em_producao", o_que_muda: "A frase.", fechada_em: "ontem", em_producao_em: "ontem" }));

    expect(within(secao(TITULO_DATAS)).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Criado em 01/11/2026 às 09:00",
    ]);
  });

  it("o diretor não vê título de parte, número de issue nem link", () => {
    montar(VINCULADA);

    // O par de presença está nos testes acima: os textos das partes ESTÃO na
    // tela. O que se cobra aqui é que nada técnico veio junto.
    expect(within(documento()).queryAllByRole("link")).toHaveLength(0);
    expect(documento().textContent).not.toContain("#");
  });

  it("o Desenvolvedor vê o número e o link da issue", () => {
    montar({ ...VINCULADA, issue_numero: 912, issue_url: "https://github.com/pedrorezendefig/hospital-reunioes/issues/912" });

    const link = within(documento()).getByRole("link", { name: "#912" });
    expect(link.getAttribute("href")).toBe("https://github.com/pedrorezendefig/hospital-reunioes/issues/912");
  });

  it("o diretor vê o Número da Demanda no topo, sem cerquilha (issue #1585)", () => {
    montar({ ...VINCULADA, numero: 42 });

    const topo = documento().firstElementChild;
    expect(topo?.textContent).toBe("Demanda 42");
    expect(documento().textContent).not.toContain("#");
  });

  it("o Desenvolvedor vê o Número da Demanda e o #<issue> lado a lado, e só a issue leva cerquilha (issue #1585)", () => {
    montar({
      ...VINCULADA,
      numero: 42,
      issue_numero: 912,
      issue_url: "https://github.com/pedrorezendefig/hospital-reunioes/issues/912",
    });

    const topo = documento().firstElementChild as HTMLElement;
    expect(within(topo).getByText("Demanda 42")).toBeTruthy();
    expect(within(topo).getByRole("link", { name: "#912" })).toBeTruthy();
    expect(documento().textContent).not.toContain("#42");
  });

  it("com o link, a Demonstração vem num cartão próprio com o link para assistir (issue #1559)", () => {
    montar({ ...VINCULADA, demonstracao_url: "https://youtu.be/demo", demonstracao_em: "2026-11-08T13:00:00Z" });

    const cartao = within(documento()).getByRole("region", { name: TITULO_DEMONSTRACAO });
    const link = within(cartao).getByRole("link", { name: ASSISTIR_A_DEMONSTRACAO });
    expect(link.getAttribute("href")).toBe("https://youtu.be/demo");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(cartao.textContent).toContain("Adicionada em 08/11/2026");
  });

  it("sem o link, ou com um link que não é https, não há Demonstração", () => {
    montar(VINCULADA);
    expect(within(documento()).queryByRole("region", { name: TITULO_DEMONSTRACAO })).toBeNull();
    cleanup();

    montar({ ...VINCULADA, demonstracao_url: "javascript:alert(1)" });
    expect(within(documento()).queryByRole("region", { name: TITULO_DEMONSTRACAO })).toBeNull();
  });

  it("some inteiro quando a Demanda não tem Vínculo", () => {
    montar(demanda());

    expect(screen.queryByRole("region", { name: TITULO_DOCUMENTO })).toBeNull();
  });
});
