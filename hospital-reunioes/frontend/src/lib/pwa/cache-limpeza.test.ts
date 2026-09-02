/**
 * A faxina do que já ficou gravado no aparelho (issue #508).
 *
 * A regra `NetworkOnly` impede a gravação daqui para frente, mas não desfaz o
 * passado: quem abriu o link do email antes do deploy tem o caso inteiro no
 * Cache Storage e segue exposto até o `maxAgeSeconds` de 24h vencer. Vinte e
 * quatro horas de dado de cidadão no celular pessoal não é janela aceitável,
 * então o service worker novo varre os caches na ativação e apaga tudo o que
 * hoje seria proibido gravar.
 *
 * A varredura olha os MESMOS prefixos da lista de runtime, de propósito: um
 * prefixo novo lá passa a ser apagado aqui sem ninguém lembrar de mexer nos
 * dois lugares.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  limparEntradasProibidas,
  registrarLimpezaNaAtivacao,
} from "./cache-limpeza";

const ORIGEM = "https://app.exemplo.cloud";

/** Um duplo de Cache Storage com o mínimo que a faxina usa. */
function montarCacheStorage(conteudo: Record<string, string[]>) {
  const caches = new Map<string, Set<string>>(
    Object.entries(conteudo).map(([nome, urls]) => [nome, new Set(urls)])
  );
  const storage = {
    keys: async () => [...caches.keys()],
    open: async (nome: string) => {
      const urls = caches.get(nome) ?? new Set<string>();
      return {
        keys: async () => [...urls].map((url) => new Request(url)),
        delete: async (request: Request) => urls.delete(request.url),
      };
    },
  };
  return { storage: storage as unknown as CacheStorage, caches };
}

function conteudoDe(caches: Map<string, Set<string>>, nome: string): string[] {
  return [...(caches.get(nome) ?? [])];
}

describe("a faxina apaga o que ficou gravado antes do deploy (issue #508)", () => {
  it("apaga a resposta do token da Ouvidoria e a do aceite gravadas no cache apis", async () => {
    const { storage, caches } = montarCacheStorage({
      apis: [
        `${ORIGEM}/api/ouvidoria-setor/token-opaco-do-email`,
        `${ORIGEM}/api/aceite/token-opaco-do-email`,
        `${ORIGEM}/api/reunioes/calendario`,
      ],
    });

    const apagadas = await limparEntradasProibidas(storage, ORIGEM);

    expect(conteudoDe(caches, "apis")).toEqual([`${ORIGEM}/api/reunioes/calendario`]);
    expect(apagadas).toBe(2);
  });

  it("apaga a casca das rotas de token guardada nos caches de página", async () => {
    const { storage, caches } = montarCacheStorage({
      pages: [`${ORIGEM}/aceite/token-opaco-do-email`, `${ORIGEM}/reunioes`],
      "pages-rsc": [`${ORIGEM}/ouvidoria-setor/token-opaco-do-email`],
      others: [`${ORIGEM}/aceite/token-opaco-do-email?fonte=email`],
    });

    await limparEntradasProibidas(storage, ORIGEM);

    expect(conteudoDe(caches, "pages")).toEqual([`${ORIGEM}/reunioes`]);
    expect(conteudoDe(caches, "pages-rsc")).toEqual([]);
    expect(conteudoDe(caches, "others")).toEqual([]);
  });

  it("não encosta no que o app precisa para funcionar offline", async () => {
    const intocaveis = {
      "static-js-assets": [`${ORIGEM}/_next/static/chunks/main.js`],
      apis: [`${ORIGEM}/api/pops/biblioteca`, `${ORIGEM}/api/reunioes/aceite/resumo`],
      pages: [`${ORIGEM}/ouvidoria/painel`],
    };
    const { storage, caches } = montarCacheStorage(intocaveis);

    const apagadas = await limparEntradasProibidas(storage, ORIGEM);

    expect(apagadas).toBe(0);
    for (const [nome, urls] of Object.entries(intocaveis)) {
      expect(conteudoDe(caches, nome)).toEqual(urls);
    }
  });

  it("não apaga entrada de outra origem que tenha o mesmo caminho", async () => {
    // O cache "cross-origin" guarda coisa de fora. Um caminho igual num
    // domínio de terceiro não é dado do nosso cidadão, e apagar ali seria
    // mexer no que não é nosso.
    const { storage, caches } = montarCacheStorage({
      "cross-origin": ["https://cdn.terceiro.example/api/aceite/nada-a-ver"],
    });

    await limparEntradasProibidas(storage, ORIGEM);

    expect(conteudoDe(caches, "cross-origin")).toEqual([
      "https://cdn.terceiro.example/api/aceite/nada-a-ver",
    ]);
  });
});

describe("a faxina está ligada na ativação do service worker (issue #508)", () => {
  function montarEscopo() {
    const ouvintes = new Map<string, (evento: unknown) => void>();
    const { storage } = montarCacheStorage({
      apis: [`${ORIGEM}/api/aceite/token-opaco-do-email`],
    });
    const escopo = {
      addEventListener: (tipo: string, ouvinte: (evento: unknown) => void) => {
        ouvintes.set(tipo, ouvinte);
      },
      caches: storage,
      location: { origin: ORIGEM },
    };
    return { escopo: escopo as unknown as ServiceWorkerGlobalScope, ouvintes };
  }

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("registra a faxina no evento activate, e não em outro", () => {
    const { escopo, ouvintes } = montarEscopo();

    registrarLimpezaNaAtivacao(escopo);

    expect([...ouvintes.keys()]).toEqual(["activate"]);
  });

  it("segura a ativação com waitUntil até a faxina terminar", async () => {
    // Sem o waitUntil o service worker pode ativar e começar a servir enquanto
    // a varredura ainda roda, e a janela que a issue fecha continua aberta.
    const { escopo, ouvintes } = montarEscopo();
    registrarLimpezaNaAtivacao(escopo);
    const segurado: Promise<unknown>[] = [];

    ouvintes.get("activate")?.({ waitUntil: (p: Promise<unknown>) => segurado.push(p) });

    expect(segurado).toHaveLength(1);
    await expect(segurado[0]).resolves.toBe(1);
  });
});
