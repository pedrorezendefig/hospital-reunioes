/**
 * A página de POPs do manual (issue #1722, ADR 0094, decisões 4 e 5).
 *
 * Lê a página de verdade, em `public/manual/pops/pagina.md`, e o roteiro que
 * refaz os prints dela, em `scripts/manual/pops/`. Quem vê a página, o que
 * cada tarefa traz e a origem dos prints são promessas desta página; as que
 * valem para toda página (módulo no menu, imagem existente) moram em
 * `paginas.test.ts`.
 */

import { describe, expect, it } from "vitest";

import { lerFluxograma, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import { fluxogramasCitados, imagensCitadas, paginasVisiveis } from "./paginas";

function pessoa(campos: Partial<CurrentParticipante>): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
    ...campos,
  };
}

/** Cada `## ` do corpo é uma tarefa: o título e o texto até o próximo `## `. */
function tarefas(corpo: string): { titulo: string; texto: string }[] {
  return corpo
    .split(/^## /m)
    .slice(1)
    .map((bloco) => {
      const [titulo, ...resto] = bloco.split("\n");
      return { titulo: titulo.trim(), texto: resto.join("\n") };
    });
}

/** As tarefas que faltam passo numerado ou print. */
function tarefasIncompletas(corpo: string): string[] {
  return tarefas(corpo)
    .filter(({ texto }) => !/^1\. /m.test(texto) || imagensCitadas(texto).length === 0)
    .map(({ titulo }) => titulo);
}

const PAGINAS = carregarPaginasDoManual();
const POPS = PAGINAS.find((pagina) => pagina.pasta === "pops");

describe("a página de POPs", () => {
  it("existe e declara o módulo POPs", () => {
    expect(POPS?.modulo).toBe("pops");
    expect(POPS?.titulo).toBe("POPs");
  });

  it("aparece para quem acessa POPs e some para quem não acessa", () => {
    const dePops = paginasVisiveis(PAGINAS, pessoa({ access_profile: null, perfil_pop: "coordenador" }));
    const facilitador = paginasVisiveis(PAGINAS, pessoa({ access_profile: "regular" }));

    expect(dePops.map((p) => p.pasta)).toContain("pops");
    expect(facilitador.map((p) => p.pasta)).not.toContain("pops");
  });
});

describe("as tarefas da página de POPs", () => {
  it("são achar, criar, escrever, revisar e publicar, nessa ordem", () => {
    expect(tarefas(POPS!.corpo).map((t) => t.titulo)).toEqual([
      "Achar um POP publicado",
      "Criar um POP",
      "Escrever o POP com o Consultor",
      "Revisar um POP",
      "Publicar a versão nova",
    ]);
  });

  it("cada tarefa tem passos numerados e pelo menos um print", () => {
    expect(tarefasIncompletas(POPS!.corpo)).toEqual([]);
  });

  it("o detector pega a tarefa sem print e a tarefa sem passo numerado", () => {
    const corpo = [
      "## Sem print",
      "1. Clique em **POPs**.",
      "## Sem passo",
      "Abra a lista.",
      "![A lista](lista.png)",
      "## Completa",
      "1. Clique em **POPs**.",
      "![A lista](lista.png)",
    ].join("\n\n");
    expect(tarefasIncompletas(corpo)).toEqual(["Sem print", "Sem passo"]);
  });
});

/** Os passos que se alcançam a partir de `de`, seguindo as ligações. */
function alcancaveis(fluxo: Fluxo, de: string): Set<string> {
  const vistos = new Set([de]);
  const fila = [de];
  while (fila.length) {
    const atual = fila.shift()!;
    for (const l of fluxo.ligacoes) {
      if (l.de === atual && !vistos.has(l.para)) {
        vistos.add(l.para);
        fila.push(l.para);
      }
    }
  }
  return vistos;
}

describe("o fluxograma da página de POPs", () => {
  const blocos = fluxogramasCitados(POPS?.corpo ?? "");

  it("desenha o caminho do rascunho à versão publicada, sem erro de bloco", () => {
    expect(blocos).toHaveLength(1);
    const leitura = lerFluxograma(blocos[0]);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));

    const inicio = leitura.fluxo.passos.filter((p) => p.forma === "inicio");
    const fim = leitura.fluxo.passos.filter((p) => p.forma === "fim");
    expect(inicio).toHaveLength(1);
    expect(fim).toHaveLength(1);
    expect(`${inicio[0].rotulo} ${inicio[0].detalhe}`).toMatch(/rascunho/i);
    expect(fim[0].rotulo).toMatch(/versão publicada/i);
    expect(alcancaveis(leitura.fluxo, inicio[0].id).has(fim[0].id)).toBe(true);
  });

  it("mostra a devolução de quem revisa e de quem valida, voltando para a elaboração", () => {
    const leitura = lerFluxograma(blocos[0]);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const decisoes = leitura.fluxo.passos.filter((p) => p.forma === "decisao").map((p) => p.id);
    const elaborar = leitura.fluxo.ligacoes.find((l) => l.de === "criar")!.para;

    expect(decisoes).toHaveLength(2);
    for (const decisao of decisoes) {
      const naoAprovada = leitura.fluxo.ligacoes.find((l) => l.de === decisao && l.rotulo === "não");
      expect(naoAprovada, decisao).toBeTruthy();
      expect(alcancaveis(leitura.fluxo, naoAprovada!.para).has(elaborar)).toBe(true);
    }
  });
});
