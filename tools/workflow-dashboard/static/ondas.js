'use strict';

/* Desenho das ondas no card do PRD aberto (issue #943, ADR 0062, decisão 3),
   renderer próprio em SVG (ADR 0025, sem biblioteca). Colunas = ondas do
   payload `fases.ondas` (quem calcula é o fases.py, aqui só se desenha); nó =
   fatia, preenchido na cor de quem assumiu e com o anel na cor da fase; seta =
   `blocked_by` aberto entre fatias do mesmo PRD. Clicar no nó abre o card da
   fatia: o data-act "onda" borbulha até o handler delegado do app.js.
   Só tokens do :root; com reduceMotion o desenho nasce parado. */

import { esc, reduceMotion } from './ui.js';
import { corDaPessoa } from './pessoas.js';

const W = 148, H = 42;       // nó
const GX = 56, GY = 20;      // vão entre colunas (onde correm as setas) e entre nós
const ANEL = 4;              // folga do anel da fase em volta do nó
const TOPO = 26, MARGEM = 8; // faixa dos rótulos das colunas e borda do desenho
const MAX_TITULO = 21;

/* seta de uma coluna para a seguinte: um S no vão. Pulando colunas, ela
   desce (ou sobe) no primeiro vão até a faixa livre entre duas linhas de nós
   mais perto do meio do caminho, corre por ela e só sobe no último vão: assim
   não passa por baixo de um nó do meio, que parece ser a origem da seta. */
function caminho(x1, y1, x2, y2, linhas) {
  if (x2 - x1 <= GX) {
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 6} ${y2}`;
  }
  const g = GX / 2 - ANEL, topo = TOPO + ANEL - GY / 2;
  const k = Math.min(linhas, Math.max(0, Math.round(((y1 + y2) / 2 - topo) / (H + GY))));
  const yf = topo + k * (H + GY);
  return `M ${x1} ${y1} C ${x1 + g / 2} ${y1}, ${x1 + g / 2} ${yf}, ${x1 + g} ${yf} L ${x2 - g} ${yf}`
    + ` C ${x2 - g / 2} ${yf}, ${x2 - g / 2} ${y2}, ${x2 - 6} ${y2}`;
}

/* o rótulo do PRD ("Hospital OS: ") se repete em toda fatia; o título
   inteiro fica no <title> do nó */
function tituloCurto(t) {
  const s = String(t || '').replace(/^[^:]{1,30}:\s*/, '');
  return s.length > MAX_TITULO ? s.slice(0, MAX_TITULO - 1).trimEnd() + '…' : s;
}

/* `fases` é a régua [chave, nome, badge] do app.js, para nomear a borda */
export function renderOndas(prd, dados, fases) {
  const doPayload = (dados.fases || {});
  const ondas = prd.state === 'OPEN' && (doPayload.ondas || {})[prd.number];
  const porN = Object.fromEntries(((dados.github || {}).issues || []).map(i => [i.number, i]));
  const colunas = (ondas || []).map(c => c.filter(n => porN[n])).filter(c => c.length);
  if (!colunas.length) return '';

  const faseDe = n => ((doPayload.issues || {})[n] || {}).fase || '';
  const nomeDaFase = k => (fases.find(([f]) => f === k) || [k, k || 'sem fase'])[1];
  const pos = new Map();
  colunas.forEach((col, c) => col.forEach((n, r) => pos.set(n, {
    x: MARGEM + ANEL + c * (W + GX), y: TOPO + ANEL + r * (H + GY), c,
  })));
  const linhas = Math.max(...colunas.map(c => c.length));
  const largura = 2 * (MARGEM + ANEL) + colunas.length * W + (colunas.length - 1) * GX;
  const altura = TOPO + 2 * ANEL + MARGEM + linhas * (H + GY) - GY;

  const rotulos = colunas.map((_, c) =>
    `<text class="onda-col" x="${MARGEM + ANEL + c * (W + GX) + W / 2}" y="14">onda ${c + 1}</text>`).join('');

  const setas = [];
  for (const [n, p] of pos) {
    for (const b of porN[n].blocked_by || []) {
      const q = pos.get(b);
      if (!q || porN[b].state !== 'OPEN') continue;   // bloqueadora fechada ou de fora do PRD: sem seta
      const x1 = q.x + W + ANEL, y1 = q.y + H / 2, x2 = p.x - ANEL, y2 = p.y + H / 2;
      setas.push(`<g class="onda-seta" data-de="${b}" data-para="${n}">
        <path d="${caminho(x1, y1, x2, y2, linhas)}"/>
        <path class="onda-ponta" d="M ${x2 - 7} ${y2 - 4} L ${x2} ${y2} L ${x2 - 7} ${y2 + 4} Z"/></g>`);
    }
  }

  let idx = 0;
  const nos = [...pos].map(([n, p]) => {
    const i = porN[n], fase = faseDe(n);
    const quem = i.assignees.length ? i.assignees.join(', ') : 'ninguém assumiu';
    return `<g class="onda-no onda-f-${esc(fase)}" data-act="onda" data-n="${n}" data-prd="${prd.number}" data-col="${p.c}" style="--pessoa:${corDaPessoa(i.assignees[0] || null)};--i:${idx++}">
      <title>#${n} ${esc(i.title)} · ${esc(nomeDaFase(fase))} · ${esc(quem)}</title>
      <rect class="onda-anel" x="${p.x - ANEL}" y="${p.y - ANEL}" width="${W + 2 * ANEL}" height="${H + 2 * ANEL}" rx="13"/>
      <rect class="onda-corpo" x="${p.x}" y="${p.y}" width="${W}" height="${H}" rx="10"/>
      <text class="onda-num" x="${p.x + 10}" y="${p.y + 17}">#${n}</text>
      <text class="onda-tit" x="${p.x + 10}" y="${p.y + 32}">${esc(tituloCurto(i.title))}</text>
    </g>`;
  }).join('');

  const pessoas = [...new Set([...pos.keys()].map(n => porN[n].assignees[0] || null))];
  const fasesVistas = [...new Set([...pos.keys()].map(faseDe))];
  const legenda = pessoas.map(l =>
    `<span class="pessoa" style="--pessoa:${corDaPessoa(l)}"><span class="pessoa-dot"></span>${l ? esc(l) : 'ninguém assumiu'}</span>`)
    .concat(fasesVistas.map(f => `<span class="onda-leg onda-f-${esc(f)}">${esc(nomeDaFase(f))}</span>`)).join('');

  return `
  <div class="ondas">
    <div class="k-label">ondas · a cor é quem assumiu, a borda é a fase · clique abre a fatia</div>
    <div class="ondas-canvas">
      <svg class="onda-svg${reduceMotion() ? '' : ' onda-anima'}" width="${largura}" viewBox="0 0 ${largura} ${altura}" role="group"
        aria-label="Ondas do PRD #${prd.number}: ${colunas.length} ondas, ${pos.size} fatias">
        ${rotulos}<g class="onda-setas">${setas.join('')}</g>${nos}
      </svg>
    </div>
    <div class="ondas-legenda">${legenda}</div>
  </div>`;
}
