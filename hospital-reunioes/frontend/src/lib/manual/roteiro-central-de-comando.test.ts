/**
 * O roteiro dos prints da página de Central de Comando e o seed dele (issue
 * #1725, ADR 0094, decisão 5).
 *
 * O roteiro (`scripts/manual/central-de-comando/roteiro.sh`) semeia a diretora
 * de exemplo, responde no lugar do backend nas rotas da Central com os números
 * do `respostas.py` e fotografa a tela pelo playwright-cli. Rodar o roteiro de
 * verdade pede o app no ar, o que o CI não tem; aqui se prova o contrato dele:
 * refaz todas as imagens que a página cita, recusa o que não é o app local, e
 * o seed e as respostas só têm gente, contato e endereço de exemplo.
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas } from "./paginas";

const PASTA = join(process.cwd(), "scripts", "manual", "central-de-comando");
const ROTEIRO = join(PASTA, "roteiro.sh");
const SEED_CRU = readFileSync(join(PASTA, "seed.json"), "utf8");
const SEED = JSON.parse(SEED_CRU);
const TELAS = ["visao-geral", "dados-do-google", "instagram", "objetivos", "lente", "nota", "ao-vivo"];

/** Os PNGs que o roteiro grava: o último argumento de cada `print` e `print_tela`. */
function imagensDoRoteiro(texto: string): string[] {
  return Array.from(texto.matchAll(/^\s*print(?:_tela)?\s.*"([^"/]+\.png)"\s*$/gm), (m) => m[1]);
}

/** Todo texto de um valor JSON, folha por folha. */
function folhas(valor: unknown): string[] {
  if (typeof valor === "string") return [valor];
  if (valor && typeof valor === "object") return Object.values(valor).flatMap(folhas);
  return [];
}

/** O que cada tela recebe no print: a saída do `respostas.py`. */
function resposta(tela: string): unknown {
  const rodada = spawnSync("python3", [join(PASTA, "respostas.py"), tela], { encoding: "utf8" });
  if (rodada.status !== 0) throw new Error(rodada.stderr);
  return JSON.parse(rodada.stdout);
}

const NUMERO_LONGO = /\d[\d .()-]{7,}\d/;
const EMAIL = /[\w.+-]+@[\w.-]+/g;
const ENDERECO = /https?:\/\/[^\s"']+/g;

/** E-mails, telefones e endereços que não são de exemplo, num texto. */
function dadoReal(texto: string): string[] {
  const emails = (texto.match(EMAIL) ?? []).filter((e) => !e.toLowerCase().endsWith("@exemplo.local"));
  const enderecos = (texto.match(ENDERECO) ?? []).filter(
    (u) => !/^https:\/\/[\w.-]*exemplo\.local(\/|$)/i.test(u) && !u.startsWith("http://www.w3.org/"),
  );
  // Data e hora (2026-11-12, 2026-11-12T12:00:00+00:00) são do período, não de gente.
  const semDatas = texto.replace(/\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?\b/g, "");
  const numeros = NUMERO_LONGO.test(semDatas) ? [texto] : [];
  return [...emails, ...enderecos, ...numeros];
}

describe("o roteiro dos prints da página de Central de Comando", () => {
  it("refaz todas as imagens que a página cita, e só elas", () => {
    const pagina = carregarPaginasDoManual().find((p) => p.modulo === "central-de-comando")!;
    const citadas = imagensCitadas(pagina.corpo);
    const doRoteiro = imagensDoRoteiro(readFileSync(ROTEIRO, "utf8"));

    expect(citadas.length).toBeGreaterThan(0);
    expect([...doRoteiro].sort()).toEqual([...citadas].sort());
  });

  it("responde no lugar do backend em todas as telas que fotografa", () => {
    const texto = readFileSync(ROTEIRO, "utf8");
    const respondidas = Array.from(texto.matchAll(/^responder\s+".*"\s+(\S+)\s*$/gm), (m) => m[1]);
    expect([...respondidas].sort()).toEqual([...TELAS].sort());
  });

  it("recusa rodar contra um endereço que não é o app local", () => {
    const rodada = spawnSync("bash", [ROTEIRO], {
      env: { ...process.env, BASE: "https://app.hospitalsaomatheus.cloud", PATH: "/usr/bin:/bin" },
      encoding: "utf8",
    });

    expect(rodada.status).toBe(1);
    expect(rodada.stderr).toContain("não é o app local");
    expect(rodada.stdout).not.toContain("pronta");
  });
});

describe("o seed e as respostas da página de Central de Comando", () => {
  it("a diretora de exemplo fica na faixa P17250 a P17259, longe das pessoas dos outros roteiros", () => {
    expect(SEED.admin.id).toMatch(/^P1725\d$/);
  });

  it("o seed só tem e-mail de exemplo, e nenhum telefone, CPF ou carteirinha", () => {
    expect((SEED_CRU.match(EMAIL) ?? []).length).toBeGreaterThan(0);
    expect(folhas(SEED).flatMap(dadoReal)).toEqual([]);
  });

  it.each(TELAS)("a resposta da tela %s não traz e-mail, telefone nem endereço que não sejam de exemplo", (tela) => {
    expect(folhas(resposta(tela)).flatMap(dadoReal)).toEqual([]);
  });

  it("as miniaturas das publicações apontam para o endereço de exemplo que o roteiro responde", () => {
    const { principais_publicacoes } = resposta("instagram") as { principais_publicacoes: { miniatura: string }[] };
    expect(principais_publicacoes.length).toBeGreaterThan(0);
    for (const { miniatura } of principais_publicacoes) {
      expect(miniatura).toMatch(/^https:\/\/miniaturas\.exemplo\.local\/[\w-]+\.svg$/);
    }
  });
});

describe("os detectores do roteiro e do dado real", () => {
  it("o print de um pedaço e o da tela inteira contam como imagem do roteiro", () => {
    const texto = 'print "$(bloco x)" "bloco.png"\nprint_tela "tela.png"\n# print "velho.png"';
    expect(imagensDoRoteiro(texto)).toEqual(["bloco.png", "tela.png"]);
  });

  it("e-mail de verdade, telefone e endereço de fora são pegos, em maiúscula ou minúscula", () => {
    for (const real of [
      "diretoria@hospitalsaomatheus.com.br",
      "Fulano@Gmail.com",
      "(21) 99876-5432",
      "123.456.789-09",
      "https://scontent.cdninstagram.com/foto.jpg",
    ]) {
      expect(dadoReal(real), real).not.toEqual([]);
    }
    expect(dadoReal("VERA@EXEMPLO.LOCAL")).toEqual([]);
    expect(dadoReal("2026-11-12T12:00:00+00:00")).toEqual([]);
  });
});
