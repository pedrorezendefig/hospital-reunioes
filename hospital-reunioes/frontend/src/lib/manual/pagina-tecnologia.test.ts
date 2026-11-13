/**
 * A página de Tecnologia do manual (issue #1727, ADR 0094, decisões 4 e 5).
 *
 * Lê o Markdown de verdade, em `public/manual/tecnologia/pagina.md`, e prova o
 * que a issue promete dele: só quem acessa Tecnologia vê a página, cada tarefa
 * tem passos numerados e print, e o fluxograma desenha o caminho de um pedido,
 * da conversa com o Assistente até Entregue.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MarkdownDoManual } from "@/components/manual/MarkdownDoManual";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { lerFluxograma, type Fluxo, type Passo } from "@/components/manual/fluxograma/fluxo";
import { carregarPaginasDoManual } from "./carregar";
import { fluxogramasCitados, imagensCitadas, paginasVisiveis } from "./paginas";

const PAGINAS = carregarPaginasDoManual();
const TECNOLOGIA = PAGINAS.find((p) => p.modulo === "tecnologia");
const TAREFAS = [
  "Pedir um bug ou uma melhoria ao Assistente",
  "Acompanhar o pedido no Quadro",
  "Filtrar por Projeto",
  "Ver as Entregas",
];

function pessoa(campos: Partial<CurrentParticipante>): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
    perfil_pop: null,
    perfil_ouvidoria: null,
    perfil_contas_medicas: null,
    ...campos,
  };
}

/** As seções `## ` do corpo, com o título e o texto de cada uma. */
function secoes(corpo: string): { titulo: string; texto: string }[] {
  return corpo
    .split(/^## /m)
    .slice(1)
    .map((bloco) => {
      const [titulo, ...resto] = bloco.split("\n");
      return { titulo: titulo.trim(), texto: resto.join("\n") };
    });
}

function secao(titulo: string) {
  const achada = secoes(TECNOLOGIA!.corpo).find((s) => s.titulo === titulo);
  expect(achada, `a página não tem a tarefa "${titulo}"`).toBeDefined();
  return achada!;
}

/** Os passos que se alcançam saindo de um, pelas ligações, sem passar pelos de `evitar`. */
function alcancaveis(fluxo: Fluxo, de: string, evitar: Set<string> = new Set()): Set<string> {
  const vistos = new Set([de]);
  const fila = [de];
  while (fila.length) {
    const atual = fila.shift()!;
    for (const l of fluxo.ligacoes) {
      if (l.de === atual && !vistos.has(l.para) && !evitar.has(l.para)) {
        vistos.add(l.para);
        fila.push(l.para);
      }
    }
  }
  return vistos;
}

function passoPorRotulo(fluxo: Fluxo, rotulo: RegExp): Passo {
  const passo = fluxo.passos.find((p) => rotulo.test(p.rotulo));
  if (!passo) throw new Error(`O fluxograma não tem um passo ${rotulo}.`);
  return passo;
}

describe("a página de Tecnologia do manual", () => {
  it("existe e aparece para o Super admin, que tem Tecnologia no menu", () => {
    expect(TECNOLOGIA?.pasta).toBe("tecnologia");
    const superAdmin = pessoa({ access_profile: "super_admin" });
    expect(paginasVisiveis(PAGINAS, superAdmin).map((p) => p.modulo)).toContain("tecnologia");
  });

  it.each([
    ["o Facilitador, que entra no Admin só pelo Dados do Atendimento", pessoa({ access_profile: "regular" })],
    ["a Secretária", pessoa({ access_profile: "secretaria" })],
  ])("não aparece para %s", (_quem, participante) => {
    expect(paginasVisiveis(PAGINAS, participante).map((p) => p.modulo)).not.toContain("tecnologia");
  });

  it.each(TAREFAS)("a tarefa %s tem passos numerados e pelo menos um print", (tarefa) => {
    const { texto } = secao(tarefa);
    const passos = texto.match(/^\d+\. /gm) ?? [];
    expect(passos.slice(0, 2)).toEqual(["1. ", "2. "]);
    expect(imagensCitadas(texto).length).toBeGreaterThan(0);
  });

  it.each(TAREFAS)("a tarefa %s sai na tela como uma lista só, numerada em sequência", (tarefa) => {
    const { texto } = secao(tarefa);
    const numeros = (texto.match(/^\d+(?=\. )/gm) ?? []).map(Number);
    expect(numeros).toEqual(numeros.map((_, i) => i + 1));
    // O `ol` do manual não repassa o `start`: um print fora do item fecha a
    // lista e a próxima recomeça em 1 na tela. Uma lista só, com todos os passos.
    const html = renderToStaticMarkup(MarkdownDoManual({ pasta: "tecnologia", children: texto }));
    expect(html.match(/<ol[ >]/g) ?? []).toHaveLength(1);
    expect(html.match(/<li[ >]/g) ?? []).toHaveLength(numeros.length);
  });
});

describe("o fluxograma do caminho de um pedido", () => {
  function fluxo(): Fluxo {
    const blocos = fluxogramasCitados(TECNOLOGIA!.corpo);
    expect(blocos).toHaveLength(1);
    const leitura = lerFluxograma(blocos[0]);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    return leitura.fluxo;
  }

  it("lê sem erro de bloco e começa num só lugar, a conversa com o Assistente", () => {
    const inicios = fluxo().passos.filter((p) => p.forma === "inicio");
    expect(inicios).toHaveLength(1);
    expect(inicios[0].rotulo).toMatch(/Assistente/);
  });

  it("termina em Entregue, que se alcança a partir da conversa", () => {
    const f = fluxo();
    const entregue = passoPorRotulo(f, /^Entregue$/);
    expect(entregue.forma).toBe("fim");
    const inicio = f.passos.find((p) => p.forma === "inicio")!;
    expect(alcancaveis(f, inicio.id).has(entregue.id)).toBe(true);
  });

  it("nada chega a Entregue sem o clique em Criar o card", () => {
    const f = fluxo();
    const inicio = f.passos.find((p) => p.forma === "inicio")!;
    const criar = passoPorRotulo(f, /^Criar o card$/);
    const entregue = passoPorRotulo(f, /^Entregue$/);
    expect(alcancaveis(f, inicio.id, new Set([criar.id])).has(entregue.id)).toBe(false);
  });

  it("o bug e a melhoria são os dois lados da primeira decisão, e os dois chegam ao Criar o card", () => {
    const f = fluxo();
    const decisao = passoPorRotulo(f, /[Bb]ug ou melhoria/);
    expect(decisao.forma).toBe("decisao");
    const criar = passoPorRotulo(f, /^Criar o card$/);
    const saidas = f.ligacoes.filter((l) => l.de === decisao.id);
    expect(saidas.map((l) => l.rotulo).sort()).toEqual(["bug", "melhoria"]);
    for (const saida of saidas) {
      expect(alcancaveis(f, saida.para).has(criar.id), `o lado ${saida.rotulo} não chega ao Criar o card`).toBe(true);
    }
  });

  it("depois do card, o pedido passa pelas Etapas Em análise, Planejada e Em desenvolvimento, nessa ordem", () => {
    const f = fluxo();
    const criar = passoPorRotulo(f, /^Criar o card$/);
    const etapas = [/^Em análise$/, /^Planejada$/, /^Em desenvolvimento$/, /^Entregue$/].map((r) => passoPorRotulo(f, r));
    expect(alcancaveis(f, criar.id).has(etapas[0].id)).toBe(true);
    for (let i = 0; i < etapas.length - 1; i++) {
      expect(alcancaveis(f, etapas[i].id).has(etapas[i + 1].id), `${etapas[i].rotulo} não leva a ${etapas[i + 1].rotulo}`).toBe(true);
      expect(alcancaveis(f, etapas[i + 1].id).has(etapas[i].id), `${etapas[i + 1].rotulo} volta para ${etapas[i].rotulo}`).toBe(false);
    }
  });
});
