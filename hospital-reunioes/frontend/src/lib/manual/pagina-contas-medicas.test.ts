/**
 * A página de Contas médicas do manual (issue #1724, ADR 0094, decisões 4 e 5).
 *
 * Lê o Markdown de verdade, em `public/manual/contas-medicas/pagina.md`, e
 * prova o que a issue promete dele: quem vê a página, o passo a passo de cada
 * tarefa com o print, e o fluxograma do caminho de uma conta, do envio à
 * análise concluída.
 */

import { describe, expect, it } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { lerFluxograma, ordemDoFluxo, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas, paginasVisiveis } from "./paginas";

const PAGINAS = carregarPaginasDoManual();
const CONTAS = PAGINAS.find((p) => p.modulo === "contas-medicas");

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

describe("a página de Contas médicas do manual", () => {
  it("aparece para a faturista, que tem Contas médicas no menu", () => {
    expect(CONTAS?.pasta).toBe("contas-medicas");
    const faturista = pessoa({ access_profile: null, perfil_contas_medicas: "faturista" });
    expect(paginasVisiveis(PAGINAS, faturista).map((p) => p.modulo)).toContain("contas-medicas");
  });

  it("não aparece para quem não acessa Contas médicas", () => {
    const semOModulo = pessoa({ access_profile: "regular", perfil_contas_medicas: null });
    expect(paginasVisiveis(PAGINAS, semOModulo).map((p) => p.modulo)).not.toContain("contas-medicas");
  });

  it.each([
    ["Enviar uma conta"],
    ["Pegar uma conta da Fila"],
    ["Analisar a conta no Guia"],
    ["Pedir o que faltou"],
  ])("a tarefa %s tem passos numerados e pelo menos um print", (tarefa) => {
    const secao = secoes(CONTAS!.corpo).find((s) => s.titulo === tarefa);
    expect(secao, `a página não tem a tarefa "${tarefa}"`).toBeDefined();
    const passos = secao!.texto.match(/^\d+\. /gm) ?? [];
    expect(passos.slice(0, 2)).toEqual(["1. ", "2. "]);
    expect(imagensCitadas(secao!.texto).length).toBeGreaterThan(0);
  });

  it("o fluxograma lê sem erro e vai do envio à análise concluída", () => {
    const leitura = lerFluxograma(blocoDoFluxograma(CONTAS!.corpo));
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const { fluxo } = leitura;

    const [primeiro] = ordemDoFluxo(fluxo);
    expect(primeiro.forma).toBe("inicio");
    expect(primeiro.rotulo).toMatch(/envi/i);

    const concluida = fluxo.passos.find((p) => p.forma === "fim" && /conclu/i.test(p.rotulo));
    expect(concluida, "falta o fim da análise concluída").toBeDefined();
    expect(alcancaveis(fluxo, primeiro.id).has(concluida!.id)).toBe(true);
  });

  it("o fluxograma passa pela Fila e pelo Guia da faturista", () => {
    const leitura = lerFluxograma(blocoDoFluxograma(CONTAS!.corpo));
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const rotulos = leitura.fluxo.passos.map((p) => p.rotulo).join("\n");
    expect(rotulos).toMatch(/Fila/);
    expect(rotulos).toMatch(/Guia/);
  });
});
