/**
 * As cores dos gráficos da Central de Comando são os tokens do app (issue #817).
 *
 * No molde da varredura do teste de leitura direta do dashboard
 * (`app/dashboard/leitura-direta.test.tsx`): em vez de confiar que ninguém vai
 * escrever uma cor à mão num gráfico, o teste lê o código de cada gráfico da
 * Central (todo arquivo da seção que usa `recharts`, e o
 * `lib/central-de-comando/graficos.ts`, onde as cores moram), sem os
 * comentários, e trava:
 *
 * - hexadecimal em qualquer lugar do código: numa string inteira ("#2B2E7E"),
 *   dentro de uma maior ("1px solid #E2E8F0"), numa classe arbitrária do
 *   Tailwind (`bg-[#2B2E7E]`) ou no valor de reserva de um token;
 * - função de cor: `rgb()`, `rgba()`, `hsl()`, `hsla()`, `hwb()`, `lab()`,
 *   `lch()`, `oklab()`, `oklch()`, `color()` e `color-mix()`;
 * - cor por nome ("white", "red") em `fill`, `stroke`, `color`,
 *   `backgroundColor`, `borderColor` e `stopColor`, como atributo do JSX ou
 *   chave de objeto (só `none`, `currentColor` e `transparent` passam);
 * - token que não existe: todo `var(--...)` usado, com ou sem valor de reserva
 *   e com dígito no nome, tem de estar definido no `globals.css`. Um token com o
 *   nome errado não quebra nada, só some: a linha do gráfico fica sem cor, e
 *   ninguém é avisado.
 *
 * Fica de fora, de propósito: as classes da paleta do Tailwind (`bg-white`,
 * `text-emerald-700`), que são o molde da casa (as mesmas da variação da Visão
 * Geral), e cor dentro de uma declaração CSS escrita em string (`"fill: red"`),
 * que os gráficos em `recharts` não usam.
 *
 * Os casos de controle provam que a varredura enxerga cada padrão: sem eles,
 * uma mudança nas expressões poderia deixá-la cega sem ninguém ver. Se um dia
 * um padrão pegar no código algo que não é cor, a saída é uma lista explícita
 * aqui, com o motivo por escrito, e não afrouxar a expressão.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// O vitest roda com a raiz do frontend como cwd (é onde está o vitest.config).
const RAIZ_SRC = join(process.cwd(), "src");

const PASTAS_DA_CENTRAL = [join("components", "central-de-comando"), join("lib", "central-de-comando")];

const ONDE_AS_CORES_MORAM = join("lib", "central-de-comando", "graficos.ts");

/**
 * O código sem os comentários: o "#817" de um comentário não é cor, e uma cor
 * comentada não vai para a tela. As barras duplas de um endereço
 * ("https://...") não abrem comentário.
 */
function semComentarios(codigo: string): string {
  return codigo.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:\\])\/\/.*$/gm, "$1");
}

// Hexadecimal em qualquer lugar: string inteira, pedaço de string, classe.
const HEX = /#[0-9a-fA-F]{3,8}\b/g;

