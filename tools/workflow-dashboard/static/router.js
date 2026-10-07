'use strict';

/* Router de hash do Hospital OS (ADR 0062, decisão 8; issue #944).
   A rota é aba, item aberto e filtros: #issues/930, #prs/930,
   #producao/v0.161.0, #issues?resp=...&fase=.... Único módulo que lê e
   escreve o location.hash: o app.js recebe e entrega a rota como objeto
   { aba, item, filtros }, com os filtros como texto. */

export const ABAS = ['issues', 'prs', 'producao', 'documentacao'];

/* sub-pills da aba Documentação: o item da rota (#documentacao/decisoes);
   o Glossário leva o termo depois da barra (#documentacao/glossario/ata) */
export const SUBS_DOC = ['fluxo', 'mapa', 'decisoes', 'glossario'];

/* hashes da navegação antiga (bookmarks) caem na aba que herdou o conteúdo;
   Plano, Pendências e Guia saíram (ADR 0062, decisão 3) e caem na home;
   Mapa e Domínio viraram sub-pills de Documentação */
const ALIAS = {
  plano: 'issues', pendencias: 'issues', guia: 'issues',
  setup: 'issues', workflow: 'issues', fluxo: 'issues', bastidores: 'issues',
  agora: 'producao', deploys: 'producao',
  mapa: 'documentacao', dominio: 'documentacao',
};
/* a sub-pill que o apelido antigo abre (o #mapa cai no Mapa, o #dominio nas Decisões) */
const SUB_DO_ALIAS = { mapa: 'mapa', dominio: 'decisoes' };

/* aba conhecida, apelido antigo ou a home */
export function abaValida(t) {
  return ALIAS[t] || (ABAS.includes(t) ? t : ABAS[0]);
}

/* '#issues/930?fase=pr_aberto' -> { aba: 'issues', item: '930', filtros: { fase: 'pr_aberto' } } */
export function lerHash(hash) {
  const h = String(hash || '').replace(/^#/, '');
  const q = h.indexOf('?');
  const caminho = q < 0 ? h : h.slice(0, q);
  const barra = caminho.indexOf('/');
  const aba = barra < 0 ? caminho : caminho.slice(0, barra);
  const item = barra < 0 ? '' : decodeURIComponent(caminho.slice(barra + 1));
  const filtros = Object.fromEntries(new URLSearchParams(q < 0 ? '' : h.slice(q + 1)));
  return { aba: abaValida(aba), item: item || SUB_DO_ALIAS[aba] || null, filtros };
}

/* o inverso do lerHash; filtro vazio não entra no hash. A barra do item
   fica legível (#documentacao/glossario/ata): o lerHash só corta na primeira */
export function montarHash({ aba, item, filtros }) {
  const q = new URLSearchParams(Object.entries(filtros || {}).filter(([, v]) => v)).toString();
  return `#${aba}${item ? '/' + encodeURIComponent(item).replace(/%2F/g, '/') : ''}${q ? '?' + q : ''}`;
}

/* a rota do endereço atual */
export const lerRota = () => lerHash(location.hash);

/* grava a rota no endereço sem entrada nova no histórico e sem hashchange */
export function gravarRota(rota) {
  const h = montarHash(rota);
  if (location.hash !== h) history.replaceState(null, '', h);
}

/* endereço trocado por fora (link de chip, voltar do navegador, URL colada) */
export function aoMudarRota(fn) {
  window.addEventListener('hashchange', () => fn(lerRota()));
}
