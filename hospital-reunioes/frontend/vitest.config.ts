import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * O harness de teste do frontend (issue #438, PRD #402).
 *
 * A suíte de lógica pura rodava sem config nenhuma. Testar JSX pede duas coisas
 * que o vitest não adivinha sozinho neste projeto:
 *
 * * o `jsx` do transform. O `tsconfig.json` do Next diz `preserve`, porque em
 *   produção quem transforma o JSX é o compilador do Next; no teste não há Next,
 *   e sem esta linha o JSX chegaria cru ao Node.
 * * o alias `@/`, que o Next resolve pelo `paths` do tsconfig e o vitest não lê.
 *
 * O ambiente continua sendo o `node` para a suíte inteira. Quem precisa de DOM
 * pede jsdom no próprio arquivo, pelo comentário `@vitest-environment jsdom`:
 * assim o teste do `middleware.ts` e os de lógica pura seguem rodando fora do
 * navegador, que é onde eles valem.
 */
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
