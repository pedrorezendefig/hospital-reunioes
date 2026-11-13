/**
 * O roteiro dos prints da página de Contas médicas e o seed dele (issue #1724,
 * ADR 0094, decisão 5).
 *
 * O roteiro (`scripts/manual/contas-medicas/roteiro.sh`) semeia o banco local,
 * fotografa a tela pelo playwright-cli e só deixa o PNG chegar à página depois
 * que a guarda confere que o texto fotografado não tem nome de fora do seed.
 * Rodar o roteiro de verdade pede o app no ar, o que o CI não tem; aqui se
 * prova o contrato dele: refaz todas as imagens que a página cita, recusa o
 * que não é o app local, o seed só tem gente e número de exemplo, e a guarda
 * acha o nome de fora mesmo em caixa alta.
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas } from "./paginas";

const PASTA = join(process.cwd(), "scripts", "manual", "contas-medicas");
const ROTEIRO = join(PASTA, "roteiro.sh");
const PRINTS = join(PASTA, "prints.js");
const SEED_CRU = readFileSync(join(PASTA, "seed.json"), "utf8");
const SEED = JSON.parse(SEED_CRU);

/** Os PNGs que o roteiro grava: o arquivo de cada `foto(...)` do prints.js. */
function imagensDoRoteiro(texto: string): string[] {
  return Array.from(texto.matchAll(/^\s*await foto\(\s*"([^"/]+\.png)"/gm), (m) => m[1]);
}

/** Todo texto do seed, folha por folha. */
function folhas(valor: unknown): string[] {
  if (typeof valor === "string") return [valor];
  if (valor && typeof valor === "object") return Object.values(valor).flatMap(folhas);
  return [];
}

const NUMERO_LONGO = /\d[\d .()-]{7,}\d/;
/** A data da conta, como o banco grava: só ela pode ter oito dígitos ou mais. */
const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;

/** A guarda do roteiro, a de verdade, do `semear.py`. */
function nomesDeForaNoTexto(texto: string, nomesDeFora: string[]): string[] {
  const rodada = spawnSync(
    "python3",
    [
      "-I",
      "-c",
      "import json, sys; sys.path.insert(0, sys.argv[1]); from semear import nomes_de_fora_no_texto; " +
        "print(json.dumps(nomes_de_fora_no_texto(sys.argv[2], json.loads(sys.argv[3]))))",
      PASTA,
      texto,
      JSON.stringify(nomesDeFora),
    ],
    { encoding: "utf8" }
  );
  if (rodada.status !== 0) throw new Error(rodada.stderr);
  return JSON.parse(rodada.stdout);
}

describe("o roteiro dos prints da página de Contas médicas", () => {
  it("refaz todas as imagens que a página cita, e só elas", () => {
    const pagina = carregarPaginasDoManual().find((p) => p.modulo === "contas-medicas")!;
    const citadas = imagensCitadas(pagina.corpo);
    const doRoteiro = imagensDoRoteiro(readFileSync(PRINTS, "utf8"));

    expect(citadas.length).toBeGreaterThan(0);
    expect([...doRoteiro].sort()).toEqual([...citadas].sort());
  });

  it("recusa rodar contra um endereço que não é o app local", () => {
    const rodada = spawnSync("bash", [ROTEIRO], {
      env: { ...process.env, BASE: "https://app.hospitalsaomatheus.cloud", PATH: "/usr/bin:/bin" },
      encoding: "utf8",
    });

    expect(rodada.status).toBe(1);
    expect(rodada.stderr).toContain("não é o app local");
    expect(rodada.stdout).not.toContain("prontos");
  });
});

describe("o seed da página de Contas médicas", () => {
  it("a faturista de exemplo fica na faixa P17240 a P17249, longe das pessoas dos outros roteiros", () => {
    expect(SEED.faturista.id).toMatch(/^P1724\d$/);
  });

  it("todo e-mail do seed é de exemplo", () => {
    const emails = SEED_CRU.match(/[\w.+-]+@[\w.-]+/g) ?? [];
    expect(emails.length).toBeGreaterThan(0);
    expect(emails.filter((email) => !email.endsWith("@exemplo.local"))).toEqual([]);
  });

  it("nenhum telefone, CPF ou carteirinha no seed", () => {
    const semAsDatas = folhas(SEED).filter((texto) => !DATA_ISO.test(texto));
    expect(semAsDatas.filter((texto) => NUMERO_LONGO.test(texto))).toEqual([]);
  });

  it("o paciente de cada conta é só o primeiro nome e uma inicial", () => {
    const pacientes = Object.values(SEED.contas).map((c) => (c as { paciente_rotulo: string }).paciente_rotulo);
    expect(pacientes.length).toBeGreaterThan(0);
    expect(pacientes.filter((p) => !/^\p{Lu}\p{Ll}+ \p{Lu}\.$/u.test(p))).toEqual([]);
  });
});

describe("a guarda do dado real nos prints", () => {
  it("acha o nome de fora do seed mesmo quando a tela o mostra em caixa alta", () => {
    const tela = "ATENDIMENTO 172401 · JOSÉ M. · CONTA 72401";
    expect(nomesDeForaNoTexto(tela, ["José M.", "Yara Quintela"])).toEqual(["José M."]);
  });

  it("compara em casefold, não só em minúscula", () => {
    expect(nomesDeForaNoTexto("RUA DA STRASSE NOVA", ["Straße Nova"])).toEqual(["Straße Nova"]);
  });

  it("nome de uma palavra só fica de fora da conta, porque casaria com qualquer texto", () => {
    expect(nomesDeForaNoTexto("Abrir a Fila", ["Fila"])).toEqual([]);
  });
});

describe("os detectores do roteiro e do seed", () => {
  it("cada foto do prints.js conta como imagem do roteiro, e o comentário não", () => {
    const texto = '  await foto("fila.png", fila);\n  // await foto("velho.png")\n  await foto("guia.png");';
    expect(imagensDoRoteiro(texto)).toEqual(["fila.png", "guia.png"]);
  });

  it("telefone e CPF escritos de qualquer jeito são pegos", () => {
    for (const numero of ["(21) 99876-5432", "21998765432", "+55 21 99887-7665", "123.456.789-09"]) {
      expect(NUMERO_LONGO.test(numero)).toBe(true);
      expect(DATA_ISO.test(numero)).toBe(false);
    }
  });
});
