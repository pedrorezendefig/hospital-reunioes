/**
 * A página de Ouvidoria do manual (issue #1723, ADR 0094, decisões 4 e 5).
 *
 * Lê o Markdown de verdade, em `public/manual/ouvidoria/pagina.md`, e prova o
 * que a issue promete dele: quem vê a página, o passo a passo de cada tarefa
 * com o print, e o fluxograma do caminho de uma manifestação com os prazos.
 */

import { describe, expect, it } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { lerFluxograma, ordemDoFluxo, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas, paginasVisiveis } from "./paginas";

const PAGINAS = carregarPaginasDoManual();
const OUVIDORIA = PAGINAS.find((p) => p.modulo === "ouvidoria");

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

/** O texto do bloco ```fluxograma da página. */
function blocoDoFluxograma(corpo: string): string {
  const achado = /```fluxograma\n([\s\S]*?)```/.exec(corpo);
  if (!achado) throw new Error("A página não tem o bloco fluxograma.");
  return achado[1];
}

/** Os passos que se alcançam a partir de um, seguindo as ligações. */
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

describe("a página de Ouvidoria do manual", () => {
  it("existe e aparece para quem tem a Ouvidoria no menu", () => {
    expect(OUVIDORIA?.pasta).toBe("ouvidoria");
    const facilitador = pessoa({ access_profile: "regular" });
    expect(paginasVisiveis(PAGINAS, facilitador).map((p) => p.modulo)).toContain("ouvidoria");
  });

  it("não aparece para quem só tem os POPs, que não vê a Ouvidoria no menu", () => {
    const soDosPops = pessoa({ access_profile: null, perfil_pop: "coordenador" });
    expect(paginasVisiveis(PAGINAS, soDosPops).map((p) => p.modulo)).not.toContain("ouvidoria");
  });

  it.each([
    ["Registrar uma manifestação"],
    ["Encaminhar ao setor"],
    ["Cobrar a resposta do setor"],
    ["Encerrar com o manifestante"],
  ])("a tarefa %s tem passos numerados e pelo menos um print", (tarefa) => {
    const secao = secoes(OUVIDORIA!.corpo).find((s) => s.titulo === tarefa);
    expect(secao, `a página não tem a tarefa "${tarefa}"`).toBeDefined();
    const passos = secao!.texto.match(/^\d+\. /gm) ?? [];
    expect(passos.slice(0, 2)).toEqual(["1. ", "2. "]);
    expect(imagensCitadas(secao!.texto).length).toBeGreaterThan(0);
  });

  it("o fluxograma lê sem erro e vai do registro ao encerramento", () => {
    const leitura = lerFluxograma(blocoDoFluxograma(OUVIDORIA!.corpo));
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const { fluxo } = leitura;

    const [primeiro] = ordemDoFluxo(fluxo);
    expect(primeiro.forma).toBe("inicio");
    expect(primeiro.rotulo).toMatch(/registr|chega/i);

    const fins = fluxo.passos.filter((p) => p.forma === "fim");
    const encerramento = fins.find((p) => /encerr/i.test(p.rotulo));
    expect(encerramento, "falta o fim do encerramento").toBeDefined();
    expect(alcancaveis(fluxo, primeiro.id).has(encerramento!.id)).toBe(true);
  });

  it("o fluxograma diz os prazos: o acuse em 24 horas, a resposta da área e a conclusiva em dias úteis", () => {
    const leitura = lerFluxograma(blocoDoFluxograma(OUVIDORIA!.corpo));
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const textos = leitura.fluxo.passos.map((p) => `${p.rotulo} ${p.detalhe}`).join("\n");

    expect(textos).toMatch(/24 horas/);
    expect(textos).toMatch(/2 dias úteis/);
    expect(textos).toMatch(/4 dias úteis/);
    expect(textos).toMatch(/7 dias úteis/);
  });
});
