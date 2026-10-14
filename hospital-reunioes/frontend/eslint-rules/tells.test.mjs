// Testes da regra `hospital/sem-tells` (ADR 0071, decisao 1).
//
// Os casos vem do `tools/tells_casos.json`, o mesmo arquivo que o pytest do
// lint do Manual le (`tools/test_tells_texto.py`): os dois lints concordam em
// cada caso, ou um dos dois fica vermelho.
import { readFileSync } from "node:fs";
import { Linter } from "eslint";
import { describe, expect, it } from "vitest";
import { CACOETES, acharTells, pluginHospital } from "./tells.mjs";

const { casos } = JSON.parse(
  readFileSync(new URL("../../../tools/tells_casos.json", import.meta.url), "utf8"),
);

const nomes = (texto) => [...new Set(acharTells(texto).map((o) => o.cacoete))].sort();

function lintar(codigo) {
  const linter = new Linter({ configType: "flat" });
  return linter.verify(codigo, [
    {
      files: ["**/*.jsx"],
      plugins: { hospital: pluginHospital },
      languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
      rules: { "hospital/sem-tells": "error" },
    },
  ], "tela.jsx");
}

describe("acharTells com os casos compartilhados", () => {
  it.each(casos.map((c) => [c.texto.slice(0, 50), c]))("%s", (_, caso) => {
    expect(nomes(caso.texto)).toEqual([...caso.tells].sort());
  });

  it("tirar um cacoete da lista derruba algum caso", () => {
    for (const nome of CACOETES.map((c) => c.nome)) {
      const sem = CACOETES.filter((c) => c.nome !== nome);
      const falhas = casos.filter((c) => {
        const achados = [...new Set(acharTells(c.texto, sem).map((o) => o.cacoete))].sort();
        return JSON.stringify(achados) !== JSON.stringify([...c.tells].sort());
      });
      expect(falhas.length, `tirar '${nome}' nao derrubou nenhum caso`).toBeGreaterThan(0);
    }
  });
});

describe("regra hospital/sem-tells", () => {
  it.each(casos.map((c) => [c.texto.slice(0, 50), c]))("string: %s", (_, caso) => {
    const erros = lintar(`const t = ${JSON.stringify(caso.texto)};`);
    expect(erros.map((e) => e.ruleId)).toEqual(caso.tells.map(() => "hospital/sem-tells"));
  });

  const deUmaLinha = casos.filter((c) => !c.texto.includes("\n"));
  it.each(deUmaLinha.map((c) => [c.texto.slice(0, 50), c]))("JSX: %s", (_, caso) => {
    const erros = lintar(`const el = <p>${caso.texto}</p>;`);
    expect(erros.map((e) => e.ruleId)).toEqual(caso.tells.map(() => "hospital/sem-tells"));
  });

  it("cacoete conhecido no arquivo listado passa, em outro arquivo trava", () => {
    const codigo = 'const t = "A ata não é um resumo, é a memória.";';
    const conhecidos = { "src/tela.jsx": ["não é um resumo, é"] };
    const lintarEm = (arquivo) =>
      new Linter({ configType: "flat" }).verify(
        codigo,
        [
          {
            files: ["**/*.jsx"],
            plugins: { hospital: pluginHospital },
            rules: { "hospital/sem-tells": ["error", { conhecidos }] },
          },
        ],
        { filename: `${process.cwd()}/${arquivo}` },
      );
    expect(lintarEm("src/tela.jsx")).toEqual([]);
    expect(lintarEm("src/outra.jsx")).toHaveLength(1);
  });

  it("a lista de conhecidos do front cobre o que esta no ar e nada mais", () => {
    const { arquivos } = JSON.parse(
      readFileSync(new URL("./tells_conhecidos.json", import.meta.url), "utf8"),
    );
    for (const [arquivo, trechos] of Object.entries(arquivos)) {
      const fonte = readFileSync(new URL(`../${arquivo}`, import.meta.url), "utf8");
      const achados = acharTells(fonte).map((o) => o.trecho);
      for (const trecho of trechos) {
        expect(achados, `${arquivo}: "${trecho}" ja saiu, tire da lista`).toContain(trecho);
      }
    }
  });

  it("depois da varredura (issue #1229) nenhum cacoete do front fica de fora da regra", () => {
    const { arquivos } = JSON.parse(
      readFileSync(new URL("./tells_conhecidos.json", import.meta.url), "utf8"),
    );
    expect(arquivos).toEqual({});
  });

  it("a mensagem cita o cacoete e o trecho", () => {
    const [erro] = lintar('const t = "A ata nao vale isso. A ata não é um resumo, é a memória.";');
    expect(erro.message).toContain("nao-e-x-e-y");
    expect(erro.message).toContain('"não é um resumo, é"');
  });
});
