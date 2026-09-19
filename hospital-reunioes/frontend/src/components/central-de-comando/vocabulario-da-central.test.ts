/**
 * O vocabulário da Central de Comando no código do front (issue #818).
 *
 * ADR 0058, decisão 7: a Área do site tem o nome novo em toda a interface e
 * no código, e não tem vínculo nenhum com a taxonomia de Setores (nome igual
 * ao de um Setor é coincidência). Em vez de confiar que ninguém vai escrever o
 * nome antigo ou importar os Setores numa tela da seção, o teste lê o código
 * da seção inteira, no molde da varredura das cores dos gráficos.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// O vitest roda com a raiz do frontend como cwd (é onde está o vitest.config).
const RAIZ_SRC = join(process.cwd(), "src");

const PASTAS_DA_CENTRAL = [
  join("components", "central-de-comando"),
  join("lib", "central-de-comando"),
  join("app", "admin", "central-de-comando"),
];

// O nome antigo da Área do site, com e sem cedilha, no singular e no plural.
const NOME_ANTIGO = /bra[cç]os?\b/i;

// Import de qualquer módulo de Setores ou da taxonomia.
const IMPORTA_SETORES = /from\s+["'][^"']*(setor|taxonomia)[^"']*["']/i;

function arquivos(pasta: string): string[] {
  return readdirSync(join(RAIZ_SRC, pasta)).flatMap((nome) => {
    const caminho = join(pasta, nome);
    if (statSync(join(RAIZ_SRC, caminho)).isDirectory()) return arquivos(caminho);
    return /\.tsx?$/.test(nome) ? [caminho] : [];
  });
}

const CODIGO_DA_CENTRAL = PASTAS_DA_CENTRAL.flatMap(arquivos);

function codigo(caminho: string): string {
  return readFileSync(join(RAIZ_SRC, caminho), "utf8");
}

describe("o vocabulário da Central de Comando", () => {
  it("a varredura acha o código da seção (sem isto, varrer nada passaria em tudo)", () => {
    expect(CODIGO_DA_CENTRAL).toEqual(
      expect.arrayContaining([
        join("components", "central-de-comando", "RankingAreasDoSite.tsx"),
        join("components", "central-de-comando", "DadosDoGoogle.tsx"),
        join("app", "admin", "central-de-comando", "dados-do-google", "page.tsx"),
      ]),
    );
  });

  it("o nome antigo da Área do site não aparece no código da seção", () => {
    expect(CODIGO_DA_CENTRAL.filter((caminho) => NOME_ANTIGO.test(codigo(caminho)))).toEqual([]);
  });

  it("nenhum arquivo da seção importa os Setores ou a taxonomia", () => {
    expect(CODIGO_DA_CENTRAL.filter((caminho) => IMPORTA_SETORES.test(codigo(caminho)))).toEqual([]);
  });
});
