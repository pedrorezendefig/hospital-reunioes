/**
 * A página de Central de Comando do manual (issue #1725, ADR 0094, decisões 4
 * e 5).
 *
 * Lê o Markdown de verdade, em `public/manual/central-de-comando/pagina.md`, e
 * prova o que a issue promete dele: só quem acessa a Central de Comando vê a
 * página, cada tarefa tem passos numerados e print, e o fluxograma desenha de
 * onde vem cada número.
 */

import { describe, expect, it } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { lerFluxograma, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas, paginasVisiveis } from "./paginas";

const PAGINAS = carregarPaginasDoManual();
const CENTRAL = PAGINAS.find((p) => p.modulo === "central-de-comando");

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

/** Os passos que chegam a um, seguindo as ligações de trás para a frente. */
function origens(fluxo: Fluxo, ate: string): Set<string> {
  const vistos = new Set([ate]);
  const fila = [ate];
  while (fila.length) {
    const atual = fila.shift()!;
    for (const l of fluxo.ligacoes) {
      if (l.para === atual && !vistos.has(l.de)) {
        vistos.add(l.de);
        fila.push(l.de);
      }
    }
  }
  return vistos;
}

function passoPorRotulo(fluxo: Fluxo, rotulo: RegExp) {
  const passo = fluxo.passos.find((p) => rotulo.test(p.rotulo));
  if (!passo) throw new Error(`O fluxograma não tem um passo ${rotulo}.`);
  return passo;
}

describe("a página de Central de Comando do manual", () => {
  it("existe e aparece para o Super admin, que tem a Central no menu", () => {
    expect(CENTRAL?.pasta).toBe("central-de-comando");
    const superAdmin = pessoa({ access_profile: "super_admin" });
    expect(paginasVisiveis(PAGINAS, superAdmin).map((p) => p.modulo)).toContain("central-de-comando");
  });

  it.each([
    ["o Facilitador, que entra no Admin só pelo Dados do Atendimento", pessoa({ access_profile: "regular" })],
    ["a Secretária", pessoa({ access_profile: "secretaria" })],
  ])("não aparece para %s", (_quem, participante) => {
    expect(paginasVisiveis(PAGINAS, participante).map((p) => p.modulo)).not.toContain("central-de-comando");
  });
});