// As funções de cor do CSS. O `color-mix` vem antes do `color`.
const FUNCAO_DE_COR = /(?<![\w-])(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix|color)\s*\(/g;

// Cor por nome numa propriedade de cor, como atributo (`stroke="white"`,
// `stroke={"white"}`) ou chave de objeto (`fill: "white"`, `"fill": "white"`).
const COR_POR_NOME =
  /(?<![\w-])(?:fill|stroke|color|backgroundColor|borderColor|stopColor)["']?\s*[=:]\s*\{?\s*(["'`])([a-zA-Z]+)\1/g;

// As palavras que ocupam o lugar de uma cor sem serem uma.
const NAO_SAO_COR = new Set(["none", "currentcolor", "transparent"]);

/** Cada cor escrita à mão no trecho, como aparece nele. */
function coresEscritasAMao(codigo: string): string[] {
  const limpo = semComentarios(codigo);
  return [
    ...[...limpo.matchAll(HEX)].map((m) => m[0]),
    ...[...limpo.matchAll(FUNCAO_DE_COR)].map((m) => m[0]),
    ...[...limpo.matchAll(COR_POR_NOME)].filter((m) => !NAO_SAO_COR.has(m[2].toLowerCase())).map((m) => m[0]),
  ];
}

// O token usado, com ou sem valor de reserva: `var(--color-primary)`,
// `var(--color-primary, #fff)`, `var(--color-gray-100)`.
const TOKEN_USADO = /var\(\s*(--[\w-]+)/g;

function codigo(caminho: string): string {
  return readFileSync(join(RAIZ_SRC, caminho), "utf8");
}

const TOKENS_DO_APP = new Set([...codigo(join("app", "globals.css")).matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

function tokensUsados(trecho: string): string[] {
  return [...new Set([...semComentarios(trecho).matchAll(TOKEN_USADO)].map((m) => m[1]))];
}

/** Os tokens do trecho que não estão definidos no `globals.css`. */
function tokensQueNaoExistem(trecho: string): string[] {
  return tokensUsados(trecho).filter((token) => !TOKENS_DO_APP.has(token));
}

function arquivosDosGraficos(): string[] {
  return PASTAS_DA_CENTRAL.flatMap((pasta) =>
    readdirSync(join(RAIZ_SRC, pasta))
      .filter((nome) => /\.tsx?$/.test(nome) && !/\.test\.tsx?$/.test(nome))
      .map((nome) => join(pasta, nome))
      .filter((caminho) => caminho === ONDE_AS_CORES_MORAM || /from\s+["']recharts["']/.test(codigo(caminho))),
  );
}

// ─── Os casos de controle: o que a varredura tem de pegar, e o que não ──────

const COM_COR_A_MAO: [string, string][] = [
  ["hex numa string inteira", `<Line stroke="#2B2E7E" />`],
  ["hex curto", `<Line stroke="#fff" />`],
  ["hex dentro de uma string maior", `<div style={{ border: "1px solid #E2E8F0" }} />`],
  ["hex numa classe arbitrária do Tailwind", `<span className="h-3 w-3 bg-[#2B2E7E]" />`],
  ["hex no valor de reserva de um token", `<Line stroke="var(--color-primary, #2B2E7E)" />`],
  ["hex na mesma linha de um endereço", `const ajuda = "https://recharts.org/api"; const cor = "#2B2E7E";`],
  ["rgb()", `<Cell fill="rgb(43, 46, 126)" />`],
  ["rgba()", `<Cell fill="rgba(43, 46, 126, 0.5)" />`],
  ["hsl()", `<Cell fill="hsl(237 49% 33%)" />`],
  ["hsla()", `<Cell fill="hsla(237, 49%, 33%, 0.5)" />`],
  ["hwb()", `<Cell fill="hwb(237 18% 51%)" />`],
  ["lab()", `<Cell fill="lab(22% 17 -45)" />`],
  ["lch()", `<Cell fill="lch(22% 48 290)" />`],
  ["oklab()", `<Cell fill="oklab(0.33 0.03 -0.13)" />`],
  ["oklch()", `<Cell fill="oklch(0.33 0.13 275)" />`],
  ["color()", `<Cell fill="color(display-p3 0.17 0.18 0.49)" />`],
  ["color-mix()", `<Cell fill="color-mix(in srgb, var(--color-primary) 50%, var(--color-info))" />`],
  ["cor por nome em atributo", `<Line stroke="white" />`],
  ["cor por nome entre chaves", `<Line stroke={"white"} />`],
  ["cor por nome em fill de objeto", `<XAxis tick={{ fill: "gray" }} />`],
  ["cor por nome em color", `<Tooltip contentStyle={{ color: "black" }} />`],
  ["cor por nome em backgroundColor", `<span style={{ backgroundColor: "red" }} />`],
  ["cor por nome em borderColor", `<span style={{ borderColor: "navy" }} />`],
  ["cor por nome em stopColor", `<stop stopColor="blue" />`],
  ["cor por nome em chave entre aspas", `const estilo = { "fill": "red" };`],
];

const SEM_COR_A_MAO: [string, string][] = [
  ["token do app", `<Line stroke="var(--color-primary)" />`],
  ["cor que vem de constante", `<Line stroke={COR_ATUAL} />`],
  ["sem traço", `<Pie stroke="none" />`],
  ["a cor do texto em volta", `<path fill="currentColor" />`],
  ["transparente", `<rect fill="transparent" />`],
  ["número de issue num comentário de linha", `// o gráfico da issue #817\n<Line stroke={COR_ATUAL} />`],
  ["hex num comentário de bloco", `/* a cor antiga era #2B2E7E */ <Line stroke={COR_ATUAL} />`],
  ["classe da paleta do Tailwind", `<span className="bg-white text-emerald-700" />`],
  ["outra propriedade com nome parecido", `<Line dataKey="visitantes" type="linear" />`],
];

const TOKENS_QUE_NAO_EXISTEM: [string, string, string][] = [
  ["token com o nome errado", `<Line stroke="var(--color-primari)" />`, "--color-primari"],
  ["token errado com valor de reserva", `<Line stroke="var(--color-primari, #2B2E7E)" />`, "--color-primari"],
  ["token com dígito no nome", `<Cell fill="var(--color-gray-100)" />`, "--color-gray-100"],
  ["token fora do globals.css", `<Line stroke="var(--cor-primaria)" />`, "--cor-primaria"],
];

describe("a varredura de cor escrita à mão", () => {
  it.each(COM_COR_A_MAO)("pega %s", (_, trecho) => {
    expect(coresEscritasAMao(trecho)).not.toEqual([]);
  });

  it.each(SEM_COR_A_MAO)("não confunde com cor: %s", (_, trecho) => {
    expect(coresEscritasAMao(trecho)).toEqual([]);
  });
});

describe("a varredura de token", () => {
  it.each(TOKENS_QUE_NAO_EXISTEM)("pega %s", (_, trecho, token) => {
    expect(tokensQueNaoExistem(trecho)).toEqual([token]);
  });

  it("aceita os tokens do app, com ou sem valor de reserva", () => {
    expect(
      tokensQueNaoExistem(`stroke="var(--color-primary)" fill="var(--color-primary-light, var(--color-info))"`),
    ).toEqual([]);
  });
});

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
    const culpados = arquivosDosGraficos().flatMap((caminho) =>
      coresEscritasAMao(codigo(caminho)).map((cor) => `${caminho}: ${cor}`),
    );

    expect(culpados, "Use os tokens do app, var(--color-...), como em lib/central-de-comando/graficos.ts.").toEqual(
      [],
    );
  });

  it("todo token usado nos gráficos existe no globals.css", () => {
    const usados = arquivosDosGraficos().flatMap((caminho) => tokensUsados(codigo(caminho)));
    const faltando = arquivosDosGraficos().flatMap((caminho) =>
      tokensQueNaoExistem(codigo(caminho)).map((token) => `${caminho}: ${token}`),
    );

    expect(usados.length).toBeGreaterThan(0);
    expect(faltando).toEqual([]);
  });
});
