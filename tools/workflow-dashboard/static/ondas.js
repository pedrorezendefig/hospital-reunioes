'use strict';

/* Fluxo do PRD no card do PRD aberto (issue #943, ADR 0062, decisão 3,
   emenda de 06/10/2026), renderer próprio em SVG (ADR 0025, sem biblioteca).
   Uma linha por fatia: o nó da fatia (bolinha na cor de quem assumiu, borda
   na cor da fase), a seta para o PR dela (borda na cor da fase do PR) e, no
   ar, a versão. As linhas vêm agrupadas em faixas por onda, do payload
   `fases.ondas` (quem calcula é o fases.py, aqui só se desenha); a seta no
   corredor da esquerda é o `blocked_by` aberto entre fatias do mesmo PRD:
   sai da bloqueadora e entra na bloqueada. Clicar na fatia abre o card dela
   (o data-act "onda" borbulha até o handler delegado do app.js); PR e
   versão são links de hash para as outras abas. Só tokens do :root; com
   reduceMotion o desenho nasce parado. */

import { esc, reduceMotion } from './ui.js';
import { corDaPessoa } from './pessoas.js';
import { montarHash } from './router.js';
import { COLUNAS } from './prs.js';

const WF = 192, WP = 156, WV = 92, H = 42;   // largura dos nós (fatia, PR, versão) e altura
const GX = 34, GY = 12, FAIXA = 24;          // vão com a seta do fluxo, vão entre linhas, cabeçalho da onda
const CORREDOR = 30, MARGEM = 8;             // corredor das setas de bloqueio e borda do desenho
const PISTAS = 4;                            // setas de bloqueio em pistas paralelas, para não se sobreporem
const MAX_TITULO = 23;
const X_FATIA = MARGEM + CORREDOR;
const X_PR = X_FATIA + WF + GX;
const X_VER = X_PR + WP + GX;

const NOME_FASE_PR = Object.fromEntries([...COLUNAS, ['fechado_sem_merge', 'fechado sem merge']]);

/* o rótulo do PRD ("Hospital OS: ") se repete em toda fatia; o título
   inteiro fica no <title> do nó */
function tituloCurto(t) {
  const s = String(t || '').replace(/^[^:]{1,30}:\s*/, '');
  return s.length > MAX_TITULO ? s.slice(0, MAX_TITULO - 1).trimEnd() + '…' : s;
}

const versaoTxt = v => 'v' + String(v).replace(/^v/, '');

/* seta reta de um nó ao seguinte, no vão entre eles */
function fluxo(x1, x2, y) {
  return `<g class="onda-fluxo"><path d="M ${x1} ${y} L ${x2 - 6} ${y}"/>
    <path class="onda-ponta" d="M ${x2 - 7} ${y - 4} L ${x2} ${y} L ${x2 - 7} ${y + 4} Z"/></g>`;
}

/* bloqueio: sai por baixo da bloqueadora, desce pelo corredor da esquerda e
   entra pela lateral da bloqueada, sempre de cima para baixo (a bloqueada
   está numa onda posterior) */
function bloqueio(y1, y2, pista) {
  const x1 = X_FATIA + 16, xc = MARGEM + 4 + (pista % PISTAS) * 6, x2 = X_FATIA;
  return `M ${x1} ${y1} C ${x1} ${y1 + 22}, ${xc} ${y1 + 10}, ${xc} ${y1 + 30} L ${xc} ${y2 - 20}`
    + ` C ${xc} ${y2 - 4}, ${xc} ${y2}, ${x2 - 6} ${y2}`;
}

