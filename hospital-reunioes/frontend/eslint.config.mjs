import { readFileSync } from "fs";
import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";
import { pluginHospital } from "./eslint-rules/tells.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

// Travessao (U+2014) e meia-risca (U+2013) sao marca de texto gerado por IA e
// estao banidos de tudo que o usuario ve (ADR 0013). Esta regra trava o front:
// quebra o build se um dos dois aparecer em string ou texto de JSX. Mira so os
// nos `Literal` e `JSXText` de proposito, comentarios ficam de fora (sao ruido,
// nao chegam ao usuario). Os caracteres entram aqui via escape unicode para nao
// existir nenhum travessao literal nem no proprio lint.
const TRAVESSAO = "/[\\u2014\\u2013]/";
const MSG_TRAVESSAO =
  "Sem travessao (U+2014) nem meia-risca (U+2013) em texto visivel (ADR 0013): use virgula, ou hifen entre numeros.";

// Cacoetes regexaveis de texto gerado ("nao e X, e Y" e variantes, fecho
// repetido) em string e texto de JSX (ADR 0071, decisao 1). A lista vive em
// eslint-rules/tells.mjs, espelho de tools/tells_texto.py, e os casos dos dois
// em tools/tells_casos.json. O que ja estava no ar fica em
// eslint-rules/tells_conhecidos.json ate a varredura (issue #1229). Teste fica
// de fora: nome de teste nao chega ao usuario.
const { arquivos: TELLS_CONHECIDOS } = JSON.parse(
  readFileSync(new URL("./eslint-rules/tells_conhecidos.json", import.meta.url), "utf8"),
);

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // MVP: aceitar `any` mas continuar sinalizando como aviso para limpeza incremental.
      "@typescript-eslint/no-explicit-any": "warn",
      "no-restricted-syntax": [
        "error",
        { selector: `Literal[value=${TRAVESSAO}]`, message: MSG_TRAVESSAO },
        { selector: `JSXText[value=${TRAVESSAO}]`, message: MSG_TRAVESSAO },
      ],
    },
  },
  {
    ignores: ["**/*.test.ts", "**/*.test.tsx"],
    plugins: { hospital: pluginHospital },
    rules: {
      "hospital/sem-tells": ["error", { conhecidos: TELLS_CONHECIDOS }],
    },
  },
];

export default eslintConfig;
