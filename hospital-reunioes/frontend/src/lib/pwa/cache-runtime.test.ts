/**
 * O que o service worker guarda no aparelho (issues #483 e #508).
 *
 * Esta suíte existe por causa de um furo concreto: a regra "apis" do
 * `defaultCache` do `@serwist/next` casa qualquer GET same-origin em `/api/` e
 * o serve por NetworkFirst com 24h de validade no Cache Storage. Depois do ADR
 * 0041, a resposta da rota do token carrega relato integral e o nome de quem
 * manifestou, e o link de uso único deixava de proteger o caso: consumido o
 * link, bastava o modo avião para o service worker servir o JSON gravado.
 *
 * Testar `sw.ts` direto não dá (ele só existe dentro de um
 * ServiceWorkerGlobalScope), então a lista mora num módulo próprio.
 *
 * Os testes carregam o módulo com `NODE_ENV=production` porque o `defaultCache`
 * TROCA de conteúdo fora de produção: em desenvolvimento ele é um NetworkOnly
 * para tudo, e um teste que rodasse contra essa versão passaria mesmo sem a
 * regra nova, provando nada. A regra "apis" só existe na versão de produção, e
 * é ela que precisa ficar do lado de fora.
 */

import { NetworkFirst, NetworkOnly, type RuntimeCaching } from "serwist";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

type ModuloDoCache = typeof import("./cache-runtime");

let modulo: ModuloDoCache;
let defaultCacheDeProducao: RuntimeCaching[];

/** A lista como ela é em produção, que é a única versão que importa aqui. */
beforeAll(async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.resetModules();
  modulo = await import("./cache-runtime");
  // Depois do módulo e sem novo reset, para pegar a MESMA instância que ele
  // espalhou dentro de `runtimeCaching`: é o que deixa comparar por identidade
  // lá embaixo, no teste da ordem da lista.
  ({ defaultCache: defaultCacheDeProducao } = await import("@serwist/next/worker"));
});

afterEach(() => {
  vi.unstubAllEnvs();
});

/**
 * Cabeçalhos que mudam a regra do `defaultCache` que atende o pedido.
 *
 * A navegação de verdade não manda `Content-Type` (esse cabeçalho vem na
 * RESPOSTA), então o pedido de documento vai sem nada e cai na regra "others"
 * do `defaultCache`. A navegação do app router manda os cabeçalhos do RSC e
 * cai em "pages-rsc"/"pages-rsc-prefetch".
 */
const NAVEGACAO = {};
const NAVEGACAO_RSC = { RSC: "1" };
const NAVEGACAO_RSC_PREFETCH = { RSC: "1", "Next-Router-Prefetch": "1" };

function casa(
  regra: RuntimeCaching,
  pathname: string,
  headers: Record<string, string> = {}
): boolean {
  const url = new URL(`https://app.exemplo.cloud${pathname}`);
  const request = new Request(url, { method: "GET", headers });
  const { matcher } = regra;
  if (typeof matcher === "function") {
    return Boolean(matcher({ url, request, sameOrigin: true, event: undefined as never }));
  }
  if (matcher instanceof RegExp) return matcher.test(url.href);
  return false;
}

/** A regra que o Serwist aplicaria a este GET: a primeira da lista que casa. */
function regraQueVence(
  pathname: string,
  headers: Record<string, string> = {},
  lista = modulo.runtimeCaching
) {
  return lista.find((regra) => casa(regra, pathname, headers));
}

describe("dado de cidadão não fica gravado no aparelho (issue #483, ADR 0041)", () => {
  it("sem a regra nova, a resposta do token cairia no cache de 24h do defaultCache", () => {
    // O furo que esta suíte fecha, provado antes da defesa: sem o primeiro item
    // da lista, quem atende a rota do token é a NetworkFirst chamada "apis".
    const semADefesa = modulo.runtimeCaching.slice(1);

    const regra = regraQueVence("/api/ouvidoria-setor/token-opaco-do-email", {}, semADefesa);

    expect(regra?.handler).toBeInstanceOf(NetworkFirst);
    expect((regra?.handler as NetworkFirst).cacheName).toContain("apis");
  });

  it("com a regra nova, a rota do token do responsável cai em NetworkOnly", () => {
    const regra = regraQueVence("/api/ouvidoria-setor/token-opaco-do-email");

    expect(regra).toBe(modulo.runtimeCaching[0]);
    expect(regra?.handler).toBeInstanceOf(NetworkOnly);
  });

  it("o resto do módulo da Ouvidoria também: o painel e a consulta por protocolo", () => {
    expect(regraQueVence("/api/ouvidoria/manifestacoes")).toBe(modulo.runtimeCaching[0]);
    expect(regraQueVence("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")).toBe(
      modulo.runtimeCaching[0]
    );
  });

  it("o resto do app segue com o cache de sempre: a regra nova não é um NetworkOnly geral", () => {
    const calendario = regraQueVence("/api/reunioes/calendario");

    expect(calendario).not.toBe(modulo.runtimeCaching[0]);
    expect(calendario?.handler).toBeInstanceOf(NetworkFirst);
    expect(modulo.podeGuardarNoAparelho("/api/pops/biblioteca")).toBe(true);
    expect(modulo.podeGuardarNoAparelho("/_next/static/chunks/main.js")).toBe(true);
  });

  it("o contador de novidades nunca é servido do cache do aparelho", () => {
    // A dúvida da review do #487: um total antigo servido pelo service worker
    // apareceria como número certo depois de a rota já ter falhado. A regra da
    // Ouvidoria pega esta rota pelo prefixo, então o handler é NetworkOnly e
    // não existe resposta velha para servir.
    expect(modulo.podeGuardarNoAparelho("/api/ouvidoria/novidades")).toBe(false);
    expect(regraQueVence("/api/ouvidoria/novidades")).toBe(modulo.runtimeCaching[0]);
  });

  it("o prefixo é comparado do início, e não em qualquer lugar do caminho", () => {
    // Sem a âncora, uma rota de outro módulo que mencionasse a Ouvidoria
    // entraria na regra sem motivo.
    expect(modulo.podeGuardarNoAparelho("/api/relatorios/api/ouvidoria/tudo")).toBe(true);
    expect(modulo.podeGuardarNoAparelho("/api/ouvidoria-setor/x")).toBe(false);
  });

  it("os prefixos protegidos estão declarados", () => {
    expect([...modulo.PREFIXOS_SEM_CACHE_NO_APARELHO]).toEqual([
      "/api/aceite/",
      "/api/ouvidoria-setor/",
      "/api/ouvidoria/",
      "/aceite/",
      "/ouvidoria-setor",
    ]);
  });
});

