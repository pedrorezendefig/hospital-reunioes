/**
 * As páginas do manual (issue #1718, ADR 0094, decisões 2 e 4).
 *
 * Cada página é um Markdown em `public/manual/<pasta>/pagina.md` que declara o
 * módulo dela, com os prints ao lado. Este arquivo prova as duas promessas que
 * valem para TODA página, inclusive as que as próximas fatias vão escrever:
 * o módulo declarado existe no menu, e toda imagem citada existe no
 * repositório. Os dois testes leem os arquivos de verdade, e os detectores
 * deles têm caso próprio, para não ficarem verdes sobre nada.
 */

import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { lerFluxograma } from "@/components/manual/fluxograma/fluxo";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import {
  enderecoDaImagem,
  fluxogramasCitados,
  imagensCitadas,
  lerPagina,
  moduloEstaNoMenu,
} from "./paginas";

const PUBLICO = join(process.cwd(), "public");

/** Quem tem todos os acessos: o menu inteiro, do app e do Admin. */
const COM_TODOS_OS_ACESSOS: CurrentParticipante = {
  id: "p1",
  nome_completo: "Fulana de Tal",
  email: "fulana@hsm",
  access_profile: "super_admin",
  perfil_pop: "superadmin",
  perfil_ouvidoria: "ouvidor",
  perfil_contas_medicas: "coordenadora",
};

const PAGINAS = carregarPaginasDoManual();

describe("as páginas do manual no repositório", () => {
  it("existe ao menos uma página, a de exemplo que prova a casca", () => {
    expect(PAGINAS.length).toBeGreaterThan(0);
  });

  it("toda página declara um módulo que existe no menu", () => {
    const fora = PAGINAS.filter(
      (pagina) => !moduloEstaNoMenu(pagina.modulo, COM_TODOS_OS_ACESSOS)
    ).map((pagina) => `${pagina.pasta}: ${pagina.modulo}`);
    expect(fora).toEqual([]);
  });

  it("toda imagem citada existe no repositório", () => {
    const citadas = PAGINAS.flatMap((pagina) =>
      imagensCitadas(pagina.corpo).map((src) => enderecoDaImagem(pagina.pasta, src))
    );
    expect(citadas.length).toBeGreaterThan(0);
    expect(citadas.filter((endereco) => !existsSync(join(PUBLICO, endereco)))).toEqual([]);
  });
});

describe("os fluxogramas das páginas", () => {
  it("todo bloco fluxograma de toda página se lê sem erro", () => {
    const comErro = PAGINAS.flatMap((pagina) =>
      fluxogramasCitados(pagina.corpo).flatMap((bloco) => {
        const leitura = lerFluxograma(bloco);
        return leitura.ok ? [] : [`${pagina.pasta}: ${leitura.erros.join(" ")}`];
      })
    );
    expect(comErro).toEqual([]);
  });

  it("o bloco fluxograma sai do Markdown inteiro, e outro bloco de código não entra", () => {
    const corpo = [
      "Texto.",
      "```fluxograma",
      "inicio a 1,1: Começo",
      "fim b 2,1: Fim",
      "a -> b",
      "```",
      "```bash",
      "echo oi",
      "```",
    ].join("\n");
    expect(fluxogramasCitados(corpo)).toEqual(["inicio a 1,1: Começo\nfim b 2,1: Fim\na -> b\n"]);
  });
});

describe("os detectores das páginas", () => {
  it("módulo que não existe no menu não passa", () => {
    expect(moduloEstaNoMenu("financeiro", COM_TODOS_OS_ACESSOS)).toBe(false);
  });

  it("a imagem citada sai com o endereço da pasta da página", () => {
    const corpo = "Texto.\n\n![A tela](tela-inicial.png)\n\nE ![outra](/icons/x.png).";
    expect(imagensCitadas(corpo)).toEqual(["tela-inicial.png", "/icons/x.png"]);
    expect(enderecoDaImagem("reunioes-e-pendencias", "tela-inicial.png")).toBe(
      "/manual/reunioes-e-pendencias/tela-inicial.png"
    );
    expect(enderecoDaImagem("reunioes-e-pendencias", "/icons/x.png")).toBe("/icons/x.png");
  });

  it("página sem o módulo declarado é recusada ao ler", () => {
    expect(() => lerPagina("solta", "# Sem cabeçalho\n\nTexto.")).toThrow(/módulo/);
  });

  it("o cabeçalho da página dá o módulo, o título e o corpo", () => {
    const pagina = lerPagina(
      "pops",
      "---\nmodulo: pops\ntitulo: POPs\n---\n\n## Abrir um POP\n\nTexto."
    );
    expect(pagina).toEqual({
      pasta: "pops",
      modulo: "pops",
      titulo: "POPs",
      corpo: "## Abrir um POP\n\nTexto.",
    });
  });
});
