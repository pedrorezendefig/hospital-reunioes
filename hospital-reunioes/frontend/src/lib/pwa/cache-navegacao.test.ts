/**
 * @vitest-environment jsdom
 *
 * O caminho de gravação que NÃO passa pelo service worker (issue #508).
 *
 * A lista do `cache-runtime.ts` manda no que o service worker guarda, e só
 * nisso. O `cacheOnNavigation` do `@serwist/next` é outra coisa: ele liga um
 * segundo worker, que roda na PÁGINA, embrulha `history.pushState` e
 * `history.replaceState` e escuta o evento `online`. A cada navegação esse
 * worker faz `caches.open("pages").put(url)` com a mão dele (está lá, escrito,
 * em `public/swe-worker-*.js`), escrita imperativa que nenhum matcher do
 * `sw.ts` intercepta.
 *
 * Quer dizer: a suíte do `cache-runtime` pode ficar inteira verde com a URL de
 * `/aceite/{token}` indo para o disco do aparelho assim mesmo. Foi o que
 * aconteceu na primeira rodada deste PR. Por isso este arquivo não interroga a
 * nossa lista: ele carrega o `sw-entry` DE VERDADE do `@serwist/next`, com a
 * opção que o `next.config.ts` declara hoje, e olha se a URL do token sai da
 * página rumo ao worker.
 */

import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `import.meta.url` no ambiente jsdom não é uma URL `file:`, então a raiz vem
// do cwd do vitest, que é a pasta do `vitest.config.ts`.
const RAIZ_DO_FRONTEND = process.cwd();
const require = createRequire(path.join(RAIZ_DO_FRONTEND, "package.json"));
const SW_ENTRY = path.join(
  path.dirname(require.resolve("@serwist/next/package.json")),
  "dist/sw-entry.js"
);

const ROTA_DE_TOKEN = "/aceite/token-opaco-do-email";

/** O que o `next.config.ts` declara hoje, lido do fonte. */
function cacheOnNavigationDeclarado(): boolean {
  const fonte = readFileSync(path.join(RAIZ_DO_FRONTEND, "next.config.ts"), "utf8");
  const achado = fonte.match(/^\s*cacheOnNavigation:\s*(true|false),/m);
  if (!achado) throw new Error("next.config.ts não declara cacheOnNavigation");
  return achado[1] === "true";
}

const pushStateOriginal = history.pushState;
const replaceStateOriginal = history.replaceState;

/**
 * Sobe o `sw-entry` da biblioteca como ele sobe no navegador e devolve tudo o
 * que a página mandou para o worker de navegação.
 */
async function carregarSwEntry(cacheOnNavigation: boolean): Promise<unknown[]> {
  const enviado: unknown[] = [];
  vi.stubGlobal(
    "Worker",
    class {
      postMessage(mensagem: unknown) {
        enviado.push(mensagem);
      }
    }
  );
  vi.stubGlobal("caches", { open: vi.fn() });
  Object.defineProperty(window.navigator, "serviceWorker", {
    configurable: true,
    value: { register: vi.fn(), addEventListener: vi.fn() },
  });

  (self as unknown as Record<string, unknown>).__SERWIST_SW_ENTRY = {
    scope: "/",
    sw: "/sw.js",
    register: false,
    reloadOnOnline: false,
    cacheOnNavigation,
    // O `@serwist/next` só emite este arquivo quando `cacheOnNavigation` é
    // true (`shouldBuildSWEntryWorker = cacheOnNavigation`), então o cenário
    // fiel amarra os dois.
    swEntryWorker: cacheOnNavigation ? "/swe-worker.js" : undefined,
  };

  vi.resetModules();
  await import(SW_ENTRY);
  return enviado;
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  history.pushState = pushStateOriginal;
  history.replaceState = replaceStateOriginal;
  vi.unstubAllGlobals();
  delete (self as unknown as Record<string, unknown>).__SERWIST_SW_ENTRY;
});

describe("a página não grava a URL de token no cache por fora do service worker (issue #508)", () => {
  it("com cacheOnNavigation ligado, a URL do token vai para o worker que escreve no cache pages", async () => {
    // O furo, provado antes da defesa e contra a biblioteca de verdade. Sem
    // este caso o teste de baixo não valeria nada: ele passaria também se o
    // `sw-entry` nunca chegasse a rodar aqui.
    const enviado = await carregarSwEntry(true);

    history.replaceState({}, "", ROTA_DE_TOKEN);

    expect(enviado).toEqual([{ type: "__FRONTEND_NAV_CACHE__", url: ROTA_DE_TOKEN }]);
  });

  it("com o que o next.config.ts declara hoje, nada sai da página", async () => {
    const enviado = await carregarSwEntry(cacheOnNavigationDeclarado());

    history.replaceState({}, "", ROTA_DE_TOKEN);
    history.pushState({}, "", "/ouvidoria-setor/token-opaco-do-email");
    window.dispatchEvent(new Event("online"));

    expect(enviado).toEqual([]);
  });

  it("o next.config.ts declara a decisão explicitamente, e não por herança do default", async () => {
    expect(cacheOnNavigationDeclarado()).toBe(false);
  });
});

describe("a faxina está ligada no service worker de verdade (issue #508)", () => {
  it("o sw.ts chama registrarLimpezaNaAtivacao", () => {
    // `sw.ts` só existe dentro de um ServiceWorkerGlobalScope e não roda em
    // teste nenhum, então apagar a chamada dele deixava a suíte inteira verde.
    // Ler o fonte é feio e é a única prova possível dessa fiação.
    const fonte = readFileSync(path.join(RAIZ_DO_FRONTEND, "src/app/sw.ts"), "utf8");

    expect(fonte).toMatch(/registrarLimpezaNaAtivacao\(self\);/);
  });
});
