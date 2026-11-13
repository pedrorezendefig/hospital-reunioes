/**
 * O roteiro dos prints da página de Ouvidoria e o seed dele (issue #1723,
 * ADR 0094, decisão 5).
 *
 * O roteiro (`scripts/manual/ouvidoria/roteiro.sh`) semeia o banco local e
 * fotografa a tela pelo playwright-cli. Rodar o roteiro de verdade pede o app
 * no ar, o que o CI não tem; aqui se prova o contrato dele: refaz todas as
 * imagens que a página cita, recusa o que não é o app local, e o seed só tem
 * gente e contato de exemplo.
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas } from "./paginas";

const PASTA = join(process.cwd(), "scripts", "manual", "ouvidoria");
const ROTEIRO = join(PASTA, "roteiro.sh");
const SEED_CRU = readFileSync(join(PASTA, "seed.json"), "utf8");
const SEED = JSON.parse(SEED_CRU);

/** Os PNGs que o roteiro grava: o último argumento de cada `print`. */
function imagensDoRoteiro(texto: string): string[] {
  return Array.from(texto.matchAll(/^\s*print(?:_janela)?\s.*"([^"/]+\.png)"\s*$/gm), (m) => m[1]);
}

/** Todo texto do seed, folha por folha. */
function folhas(valor: unknown): string[] {
  if (typeof valor === "string") return [valor];
  if (valor && typeof valor === "object") return Object.values(valor).flatMap(folhas);
  return [];
}

describe("o roteiro dos prints da página de Ouvidoria", () => {
  it("refaz todas as imagens que a página cita, e só elas", () => {
    const pagina = carregarPaginasDoManual().find((p) => p.modulo === "ouvidoria")!;
    const citadas = imagensCitadas(pagina.corpo);
    const doRoteiro = imagensDoRoteiro(readFileSync(ROTEIRO, "utf8"));

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

describe("o seed da página de Ouvidoria", () => {
  it("a ouvidora de exemplo fica na faixa P1300, longe das pessoas dos outros roteiros", () => {
    expect(SEED.ouvidora.id).toMatch(/^P13\d\d$/);
  });

  it("todo e-mail do seed é de exemplo", () => {
    const emails = SEED_CRU.match(/[\w.+-]+@[\w.-]+/g) ?? [];
    expect(emails.length).toBeGreaterThan(0);
    expect(emails.filter((email) => !email.endsWith("@exemplo.local"))).toEqual([]);
  });

  it("nenhum telefone, CPF ou carteirinha no seed", () => {
    const comNumeroLongo = folhas(SEED).filter((texto) => /\d[\d .()-]{7,}\d/.test(texto));
    expect(comNumeroLongo).toEqual([]);
  });
});

describe("os detectores do roteiro e do seed", () => {
  it("o print de uma janela também conta como imagem do roteiro", () => {
    const texto = 'print "$(linha x)" "linha.png"\nprint_janela "Encerrar" "encerrar.png"\n# print "velho.png"';
    expect(imagensDoRoteiro(texto)).toEqual(["linha.png", "encerrar.png"]);
  });

  it("telefone escrito de qualquer jeito é pego", () => {
    for (const telefone of ["(21) 99876-5432", "21998765432", "+55 21 99887-7665", "123.456.789-09"]) {
      expect(folhas({ contato: telefone }).filter((t) => /\d[\d .()-]{7,}\d/.test(t))).toEqual([telefone]);
    }
  });
});
