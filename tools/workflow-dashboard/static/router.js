'use strict';

/* Router de hash do Hospital OS (ADR 0062, decisão 8; issue #944).
   A rota é aba, item aberto e filtros: #issues/930, #prs/930,
   #producao/v0.161.0, #issues?resp=...&fase=.... Único módulo que lê e
   escreve o location.hash: o app.js recebe e entrega a rota como objeto
   { aba, item, filtros }, com os filtros como texto. */

export const ABAS = ['issues', 'prs', 'producao', 'mapa', 'dominio'];

/* hashes da navegação antiga (bookmarks) caem na aba que herdou o conteúdo;
   Plano, Pendências e Guia saíram (ADR 0062, decisão 3) e caem na home */
const ALIAS = {
  plano: 'issues', pendencias: 'issues', guia: 'issues',
  setup: 'issues', workflow: 'issues', fluxo: 'issues', bastidores: 'issues',
  agora: 'producao', deploys: 'producao',
};

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
  return { aba: abaValida(aba), item: item || null, filtros };
}
