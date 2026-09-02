/**
 * O que o service worker pode guardar no aparelho de quem abre o app.
 *
 * O `defaultCache` do `@serwist/next` traz uma regra que casa QUALQUER GET
 * same-origin em `/api/` e a serve por NetworkFirst, com 24h de validade no
 * Cache Storage. Ela é boa para o resto do app e péssima para a Ouvidoria:
 * desde o ADR 0041, a resposta de `GET /api/ouvidoria-setor/{token}` carrega
 * resumo, relato integral e o nome de quem manifestou, e as rotas de
 * `/api/ouvidoria/` carregam a manifestação inteira.
 *
 * O estrago concreto: o responsável abre o link do email no celular pessoal ou
 * compartilhado. A resposta fica gravada na origem do app. Depois que o link de
 * uso único é consumido (a API passa a devolver 410), basta pôr o aparelho em
 * modo avião para o service worker servir o JSON do cache e a tela reabrir o
 * caso inteiro, sem passar pelo servidor.
 *
 * O `Cache-Control: no-store` do backend NÃO resolve: a Cache Storage API é
 * imperativa e não consulta o cabeçalho. Quem decide é esta lista, e a primeira
 * regra que casa vence, por isso a de baixo entra ANTES do `defaultCache`.
 *
 * O preço é a Ouvidoria não funcionar offline, que é o que se quer: dado de
 * cidadão não fica no aparelho de ninguém.
 */

import { defaultCache } from "@serwist/next/worker";
import { NetworkOnly, type RuntimeCaching } from "serwist";

/**
 * Os prefixos cujo GET nunca é gravado no aparelho.
 *
 * `/api/ouvidoria-setor/` é a rota do link tokenizado do responsável;
 * `/api/ouvidoria/` é o resto do módulo (painel, dossiê e a consulta pública
 * por protocolo), que carrega a manifestação do cidadão do mesmo jeito.
 */
export const PREFIXOS_SEM_CACHE_NO_APARELHO = ["/api/ouvidoria-setor/", "/api/ouvidoria/"] as const;

/** Esta resposta pode ser gravada no Cache Storage do aparelho? */
export function podeGuardarNoAparelho(pathname: string): boolean {
  return !PREFIXOS_SEM_CACHE_NO_APARELHO.some((prefixo) => pathname.startsWith(prefixo));
}

/**
 * A lista que o service worker usa. A regra da Ouvidoria vem primeiro de
 * propósito: o Serwist aplica a primeira que casar, então qualquer coisa
 * depois dela (inclusive a regra "apis" do `defaultCache`) já não alcança
 * essas rotas.
 */
export const runtimeCaching: RuntimeCaching[] = [
  {
    matcher: ({ sameOrigin, url }) => sameOrigin && !podeGuardarNoAparelho(url.pathname),
    handler: new NetworkOnly(),
  },
  ...defaultCache,
];
