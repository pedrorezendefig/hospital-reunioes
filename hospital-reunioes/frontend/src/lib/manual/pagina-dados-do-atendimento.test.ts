/**
 * A página de Dados do Atendimento do manual (issue #1726, ADR 0094, decisões
 * 4 e 5).
 *
 * Lê a página de verdade, em `public/manual/dados-do-atendimento/pagina.md`, e
 * o roteiro que refaz os prints dela, em `scripts/manual/dados-do-atendimento/`.
 * Quem vê a página, o que cada tarefa traz, o fluxograma e a origem dos prints
 * são promessas desta página; as que valem para toda página (módulo no menu,
 * imagem existente) moram em `paginas.test.ts`.
 */

import { describe, expect, it } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas, paginasVisiveis } from "./paginas";

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
const PAGINA = PAGINAS.find((pagina) => pagina.pasta === "dados-do-atendimento");

describe("a página de Dados do Atendimento", () => {
  it("existe e declara o módulo Dados do Atendimento", () => {
    expect(PAGINA?.modulo).toBe("dados-do-atendimento");
    expect(PAGINA?.titulo).toBe("Dados do Atendimento");
  });

  it("aparece para quem acessa Dados do Atendimento e some para quem não acessa", () => {
    const pastas = (p: CurrentParticipante) => paginasVisiveis(PAGINAS, p).map((x) => x.pasta);

    expect(pastas(pessoa({ access_profile: "secretaria" }))).toContain("dados-do-atendimento");
    expect(pastas(pessoa({ access_profile: "regular" }))).toContain("dados-do-atendimento");
    expect(pastas(pessoa({ access_profile: null, perfil_pop: "coordenador" }))).not.toContain(
      "dados-do-atendimento"
    );
  });
});

describe("as tarefas da página de Dados do Atendimento", () => {
  it("são o preço da consulta particular, o preparo do exame e a estimativa de cirurgia", () => {
    expect(tarefas(PAGINA!.corpo).map((t) => t.titulo)).toEqual([
      "Mudar o preço de uma consulta particular",
      "Mudar o preparo de um exame",
      "Mudar a estimativa de uma cirurgia",
    ]);
  });

  it("cada tarefa tem passos numerados e pelo menos um print", () => {
    expect(tarefasIncompletas(PAGINA!.corpo)).toEqual([]);
  });

  it("o detector pega a tarefa sem print e a tarefa sem passo numerado", () => {
    const corpo = [
      "## Sem print",
      "1. Clique em **Admin**.",
      "## Sem passo",
      "Abra a tabela.",
      "![A tabela](tabela.png)",
      "## Completa",
      "1. Clique em **Admin**.",
      "![A tabela](tabela.png)",
    ].join("\n\n");
    expect(tarefasIncompletas(corpo)).toEqual(["Sem print", "Sem passo"]);
  });
});