/* `fases` é a régua [chave, nome, badge] do app.js, para nomear a borda */
export function renderOndas(prd, dados, fases) {
  const doPayload = dados.fases || {};
  const ondas = prd.state === 'OPEN' && (doPayload.ondas || {})[prd.number];
  const porN = Object.fromEntries(((dados.github || {}).issues || []).map(i => [i.number, i]));
  const colunas = (ondas || []).map(c => c.filter(n => porN[n])).filter(c => c.length);
  if (!colunas.length) return '';

  const fasesIssue = doPayload.issues || {}, fasesPr = doPayload.prs || {};
  const faseDe = n => (fasesIssue[n] || {}).fase || '';
  const nomeDaFase = k => (fases.find(([f]) => f === k) || [k, k || 'sem fase'])[1];

  // posição de cada fatia: faixas por onda, uma linha por fatia
  const pos = new Map();
  let y = MARGEM;
  colunas.forEach((col, c) => {
    y += FAIXA;
    col.forEach(n => { pos.set(n, { y, c }); y += H + GY; });
    y += GY;
  });
  const altura = y - 2 * GY + MARGEM;
  const estagio = Math.max(...[...pos.keys()].map(n => {
    const fs = fasesIssue[n] || {};
    return fs.versao ? 2 : fs.pr ? 1 : 0;
  }));
  const largura = [X_FATIA + WF, X_PR + WP, X_VER + WV][estagio] + MARGEM;

  const faixas = colunas.map((col, c) => {
    const topo = pos.get(col[0]).y - FAIXA;
    return `${c ? `<line class="onda-faixa" x1="${X_FATIA}" y1="${topo + 4}" x2="${largura - MARGEM}" y2="${topo + 4}"/>` : ''}
      <text class="onda-col" x="${X_FATIA}" y="${topo + 16}">onda ${c + 1}</text>`;
  }).join('');

  const setas = [];
  for (const [n, p] of pos) {
    for (const b of porN[n].blocked_by || []) {
      const q = pos.get(b);
      if (!q || porN[b].state !== 'OPEN') continue;   // bloqueadora fechada ou de fora do PRD: sem seta
      const y2 = p.y + H / 2, x2 = X_FATIA;
      setas.push(`<g class="onda-seta" data-de="${b}" data-para="${n}">
        <path d="${bloqueio(q.y + H, y2, setas.length)}"/>
        <path class="onda-ponta" d="M ${x2 - 7} ${y2 - 4} L ${x2} ${y2} L ${x2 - 7} ${y2 + 4} Z"/></g>`);
    }
  }

  let idx = 0;
  const linhas = [...pos].map(([n, p]) => {
    const i = porN[n], fase = faseDe(n), fs = fasesIssue[n] || {}, ym = p.y + H / 2;
    const quem = i.assignees.length ? i.assignees.join(', ') : 'ninguém assumiu';
    const partes = [`<g class="onda-no onda-f-${esc(fase)}" data-act="onda" data-n="${n}" data-prd="${prd.number}" data-col="${p.c}" style="--pessoa:${corDaPessoa(i.assignees[0] || null)};--i:${idx++}">
      <title>#${n} ${esc(i.title)} · ${esc(nomeDaFase(fase))} · ${esc(quem)}</title>
      <rect class="onda-anel" x="${X_FATIA}" y="${p.y}" width="${WF}" height="${H}" rx="10"/>
      <circle class="onda-dot" cx="${X_FATIA + 15}" cy="${ym}" r="5"/>
      <text class="onda-num" x="${X_FATIA + 27}" y="${p.y + 17}">#${n}</text>
      <text class="onda-tit" x="${X_FATIA + 27}" y="${p.y + 32}">${esc(tituloCurto(i.title))}</text>
    </g>`];
    if (fs.pr) {
      const fp = fasesPr[fs.pr] || {}, nomePr = NOME_FASE_PR[fp.fase] || fp.fase || 'PR';
      partes.push(fluxo(X_FATIA + WF, X_PR, ym));
      partes.push(`<a class="onda-pr onda-p-${esc(fp.fase || '')}" href="${esc(montarHash({ aba: 'prs', item: String(fs.pr) }))}" data-pr="${fs.pr}" style="--i:${idx++}">
        <title>PR #${fs.pr} · ${esc(nomePr)}</title>
        <rect class="onda-pr-corpo" x="${X_PR}" y="${p.y}" width="${WP}" height="${H}" rx="10"/>
        <text class="onda-num" x="${X_PR + 12}" y="${p.y + 17}">PR #${fs.pr}</text>
        <text class="onda-tit" x="${X_PR + 12}" y="${p.y + 32}">${esc(nomePr)}</text>
      </a>`);
    }
    if (fs.versao) {
      const v = versaoTxt(fs.versao);
      partes.push(fluxo(X_PR + WP, X_VER, ym));
      partes.push(`<a class="onda-ver" href="${esc(montarHash({ aba: 'producao', item: v }))}" data-versao="${esc(v)}" style="--i:${idx++}">
        <title>em produção na ${esc(v)}</title>
        <rect class="onda-ver-corpo" x="${X_VER}" y="${p.y}" width="${WV}" height="${H}" rx="10"/>
        <text class="onda-num" x="${X_VER + WV / 2}" y="${ym + 4}" text-anchor="middle">${esc(v)}</text>
      </a>`);
    }
    return partes.join('');
  }).join('');

  const pessoas = [...new Set([...pos.keys()].map(n => porN[n].assignees[0] || null))];
  const fasesVistas = [...new Set([...pos.keys()].map(faseDe))];
  const legenda = pessoas.map(l =>
    `<span class="pessoa" style="--pessoa:${corDaPessoa(l)}"><span class="pessoa-dot"></span>${l ? esc(l) : 'ninguém assumiu'}</span>`)
    .concat(fasesVistas.map(f => `<span class="onda-leg onda-f-${esc(f)}">${esc(nomeDaFase(f))}</span>`)).join('');

  return `
  <div class="ondas">
    <div class="k-label">fluxo do PRD · bolinha é quem assumiu, borda é a fase, seta à esquerda é quem bloqueia quem · fatia → PR → versão</div>
    <div class="ondas-canvas">
      <svg class="onda-svg${reduceMotion() ? '' : ' onda-anima'}" width="${largura}" viewBox="0 0 ${largura} ${altura}" role="group"
        aria-label="Ondas do PRD #${prd.number}: ${colunas.length} ondas, ${pos.size} fatias">
        ${faixas}<g class="onda-setas">${setas.join('')}</g>${linhas}
      </svg>
    </div>
    <div class="ondas-legenda">${legenda}</div>
  </div>`;
}
