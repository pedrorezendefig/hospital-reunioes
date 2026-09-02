/**
 * O que o service worker pode guardar no aparelho de quem abre o app.
 *
 * O `defaultCache` do `@serwist/next` traz uma regra que casa QUALQUER GET
 * same-origin em `/api/` e a serve por NetworkFirst, com 24h de validade no
 * Cache Storage. Ela é boa para o resto do app e péssima para as rotas abertas
 * por token: desde o ADR 0041, a resposta de `GET /api/ouvidoria-setor/{token}`
 * carrega resumo, relato integral e o nome de quem manifestou, as rotas de
 * `/api/ouvidoria/` carregam a manifestação inteira, e `GET /api/aceite/{token}`
 * carrega a pauta e os dados de quem foi convocado.
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
 * O preço é essas rotas não funcionarem offline, que é o que se quer: dado de
 * cidadão não fica no aparelho de ninguém.
 */

import { defaultCache } from "@serwist/next/worker";
import { NetworkOnly, type RuntimeCaching } from "serwist";

/**
 * As respostas de API que nunca são gravadas no aparelho.
 *
 * `/api/ouvidoria-setor/` é a rota do link tokenizado do responsável;
 * `/api/ouvidoria/` é o resto do módulo (painel, dossiê e a consulta pública
 * por protocolo), que carrega a manifestação do cidadão do mesmo jeito;
 * `/api/aceite/` é o link tokenizado do participante convocado (issue #508).
 */
const PREFIXOS_DE_API_SEM_CACHE = [
  "/api/aceite/",
  "/api/ouvidoria-setor/",
  "/api/ouvidoria/",
] as const;

/**
 * As telas cuja casca HTML também não é gravada.
 *
 * Aqui não tem dado do caso: o que a URL carrega é o TOKEN, e ele é a
 * credencial inteira dessas rotas. Gravar a navegação no Cache Storage é
 * gravar a credencial, e o `cacheOnNavigation: true` do `next.config.ts` faz
 * exatamente isso com toda tela do app.
 */
const PREFIXOS_DE_TELA_SEM_CACHE = ["/aceite/", "/ouvidoria-setor/"] as const;

/** Os prefixos cujo GET nunca é gravado no aparelho. */
export const PREFIXOS_SEM_CACHE_NO_APARELHO = [
  ...PREFIXOS_DE_API_SEM_CACHE,
  ...PREFIXOS_DE_TELA_SEM_CACHE,
] as const;

/** Esta resposta pode ser gravada no Cache Storage do aparelho? */
export function podeGuardarNoAparelho(pathname: string): boolean {
  return !PREFIXOS_SEM_CACHE_NO_APARELHO.some((prefixo) => pathname.startsWith(prefixo));
}

/**
 * A lista que o service worker usa. A regra das rotas de token vem primeiro de
 * propósito: o Serwist aplica a primeira que casar, então qualquer coisa
 * depois dela (inclusive a regra "apis" do `defaultCache`) já não alcança
 * essas rotas.
 *
 * O `defaultCache` termina num catch-all, então regra nova entra AQUI EM CIMA,
 * nunca depois dele: lá embaixo ela nunca seria alcançada e daria só a
 * impressão de proteger. A suíte de teste quebra se alguém tentar.
 */
export const runtimeCaching: RuntimeCaching[] = [
  {
    matcher: ({ sameOrigin, url }) => sameOrigin && !podeGuardarNoAparelho(url.pathname),
    handler: new NetworkOnly(),
  },
  ...defaultCache,
];