describe("o aceite do participante tem o mesmo furo da Ouvidoria (issue #508)", () => {
  it("sem a defesa, o GET do link de aceite cairia no cache de 24h do defaultCache", () => {
    // Mesma prova de antes da correção: com as outras portas todas abertas,
    // quem atenderia a rota tokenizada do aceite é a NetworkFirst "apis".
    const semADefesa = modulo.runtimeCaching.slice(1);

    const regra = regraQueVence("/api/aceite/token-opaco-do-email", {}, semADefesa);

    expect(regra?.handler).toBeInstanceOf(NetworkFirst);
    expect((regra?.handler as NetworkFirst).cacheName).toContain("apis");
  });

  it("com a defesa, o GET do link de aceite cai em NetworkOnly", () => {
    const regra = regraQueVence("/api/aceite/token-opaco-do-email");

    expect(regra).toBe(modulo.runtimeCaching[0]);
    expect(regra?.handler).toBeInstanceOf(NetworkOnly);
    expect(modulo.podeGuardarNoAparelho("/api/aceite/token-opaco-do-email")).toBe(false);
  });

  it("uma rota de outro módulo que só mencione aceite segue cacheando", () => {
    expect(modulo.podeGuardarNoAparelho("/api/reunioes/aceite/resumo")).toBe(true);
  });
});

describe("a casca das rotas de token não fica no aparelho (issue #508)", () => {
  // A URL gravada no Cache Storage CARREGA O TOKEN, que é a credencial inteira
  // dessas rotas. ATENÇÃO: o que este describe prova é só que a lista do
  // service worker recusa esse caminho. Existe uma segunda porta, o
  // `cacheOnNavigation`, que grava por fora dela e que estes testes NÃO
  // alcançam. Ela é provada no `cache-navegacao.test.ts`.
  const rotasDeToken = ["/aceite/token-opaco-do-email", "/ouvidoria-setor/token-opaco-do-email"];

  it.each(rotasDeToken)("a navegação de %s cai em NetworkOnly", (rota) => {
    expect(regraQueVence(rota, NAVEGACAO)).toBe(modulo.runtimeCaching[0]);
  });

  it("a tela de acionamento por protocolo, que não tem barra no caminho, também", () => {
    // `/ouvidoria-setor` sem barra é o caminho da tela que recebe o protocolo
    // na query. Um prefixo com barra no fim deixaria ela de fora.
    expect(regraQueVence("/ouvidoria-setor", NAVEGACAO)).toBe(modulo.runtimeCaching[0]);
    expect(modulo.podeGuardarNoAparelho("/ouvidoria-setor")).toBe(false);
  });

  it.each(rotasDeToken)("a navegação RSC de %s cai em NetworkOnly", (rota) => {
    expect(regraQueVence(rota, NAVEGACAO_RSC)).toBe(modulo.runtimeCaching[0]);
    expect(regraQueVence(rota, NAVEGACAO_RSC_PREFETCH)).toBe(modulo.runtimeCaching[0]);
  });

  it("sem a defesa, a casca de /aceite/{token} cairia num cache de tela", () => {
    const semADefesa = modulo.runtimeCaching.slice(1);

    const regra = regraQueVence("/aceite/token-opaco-do-email", NAVEGACAO, semADefesa);

    expect(regra?.handler).not.toBeInstanceOf(NetworkOnly);
    expect((regra?.handler as NetworkFirst).cacheName).toContain("others");
  });

  it("o resto das telas segue funcionando offline: a defesa não é geral", () => {
    const painel = regraQueVence("/reunioes", NAVEGACAO);

    expect(painel).not.toBe(modulo.runtimeCaching[0]);
    expect(modulo.podeGuardarNoAparelho("/ouvidoria/painel")).toBe(true);
    expect(modulo.podeGuardarNoAparelho("/reunioes")).toBe(true);
  });
});

describe("nada pode entrar depois do defaultCache (issue #508)", () => {
  it("a defesa é a primeira regra e o defaultCache é o rabo intocado da lista", () => {
    // A última regra do `defaultCache` é um catch-all `/.*/i`, então uma regra
    // nova posta DEPOIS dele nunca seria alcançada: pareceria proteção e não
    // seria. Este teste morre se alguém acrescentar qualquer coisa no fim.
    const depoisDaDefesa = modulo.runtimeCaching.slice(1);

    expect(modulo.runtimeCaching[0].handler).toBeInstanceOf(NetworkOnly);
    expect(depoisDaDefesa).toHaveLength(defaultCacheDeProducao.length);
    depoisDaDefesa.forEach((regra, i) => {
      expect(regra).toBe(defaultCacheDeProducao[i]);
    });
  });
});
