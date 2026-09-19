/**
 * As cores dos gráficos da Central de Comando são os tokens do app (issue #817).
 *
 * No molde da varredura do teste de leitura direta do dashboard
 * (`app/dashboard/leitura-direta.test.tsx`): em vez de confiar que ninguém vai
 * escrever uma cor à mão num gráfico, o teste lê o código de cada gráfico da
 * Central (todo arquivo da seção que usa `recharts`, e o
 * `lib/central-de-comando/graficos.ts`, onde as cores moram) e trava duas
 * coisas: nenhuma cor escrita à mão (hexadecimal, `rgb()`, `hsl()`), e todo
 * token usado existe no `globals.css`. Um token com o nome errado não quebra
 * nada, só some: a linha do gráfico fica sem cor, e ninguém é avisado.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// O vitest roda com a raiz do frontend como cwd (é onde está o vitest.config).
const RAIZ_SRC = join(process.cwd(), "src");

const PASTAS_DA_CENTRAL = [join("components", "central-de-comando"), join("lib", "central-de-comando")];

const ONDE_AS_CORES_MORAM = join("lib", "central-de-comando", "graficos.ts");

// Cor dentro de string ("#2B2E7E"), para não pegar "#817" de um comentário.
const COR_ESCRITA_A_MAO = [/["'`]#[0-9a-fA-F]{3,8}["'`]/, /\b(?:rgba?|hsla?)\(/];

function codigo(caminho: string): string {
  return readFileSync(join(RAIZ_SRC, caminho), "utf8");
}

function arquivosDosGraficos(): string[] {
  return PASTAS_DA_CENTRAL.flatMap((pasta) =>
    readdirSync(join(RAIZ_SRC, pasta))
      .filter((nome) => /\.tsx?$/.test(nome) && !/\.test\.tsx?$/.test(nome))
      .map((nome) => join(pasta, nome))
      .filter((caminho) => caminho === ONDE_AS_CORES_MORAM || /from\s+["']recharts["']/.test(codigo(caminho))),
  );
}

describe("as cores dos gráficos da Central de Comando", () => {
  it("a varredura acha os gráficos (sem isto, varrer nada passaria em tudo)", () => {
    expect(arquivosDosGraficos()).toEqual(
      expect.arrayContaining([
        join("components", "central-de-comando", "GraficoVisitantesPorDia.tsx"),
        join("components", "central-de-comando", "GraficoDispositivos.tsx"),
        ONDE_AS_CORES_MORAM,
      ]),
    );
  });

  it("nenhum gráfico escreve cor à mão", () => {
    const culpados = arquivosDosGraficos().filter((caminho) =>
      COR_ESCRITA_A_MAO.some((padrao) => padrao.test(codigo(caminho))),
    );

    expect(culpados, "Use os tokens do app, var(--color-...), como em lib/central-de-comando/graficos.ts.").toEqual(
      [],
    );
  });

  it("todo token de cor usado nos gráficos existe no globals.css", () => {
    const globais = codigo(join("app", "globals.css"));
    const definidos = new Set([...globais.matchAll(/(--color-[a-z-]+)\s*:/g)].map((m) => m[1]));
    const usados = new Set(
      arquivosDosGraficos().flatMap((caminho) =>
        [...codigo(caminho).matchAll(/var\((--color-[a-z-]+)\)/g)].map((m) => m[1]),
      ),
    );

    expect(usados.size).toBeGreaterThan(0);
    expect([...usados].filter((token) => !definidos.has(token))).toEqual([]);
  });
});
