import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

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
];

export default eslintConfig;
