/**
 * A faxina do que o service worker antigo já gravou no aparelho (issue #508).
 *
 * A regra `NetworkOnly` do `cache-runtime.ts` impede a gravação daqui para
 * frente e não desfaz o passado. Quem abriu o link do email antes deste deploy
 * tem a resposta inteira no Cache Storage e continuaria exposto até as 24h do
 * `maxAgeSeconds` vencerem. Esperar essa janela não vale para dado de cidadão,
 * então o service worker novo varre os caches na ativação e apaga o que hoje
 * seria proibido gravar.
 *
 * Quem decide o que sai é o mesmo `podeGuardarNoAparelho` da lista de runtime:
 * um prefixo novo lá passa a ser apagado aqui sem ninguém precisar lembrar de
 * mexer nos dois lugares.
 */

import { podeGuardarNoAparelho } from "./cache-runtime";

/**
 * Apaga de todos os caches da origem as entradas que hoje seriam proibidas.
 *
 * A origem entra como parâmetro porque o Cache Storage guarda também o que veio
 * de fora (fontes, CDN): um caminho parecido num domínio de terceiro não é dado
 * nosso, e apagar ali seria mexer no que não nos pertence.
 *
 * @returns quantas entradas foram apagadas.
 */
export async function limparEntradasProibidas(
  cacheStorage: CacheStorage,
  origem: string
): Promise<number> {
  const nomes = await cacheStorage.keys();
  let apagadas = 0;

  for (const nome of nomes) {
    // Um cache que estoura no meio (removido em paralelo, por exemplo) não
    // pode levar junto os que ainda não foram varridos: a rejeição não aborta
    // a ativação, então o resto ficaria sujo em silêncio.
    try {
      const cache = await cacheStorage.open(nome);
      for (const request of await cache.keys()) {
        const url = new URL(request.url);
        if (url.origin !== origem) continue;
        if (podeGuardarNoAparelho(url.pathname)) continue;
        await cache.delete(request);
        apagadas += 1;
      }
    } catch {
      continue;
    }
  }

  return apagadas;
}

/**
 * Liga a faxina no `activate` do service worker.
 *
 * O `waitUntil` não atrasa a tomada dos clientes: o `clientsClaim: true` do
 * `sw.ts` roda no `waitUntil` do próprio Serwist, em paralelo com este. O que
 * ele garante é que o navegador não mate a varredura no meio por achar o
 * service worker ocioso, e é para isso que ele está aqui.
 */
export function registrarLimpezaNaAtivacao(escopo: ServiceWorkerGlobalScope): void {
  escopo.addEventListener("activate", (evento) => {
    evento.waitUntil(limparEntradasProibidas(escopo.caches, escopo.location.origin));
  });
}
