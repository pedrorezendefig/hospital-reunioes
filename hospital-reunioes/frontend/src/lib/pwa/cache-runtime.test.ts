/**
 * O que o service worker guarda no aparelho (issue #483).
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

/** A lista como ela é em produção, que é a única versão que importa aqui. */
beforeAll(async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.resetModules();
  modulo = await import("./cache-runtime");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

function casa(regra: RuntimeCaching, pathname: string): boolean {
  const url = new URL(`https://app.exemplo.cloud${pathname}`);
  const request = new Request(url, { method: "GET" });
  const { matcher } = regra;
  if (typeof matcher === "function") {
    return Boolean(matcher({ url, request, sameOrigin: true, event: undefined as never }));
  }
  if (matcher instanceof RegExp) return matcher.test(url.href);
  return false;
}

/** A regra que o Serwist aplicaria a este GET: a primeira da lista que casa. */
function regraQueVence(pathname: string, lista = modulo.runtimeCaching) {
  return lista.find((regra) => casa(regra, pathname));
}

describe("dado de cidadão não fica gravado no aparelho (issue #483, ADR 0041)", () => {
  it("sem a regra nova, a resposta do token cairia no cache de 24h do defaultCache", () => {
    // O furo que esta suíte fecha, provado antes da defesa: sem o primeiro item
    // da lista, quem atende a rota do token é a NetworkFirst chamada "apis".
    const semADefesa = modulo.runtimeCaching.slice(1);

    const regra = regraQueVence("/api/ouvidoria-setor/token-opaco-do-email", semADefesa);

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

  it("os dois prefixos protegidos estão declarados", () => {
    expect([...modulo.PREFIXOS_SEM_CACHE_NO_APARELHO]).toEqual([
      "/api/ouvidoria-setor/",
      "/api/ouvidoria/",
    ]);
  });
});
