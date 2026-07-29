'use strict';

/* Renderers próprios de diagrama em SVG (ADR 0025): zero lib, zero CDN.

   Interface única por tipo: renderDiagrama(diag) devolve o HTML do desenho,
   ou null quando o tipo ainda não tem renderer (o chamador mantém o fallback
   de código cru). Depois que o HTML entra no DOM, wireDiagramas(root) liga a
   interatividade. As fatias seguintes do PRD #212 registram novos tipos em
   RENDERERS sem tocar nos chamadores. */

import { esc, reduceMotion } from './ui.js';
import { TABELAS } from './content/tabelas.js';

/* ---------- ER: clusters por domínio ---------- */

/* mapeamento curado tabela → domínio; pops* cai em POPs por prefixo;
   tabela desconhecida (ex.: recém-criada no schema) cai em Outras */
const DOMINIO_DE = {
  participantes: 'Pessoas', cargos: 'Pessoas', user_preferences: 'Pessoas',
  reunioes: 'Reuniões', reuniao_participantes: 'Reuniões', tipos_reuniao: 'Reuniões',
  pendencias: 'Reuniões', comentarios_pendencias: 'Reuniões',
  agendamentos_email: 'Reuniões', tokens_validacao: 'Reuniões',
  audit_log: 'Infra', bulk_jobs: 'Infra', notificacoes: 'Infra',
};
const DOMINIOS = ['Pessoas', 'Reuniões', 'POPs', 'Infra', 'Outras'];
export const COR_DOMINIO = {
  Pessoas: 'var(--indigo)', 'Reuniões': 'var(--coral)', POPs: 'var(--green)',
  Infra: 'var(--amber)', Outras: 'var(--purple)',
};
export const dominioDe = t => (Object.hasOwn(DOMINIO_DE, t) ? DOMINIO_DE[t]
  : t === 'pops' || t.startsWith('pops_') ? 'POPs' : 'Outras');

/* layout fechado, sem motor de grafo: cards de largura única e altura
   variável (todas as colunas aparentes, issue #255) em masonry de 2 colunas
   dentro de cada cluster; clusters em 2 colunas (sempre a mais curta). O
   desenho tem tamanho natural: a página rola por ele, sem zoom/pan. Dentro
   do cluster as tabelas mais conectadas vêm primeiro (os hubs saltam ao olho). */
const CW = 300;                   // largura do card
const RH = 19;                    // altura da linha de coluna
const GX = 16, GY = 14;           // gap entre cards
const PAD = 16, HEAD = 34;        // respiro interno e cabeçalho do cluster
const GCX = 48, GCY = 40;         // gap entre clusters
const CLW = 2 * CW + GX + 2 * PAD;
const CARD_HEAD = 30;             // faixa do nome da tabela
const VLH = 13;                   // linha do verbete
const SEP = 9;                    // respiro do separador até a primeira coluna

const corta = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/* quebra o verbete em até maxLinhas pela contagem de caracteres (~5.2px por
   caractere na fonte de 10px); o que não couber encerra em reticências */
function clampaVerbete(texto, porLinha = 56, maxLinhas = 2) {
  const palavras = String(texto).split(/\s+/).filter(Boolean);
  const linhas = [];
  let atual = '';
  let sobrou = false;
  for (const p of palavras) {
    const cand = atual ? `${atual} ${p}` : p;
    if (cand.length <= porLinha) { atual = cand; continue; }
    if (linhas.length + 1 === maxLinhas) { sobrou = true; break; }
    linhas.push(atual || p.slice(0, porLinha));
    atual = atual ? p : '';
  }
  if (atual) linhas.push(atual);
  if (sobrou) linhas[linhas.length - 1] = corta(linhas[linhas.length - 1], porLinha - 1);
  return linhas;
}

/* geometria do card: verbete clampado + uma linha por coluna (+extras) */
function cardGeo(t) {
  const cur = TABELAS[t.nome] || {};
  const verbete = clampaVerbete(cur.resumo || 'sem verbete funcional ainda (tabelas.js)');
  const nLinhas = Math.max(t.colunas.length + (t.extras ? 1 : 0), 1);
  const yCols = CARD_HEAD + verbete.length * VLH + SEP;
  return { verbete, semVerbete: !cur.resumo, yCols, h: yCols + nLinhas * RH + 10 };
}

function erLayout(diag) {
  const tabelas = diag.tabelas || [];
  if (!tabelas.length) return null;

  const grau = Object.create(null);
  (diag.relacoes || []).forEach(r => {
    grau[r.origem] = (grau[r.origem] || 0) + 1;
    grau[r.destino] = (grau[r.destino] || 0) + 1;
  });
  const grupos = new Map(DOMINIOS.map(d => [d, []]));
  tabelas.forEach(t => grupos.get(dominioDe(t.nome)).push(t));
  grupos.forEach(ts => ts.sort((a, b) => (grau[b.nome] || 0) - (grau[a.nome] || 0)));

  const colY = [0, 0];
  const clusters = [];
  const pos = Object.create(null);   // sem prototype: tabela "__proto__" vira chave comum
  let seq = 0;
  for (const nome of DOMINIOS) {
    const ts = grupos.get(nome);
    if (!ts.length) continue;
    // masonry: cada card cai na coluna interna mais curta, na ordem dos hubs
    const alt = [0, 0];
    const locais = ts.map(t => {
      const geo = cardGeo(t);
      const c = alt[0] <= alt[1] ? 0 : 1;
      const local = { t, geo, cx: c, cy: alt[c] };
      alt[c] += geo.h + GY;
      return local;
    });
    const alto = HEAD + 2 * PAD + Math.max(alt[0], alt[1]) - GY;
    const col = colY[0] <= colY[1] ? 0 : 1;
    const x = col * (CLW + GCX), y = colY[col];
    colY[col] += alto + GCY;
    clusters.push({ nome, x, y, w: CLW, h: alto, n: ts.length });
    locais.forEach(l => {
      pos[l.t.nome] = {
        t: l.t,
        geo: l.geo,
        x: x + PAD + l.cx * (CW + GX),
        y: y + HEAD + PAD + l.cy,
        i: seq++,
      };
    });
  }
  const W = 2 * CLW + GCX;
  const H = Math.max(colY[0], colY[1]) - GCY;
  return { clusters, pos, W, H };
}

/* uma linha por coluna: badge PK/FK + nome + tipo (FK mostra o destino no
   lugar do tipo); opcionais (sem NOT NULL) esmaecidas. A linha FK carrega um
   rect de hit pro hover acender a aresta específica (wireErMapa). */
function colunaSvg(c, y) {
  const badge = c.pk ? `<text class="er-k er-k-pk" x="12" y="${y + 13}">PK</text>`
    : c.fk ? `<text class="er-k er-k-fk" x="12" y="${y + 13}">FK</text>` : '';
  const dest = c.fk && c.fk_ref ? String(c.fk_ref).split('.')[0] : '';
  const dir = dest
    ? `<text class="er-col-dest" x="${CW - 12}" y="${y + 13}">→ ${esc(corta(String(c.fk_ref).replace(/\.id$/, ''), 22))}</text>`
    : `<text class="er-col-tipo" x="${CW - 12}" y="${y + 13}">${esc(corta(c.tipo || '', 18))}</text>`;
  const cls = ['er-col', dest ? 'er-col-fk' : '', c.pk || c.nn ? '' : 'opcional'].filter(Boolean).join(' ');
  return `<g class="${cls}" data-col="${esc(c.nome)}"${c.pk ? ' data-pk="1"' : ''}${dest ? ` data-dest="${esc(dest)}"` : ''}>
      <rect class="er-col-hit" x="6" y="${y}" width="${CW - 12}" height="${RH}" rx="5"/>
      ${badge}<text class="er-col-nome" x="34" y="${y + 13}">${esc(corta(c.nome, 26))}</text>${dir}
    </g>`;
}

function cardSvg(p) {
  const t = p.t, g = p.geo;
  const cor = COR_DOMINIO[dominioDe(t.nome)];
  const linhas = t.colunas.map((c, i) => colunaSvg(c, g.yCols + i * RH));
  if (t.extras) {
    linhas.push(`<text class="er-col-extra" x="12" y="${g.yCols + t.colunas.length * RH + 13}">+${t.extras} colunas resumidas no snapshot</text>`);
  } else if (!t.colunas.length) {
    linhas.push(`<text class="er-col-extra" x="12" y="${g.yCols + 13}">colunas fora do snapshot</text>`);
  }
  const verbete = g.verbete.map((l, i) =>
    `<text class="er-tab-verbete${g.semVerbete ? ' er-sem-verbete' : ''}" x="12" y="${CARD_HEAD + 8 + i * VLH}">${esc(l)}</text>`).join('');
  return `<g class="er-tab" data-t="${esc(t.nome)}" tabindex="0" role="group"
    aria-label="Tabela ${esc(t.nome)}: ${t.colunas.length + (t.extras || 0)} colunas"
    transform="translate(${p.x} ${p.y})" style="--i:${Math.min(p.i, 12)}"><g class="er-tab-lift">
    <rect class="er-tab-fundo" x="0" y="0" width="${CW}" height="${g.h}" rx="10"/>
    <rect class="er-tab-bar" x="0" y="7" width="3" height="${g.h - 14}" rx="1.5" style="fill:${cor}"/>
    <text class="er-tab-nome" data-act="ficha" data-t="${esc(t.nome)}" x="12" y="21">${esc(t.nome)}</text>
    ${verbete}
    <line class="er-tab-sep" x1="12" y1="${g.yCols - 5}" x2="${CW - 12}" y2="${g.yCols - 5}"/>
    ${linhas.join('')}
  </g></g>`;
}

function erMiolo(diag) {
  const L = erLayout(diag);
  if (!L) return null;
  const { clusters, pos, W, H } = L;
  const relacoes = diag.relacoes || [];

  /* arestas: bezier entre bordas dos cards, sem rótulo (a coluna FK já está
     aparente no card, issue #255). No filho a âncora é a própria linha da
     coluna FK; no pai, a faixa do cabeçalho (com leque quando várias saem
     pela mesma borda). Na mesma prumada, arco pelo lado externo. */
  const planos = relacoes.map(r => {
    const a = pos[r.origem], b = pos[r.destino];
    if (!a || !b) return null;
    const dx = (b.x + CW / 2) - (a.x + CW / 2);
    let ladoA, ladoB;
    if (Math.abs(dx) > CW) { ladoA = dx > 0 ? 1 : -1; ladoB = -ladoA; }
    else { ladoA = ladoB = (a.x + CW / 2) <= W / 2 ? -1 : 1; }
    const idx = b.t.colunas.findIndex(c => c.nome === r.rotulo);
    const y2 = idx >= 0 ? b.y + b.geo.yCols + idx * RH + RH / 2 : b.y + 16;
    return { r, a, b, ladoA, ladoB, y2 };
  }).filter(Boolean);

  const totalAncora = {}, vistoAncora = {};
  planos.forEach(p => {
    const k = `${p.r.origem}|${p.ladoA}`;
    totalAncora[k] = (totalAncora[k] || 0) + 1;
  });

  let minX = 0, maxX = W;   // arcos laterais podem sair do retângulo dos clusters
  const arestas = [];
  planos.forEach(p => {
    const k = `${p.r.origem}|${p.ladoA}`;
    const i = vistoAncora[k] = (vistoAncora[k] || 0) + 1;
    const y1 = p.a.y + 16 + (i - (totalAncora[k] + 1) / 2) * 7;
    const x1 = p.a.x + (p.ladoA > 0 ? CW : 0);
    const x2 = p.b.x + (p.ladoB > 0 ? CW : 0);
    const y2 = p.y2;
    let c1x, c2x;
    if (p.ladoA !== p.ladoB) { c1x = c2x = (x1 + x2) / 2; }
    else {
      const arco = p.ladoA * (30 + Math.min(Math.abs(y2 - y1) * 0.1, 46));
      c1x = x1 + arco; c2x = x2 + arco;
      minX = Math.min(minX, x1 + arco, x2 + arco);
      maxX = Math.max(maxX, x1 + arco, x2 + arco);
    }
    const f = n => n.toFixed(1);
    arestas.push(`<g class="er-rel" data-a="${esc(p.r.origem)}" data-b="${esc(p.r.destino)}" data-col="${esc(p.r.rotulo)}">
      <path class="er-edge" d="M ${f(x1)} ${f(y1)} C ${f(c1x)} ${f(y1)}, ${f(c2x)} ${f(y2)}, ${f(x2)} ${f(y2)}"/>
      <circle class="er-edge-pt" cx="${f(x2)}" cy="${f(y2)}" r="3.2"/>
    </g>`);
  });

  const caixas = clusters.map(c => `
    <g class="er-cluster">
      <rect x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="14"/>
      <text x="${c.x + PAD}" y="${c.y + 20}" style="fill:${COR_DOMINIO[c.nome]}">${esc(c.nome.toUpperCase())} · ${c.n}</text>
    </g>`).join('');

  const cards = Object.values(pos).map(cardSvg).join('');

  const vx = Math.floor(minX) - 8, vw = Math.ceil(maxX) - vx + 8;
  return `<svg class="er-svg" viewBox="${vx} -8 ${vw} ${H + 16}"
    role="group" aria-label="Diagrama do banco de dados: tabelas agrupadas por domínio, todas as colunas aparentes">
    ${caixas}<g class="er-arestas">${arestas.join('')}</g>${cards}
  </svg>`;
}

/* o desenho não guarda estado vivo: sem zoom/pan nem popover (issue #255),
   o re-render do auto-refresh redesenha idêntico e o wrapper só serve pra
   rolagem interna da tela cheia */
function erSvg(diag) {
  const svg = erMiolo(diag);
  if (!svg) return null;
  return `<div class="er-canvas">${svg}</div>`;
}

/* ---------- Sequência: lifelines em colunas + play ---------- */

/* layout trivialmente determinístico (ADR 0025): cada participante é uma
   coluna de largura única (dimensionada pelo nome mais longo), cada mensagem
   é uma linha horizontal em ordem, descendo as lifelines. Rótulo com halo da
   cor do card segue legível cruzando lifelines; o viewBox alarga pros rótulos
   que passam da primeira/última coluna. */
const SQ_TOP = 8, SQ_HEAD = 30, SQ_GAP = 26;   // topo, cabeçalho, respiro até a 1a mensagem
const SQ_ROW = 34;                             // altura de cada mensagem
const SQ_LOOP = 30;                            // largura do laço da auto-mensagem

function seqSvg(diag) {
  const parts = diag.participantes || [];
  const msgs = diag.mensagens || [];
  if (!parts.length || !msgs.length) return null;

  const maxNome = Math.max(...parts.map(p => String(p.nome || p.id).length));
  const colW = Math.max(150, Math.round(maxNome * 6.8) + 26);
  const cx = Object.create(null);
  parts.forEach((p, i) => { cx[p.id] = i * colW + colW / 2; });

  const y0 = SQ_TOP + SQ_HEAD + SQ_GAP;
  const W = parts.length * colW;
  const H = y0 + msgs.length * SQ_ROW + 10;
  let minX = 0, maxX = W;

  const linhas = msgs.map((m, i) => {
    const y = y0 + i * SQ_ROW;
    const texto = esc(m.texto);
    const dash = m.seta === '-->>' ? ' seq-tracejada' : '';
    const abre = `<g class="seq-msg${dash}" data-de="${esc(m.de)}" data-para="${esc(m.para)}">`;
    if (m.de === m.para) {           // auto-mensagem: laço à direita da própria lifeline
      const x = cx[m.de], lx = x + SQ_LOOP + 8;
      maxX = Math.max(maxX, lx + m.texto.length * 6.2 + 8);
      return `${abre}
        <path class="seq-linha" d="M ${x} ${y} h ${SQ_LOOP} v 13 h ${-SQ_LOOP}"/>
        <path class="seq-ponta" d="M ${x + 8} ${y + 8.5} L ${x} ${y + 13} l 8 4.5"/>
        <text class="seq-txt seq-txt-auto" x="${lx}" y="${y + 4}">${texto}</text>
      </g>`;
    }
    const x1 = cx[m.de], x2 = cx[m.para], dir = x2 > x1 ? 1 : -1;
    const mid = (x1 + x2) / 2, meio = m.texto.length * 3.1;   // ~6.2px/caractere na fonte de 10px
    minX = Math.min(minX, mid - meio);
    maxX = Math.max(maxX, mid + meio);
    return `${abre}
      <path class="seq-linha" d="M ${x1} ${y} H ${x2}"/>
      <path class="seq-ponta" d="M ${x2 - dir * 9} ${y - 4.5} L ${x2} ${y} L ${x2 - dir * 9} ${y + 4.5}"/>
      <text class="seq-txt" x="${mid}" y="${y - 6}">${texto}</text>
    </g>`;
  });

  const colunas = parts.map(p => `
    <g class="seq-part" data-p="${esc(p.id)}">
      <line class="seq-life" x1="${cx[p.id]}" y1="${SQ_TOP + SQ_HEAD}" x2="${cx[p.id]}" y2="${H - 4}"/>
      <rect x="${cx[p.id] - (colW - 18) / 2}" y="${SQ_TOP}" width="${colW - 18}" height="${SQ_HEAD}" rx="9"/>
      <text x="${cx[p.id]}" y="${SQ_TOP + 19}">${esc(p.nome || p.id)}</text>
    </g>`).join('');

  const vx = Math.floor(minX) - 8, vw = Math.ceil(maxX) - vx + 8;
  return `<div class="seq-box">
    <div class="seq-controles">
      <button type="button" class="fchip seq-bt" data-seq="play">play</button>
      <button type="button" class="fchip seq-bt" data-seq="reset">reiniciar</button>
      <span class="seq-passo">${msgs.length} mensagens</span>
    </div>
    <svg class="seq-svg" viewBox="${vx} 0 ${vw} ${H}" role="img"
      aria-label="Diagrama de sequência: ${parts.length} participantes trocando ${msgs.length} mensagens">
      ${colunas}${linhas.join('')}
    </svg>
  </div>`;
}

/* play: percorre as mensagens em ordem destacando origem, destino e texto;
   pausa e reinício simples. Com reduceMotion não há timer: o mesmo botão
   avança um passo por clique (as transições o CSS global já zera). */
function wireSeq(box) {
  const svg = box.querySelector('.seq-svg');
  const msgs = [...box.querySelectorAll('.seq-msg')];
  const parts = [...box.querySelectorAll('.seq-part')];
  const btPlay = box.querySelector('[data-seq="play"]');
  const btReset = box.querySelector('[data-seq="reset"]');
  const passo = box.querySelector('.seq-passo');
  const total = msgs.length;
  if (!svg || !btPlay || !btReset || !total) return;
  let i = -1, timer = null;

  const rotuloParado = () => reduceMotion() ? 'próxima' : 'play';
  const pinta = () => {
    svg.classList.toggle('seq-run', i >= 0);
    msgs.forEach((m, j) => {
      m.classList.toggle('on', j === i);
      m.classList.toggle('feita', j < i);
    });
    const acesos = i >= 0 ? [msgs[i].dataset.de, msgs[i].dataset.para] : [];
    parts.forEach(p => p.classList.toggle('on', acesos.includes(p.dataset.p)));
    passo.textContent = i >= 0 ? `mensagem ${i + 1} de ${total}` : `${total} mensagens`;
  };
  const pausa = () => {
    if (timer) clearInterval(timer);
    timer = null;
    btPlay.textContent = rotuloParado();
  };
  const avanca = () => {
    if (!box.isConnected) { pausa(); return; }   // re-render trocou o DOM: timer morre junto
    i = Math.min(i + 1, total - 1);
    pinta();
    if (i >= total - 1) pausa();
  };

  btPlay.textContent = rotuloParado();
  btPlay.addEventListener('click', () => {
    if (timer) { pausa(); return; }
    if (i >= total - 1) i = -1;              // terminou: tocar de novo recomeça
    if (reduceMotion()) { avanca(); return; }
    timer = setInterval(avanca, 1300);
    btPlay.textContent = 'pausar';
    avanca();
  });
  btReset.addEventListener('click', () => { pausa(); i = -1; pinta(); });
}

/* ---------- Máquina de estados: espinha do caminho feliz ---------- */

/* layout fechado (ADR 0025), sem motor de grafo: a espinha do caminho feliz
   desce na vertical (menor caminho do estado inicial ao final principal, BFS
   na ordem de declaração das transições) e os desvios ficam pendurados na
   coluna da direita, na altura média dos estados da espinha que os alcançam;
   retornos em curva. O gatilho de cada transição aparece no hover. */
const NW = 196, NH = 42;     // nó (estado)
const VS = 104;              // passo vertical da espinha
const LGX = 190;             // vão entre a espinha e a coluna de desvios
const MR = 7;                // raio dos marcadores [*]

/* ponto da bezier cúbica em t (por eixo) */
const bezPt = (t, p0, p1, p2, p3) => {
  const u = 1 - t;
  return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
};

function estadoSvg(diag) {
  const estados = diag.estados || [];
  const trans = diag.transicoes || [];
  const inicial = trans.find(t => t.origem === '[*]' && t.destino !== '[*]');
  const finais = trans.filter(t => t.destino === '[*]').map(t => t.origem);
  if (!estados.length || !inicial || !finais.length) return null;

  /* espinha: menor caminho do estado inicial ao final principal (o primeiro
     `X --> [*]` declarado), BFS visitando na ordem de declaração */
  const adj = new Map(estados.map(n => [n, []]));
  trans.forEach(t => { if (adj.has(t.origem) && adj.has(t.destino)) adj.get(t.origem).push(t.destino); });
  const alvo = finais[0];
  const pai = new Map([[inicial.destino, null]]);
  const fila = [inicial.destino];
  while (fila.length && !pai.has(alvo)) {
    const n = fila.shift();
    for (const v of adj.get(n)) if (!pai.has(v)) { pai.set(v, n); fila.push(v); }
  }
  if (!pai.has(alvo)) return null;
  const espinha = [];
  for (let n = alvo; n != null; n = pai.get(n)) espinha.unshift(n);
  const idxE = new Map(espinha.map((n, i) => [n, i]));

  /* desvios: âncora na altura média dos estados da espinha ligados a eles,
     empilhados de cima pra baixo sem sobreposição */
  const laterais = estados.filter(n => !idxE.has(n));
  const anc = new Map(laterais.map(n => {
    const viz = trans
      .filter(t => t.origem === n || t.destino === n)
      .map(t => (t.origem === n ? t.destino : t.origem))
      .filter(v => idxE.has(v)).map(v => idxE.get(v));
    return [n, viz.length ? viz.reduce((s, i) => s + i, 0) / viz.length : (espinha.length - 1) / 2];
  }));
  laterais.sort((a, b) => anc.get(a) - anc.get(b));

  const sx = NW / 2 + 8;               // centro x da espinha
  const lx = sx + NW + LGX;            // centro x dos desvios
  const yIni = MR + 2;                 // centro do marcador inicial
  const y0 = yIni + MR + 26;           // topo do primeiro estado
  const pos = new Map();               // nome do estado -> {x do centro, y do topo}
  espinha.forEach((n, i) => pos.set(n, { x: sx, y: y0 + i * VS }));
  let yL = -Infinity;
  laterais.forEach(n => {
    yL = Math.max(y0 + anc.get(n) * VS, yL + NH + 22);
    pos.set(n, { x: lx, y: yL });
  });
  const yFim = y0 + (espinha.length - 1) * VS + NH + 44;   // centro do marcador final

  /* transições do caminho feliz: [*] -> espinha ... espinha -> [*] */
  const achar = (o, d) => trans.findIndex(t => t.origem === o && t.destino === d);
  const feliz = new Set([trans.indexOf(inicial), achar(alvo, '[*]')]);
  for (let i = 0; i + 1 < espinha.length; i++) feliz.add(achar(espinha[i], espinha[i + 1]));

  /* âncoras laterais em leque (mesma ideia do ER) pra arestas não nascerem
     umas em cima das outras; feliz usa topo/base, que só a espinha ocupa */
  const planos = trans.map((t, i) => {
    if (feliz.has(i)) return { t, i, modo: 'reta' };
    const oE = idxE.has(t.origem), dE = idxE.has(t.destino);
    if (t.destino === '[*]') return oE ? { t, i, modo: 'arcoE', l1: -1, l2: -1 } : { t, i, modo: 's', l1: -1, l2: 1 };
    if (t.origem === '[*]') return { t, i, modo: 's', l1: 1, l2: -1 };
    if (oE && dE) return { t, i, modo: 'arcoE', l1: -1, l2: -1 };
    if (!oE && !dE) return { t, i, modo: 'arcoD', l1: 1, l2: 1 };
    return oE ? { t, i, modo: 's', l1: 1, l2: -1 } : { t, i, modo: 's', l1: -1, l2: 1 };
  });
  /* os marcadores [*] têm nome próprio na contagem ('[*]i' inicial, '[*]f' final)
     pra âncora contada e âncora usada baterem na mesma chave */
  const chave = (n, lado) => `${n}|${lado}`;
  const nomeAnc = (n, origem) => (n === '[*]' ? (origem ? '[*]i' : '[*]f') : n);
  const totalAnc = {}, vistoAnc = {};
  planos.forEach(p => {
    if (p.modo === 'reta') return;
    const ko = chave(nomeAnc(p.t.origem, true), p.l1), kd = chave(nomeAnc(p.t.destino, false), p.l2);
    totalAnc[ko] = (totalAnc[ko] || 0) + 1;
    totalAnc[kd] = (totalAnc[kd] || 0) + 1;
  });
  const yAnc = (n, lado, base) => {
    const k = chave(n, lado);
    const i = vistoAnc[k] = (vistoAnc[k] || 0) + 1;
    const total = totalAnc[k];
    return base + (i - (total + 1) / 2) * Math.min(9, (NH - 10) / total);
  };
  /* ponta de uma transição: nó (lado esquerdo/direito) ou marcador [*] */
  const ponta = (n, lado, origem) => {
    if (n === '[*]') {
      return origem
        ? { x: sx + lado * MR, y: yAnc('[*]i', lado, yIni) }
        : { x: sx + lado * MR, y: yAnc('[*]f', lado, yFim) };
    }
    const p = pos.get(n);
    return { x: p.x + lado * (NW / 2), y: yAnc(n, lado, p.y + NH / 2) };
  };

  const f = n => n.toFixed(1);
  let minX = 0, maxX = lx + NW / 2;
  const arestas = [], rotulos = [];
  planos.forEach(p => {
    const { t, i } = p;
    let p1, p2, c1, c2;
    if (p.modo === 'reta') {
      const a = pos.get(t.origem), b = pos.get(t.destino);
      p1 = t.origem === '[*]' ? { x: sx, y: yIni + MR } : { x: a.x, y: a.y + NH };
      p2 = t.destino === '[*]' ? { x: sx, y: yFim - MR } : { x: b.x, y: b.y };
      c1 = { x: p1.x, y: (2 * p1.y + p2.y) / 3 };
      c2 = { x: p1.x, y: (p1.y + 2 * p2.y) / 3 };
    } else {
      p1 = ponta(t.origem, p.l1, true);
      p2 = ponta(t.destino, p.l2, false);
      if (p.modo === 's') {
        const mx = (p1.x + p2.x) / 2;
        c1 = { x: mx, y: p1.y };
        c2 = { x: mx, y: p2.y };
      } else {
        const arco = (p.modo === 'arcoE' ? -1 : 1) * (34 + Math.min(Math.abs(p2.y - p1.y) * 0.15, 60));
        c1 = { x: p1.x + arco, y: p1.y };
        c2 = { x: p2.x + arco, y: p2.y };
      }
    }
    const d = `M ${f(p1.x)} ${f(p1.y)} C ${f(c1.x)} ${f(c1.y)}, ${f(c2.x)} ${f(c2.y)}, ${f(p2.x)} ${f(p2.y)}`;
    const ang = Math.atan2(p2.y - c2.y, p2.x - c2.x) * 180 / Math.PI;
    // a bezier fica dentro do casco dos 4 pontos: extremo horizontal exato, sem
    // amostrar (arcos estufam além de t=0.5 e vazariam do viewBox)
    minX = Math.min(minX, p1.x, c1.x, c2.x, p2.x);
    maxX = Math.max(maxX, p1.x, c1.x, c2.x, p2.x);
    arestas.push(`<g class="st-rel${feliz.has(i) ? ' feliz' : ''}" data-i="${i}" tabindex="0"
      aria-label="${esc(t.origem)} para ${esc(t.destino)}${t.rotulo ? ': ' + esc(t.rotulo) : ''}">
      <path class="st-hit" d="${d}"/>
      <path class="st-edge" d="${d}"/>
      <path class="st-seta" transform="translate(${f(p2.x)} ${f(p2.y)}) rotate(${f(ang)})" d="M 0 0 L -7.5 -3.6 L -7.5 3.6 Z"/>
    </g>`);
    if (t.rotulo) {
      const lxr = bezPt(0.5, p1.x, c1.x, c2.x, p2.x);
      const lyr = bezPt(0.5, p1.y, c1.y, c2.y, p2.y);
      minX = Math.min(minX, lxr - t.rotulo.length * 3.3);
      maxX = Math.max(maxX, lxr + t.rotulo.length * 3.3);
      rotulos.push(`<text class="st-rotulo" data-i="${i}" x="${f(lxr)}" y="${f(lyr - 7)}">${esc(t.rotulo)}</text>`);
    }
  });

  const nos = estados.map((n, i) => {
    const p = pos.get(n);
    return `<g class="st-no ${idxE.has(n) ? 'st-no-feliz' : 'st-no-desvio'}" data-e="${esc(n)}" style="--i:${Math.min(i, 12)}">
      <rect x="${f(p.x - NW / 2)}" y="${f(p.y)}" width="${NW}" height="${NH}" rx="10"/>
      <text x="${f(p.x)}" y="${f(p.y + NH / 2 + 4)}">${esc(n)}</text>
    </g>`;
  }).join('');

  const marcadores = `
    <circle class="st-dot" cx="${f(sx)}" cy="${f(yIni)}" r="${MR}"/>
    <g class="st-fim"><circle cx="${f(sx)}" cy="${f(yFim)}" r="${MR}"/><circle cx="${f(sx)}" cy="${f(yFim)}" r="${MR - 4}"/></g>`;

  const H = Math.max(yFim + MR, yL + NH) + 10;
  const vx = Math.floor(minX) - 8, vw = Math.ceil(maxX) - vx + 8;
  return `<div class="st-hint glass-cap">caminho feliz na vertical · desvios na lateral · passe o mouse numa seta para ver o gatilho</div>
  <svg class="st-svg" viewBox="${vx} -8 ${vw} ${H + 16}" role="img"
    aria-label="Máquina de estados: caminho feliz de ${esc(espinha[0])} a ${esc(alvo)}, com ${laterais.length} desvios na lateral">
    <g class="st-arestas">${arestas.join('')}</g>${marcadores}${nos}<g class="st-rotulos">${rotulos.join('')}</g>
  </svg>`;
}

/* ---------- Flowchart: espinha do caminho feliz ---------- */

/* mesmo layout fechado do renderer de estado (ADR 0025), adaptado ao
   flowchart do pipeline de IA: os passos descem na vertical (menor caminho da
   fonte ao sumidouro, BFS na ordem de declaração), a decisão vira losango em
   destaque com os ramos rotulados sempre visíveis, e o desvio (resolução
   manual) fica pendurado na lateral com retorno em curva. A altura de cada nó
   segue as linhas de texto (<br/> do Mermaid); a largura é única, pela linha
   mais longa do diagrama. */
const FLH = 13;              // altura de linha do texto do nó
const FGY = 58;              // vão vertical entre nós da espinha
const FLGX = 150;            // vão entre a espinha e a coluna de desvios

function flowSvg(diag) {
  const nos = diag.nos || [];
  const arestas = diag.arestas || [];
  if (!nos.length || !arestas.length) return null;

  /* fonte = primeiro nó sem seta chegando; sumidouro = último sem seta saindo */
  const comEntrada = new Set(arestas.map(a => a.destino));
  const comSaida = new Set(arestas.map(a => a.origem));
  const fonte = nos.find(n => !comEntrada.has(n.id));
  const alvo = [...nos].reverse().find(n => !comSaida.has(n.id));
  if (!fonte || !alvo || fonte === alvo) return null;

  /* espinha: menor caminho da fonte ao sumidouro, BFS na ordem de declaração */
  const adj = new Map(nos.map(n => [n.id, []]));
  arestas.forEach(a => { if (adj.has(a.origem) && adj.has(a.destino)) adj.get(a.origem).push(a.destino); });
  const pai = new Map([[fonte.id, null]]);
  const fila = [fonte.id];
  while (fila.length && !pai.has(alvo.id)) {
    const n = fila.shift();
    for (const v of adj.get(n)) if (!pai.has(v)) { pai.set(v, n); fila.push(v); }
  }
  if (!pai.has(alvo.id)) return null;
  const espinha = [];
  for (let n = alvo.id; n != null; n = pai.get(n)) espinha.unshift(n);
  const idxE = new Map(espinha.map((n, i) => [n, i]));

  const chMax = Math.max(...nos.map(n => Math.max(...n.linhas.map(l => l.length))));
  const FW = Math.min(300, Math.max(150, Math.round(chMax * 6.4) + 26));
  const DW = FW + 40;        // o losango da decisão estufa além do retângulo
  const porId = new Map(nos.map(n => [n.id, n]));
  const altura = n => n.linhas.length * FLH + (n.decisao ? 46 : 22);

  const sx = DW / 2 + 8;               // centro x da espinha (losango não vaza)
  const lx = sx + FW + FLGX;           // centro x dos desvios
  const pos = new Map();               // id -> {x centro, y topo, h, w2 da âncora lateral}
  let y = 4;
  espinha.forEach(id => {
    const n = porId.get(id);
    pos.set(id, { x: sx, y, h: altura(n), w2: (n.decisao ? DW : FW) / 2 });
    y += altura(n) + FGY;
  });
  const fimEspinha = y - FGY;

  /* desvios: âncora na altura média dos nós da espinha ligados a eles,
     empilhados de cima pra baixo sem sobreposição */
  const laterais = nos.filter(n => !idxE.has(n.id));
  const centroE = id => pos.get(id).y + pos.get(id).h / 2;
  const anc = new Map(laterais.map(n => {
    const viz = arestas
      .filter(a => a.origem === n.id || a.destino === n.id)
      .map(a => (a.origem === n.id ? a.destino : a.origem))
      .filter(v => idxE.has(v)).map(centroE);
    return [n.id, viz.length ? viz.reduce((s, v) => s + v, 0) / viz.length : fimEspinha / 2];
  }));
  laterais.sort((a, b) => anc.get(a.id) - anc.get(b.id));
  let botL = -Infinity, minY = 0;
  laterais.forEach(n => {
    const h = altura(n);
    const topo = Math.max(anc.get(n.id) - h / 2, botL + 24);
    pos.set(n.id, { x: lx, y: topo, h, w2: (n.decisao ? DW : FW) / 2 });
    botL = topo + h;
    minY = Math.min(minY, topo);   // desvio ancorado no topo pode subir além do y=0
  });

  /* caminho feliz = arestas entre nós consecutivos da espinha (reta na prumada);
     o resto sai pelas laterais em curva, com âncoras em leque (mesma ideia do
     renderer de estado) pra não nascerem umas em cima das outras */
  const achar = (o, d) => arestas.findIndex(a => a.origem === o && a.destino === d);
  const feliz = new Set();
  for (let i = 0; i + 1 < espinha.length; i++) feliz.add(achar(espinha[i], espinha[i + 1]));
  const planos = arestas.map((a, i) => {
    if (feliz.has(i)) return { a, i, modo: 'reta' };
    const oE = idxE.has(a.origem), dE = idxE.has(a.destino);
    if (oE && dE) return { a, i, modo: 'arcoE', l1: -1, l2: -1 };
    if (!oE && !dE) return { a, i, modo: 'arcoD', l1: 1, l2: 1 };
    return oE ? { a, i, modo: 's', l1: 1, l2: -1 } : { a, i, modo: 's', l1: -1, l2: 1 };
  });
  const chave = (n, lado) => `${n}|${lado}`;
  const totalAnc = {}, vistoAnc = {};
  planos.forEach(p => {
    if (p.modo === 'reta') return;
    totalAnc[chave(p.a.origem, p.l1)] = (totalAnc[chave(p.a.origem, p.l1)] || 0) + 1;
    totalAnc[chave(p.a.destino, p.l2)] = (totalAnc[chave(p.a.destino, p.l2)] || 0) + 1;
  });
  const ponta = (n, lado) => {
    const p = pos.get(n), k = chave(n, lado);
    const i = vistoAnc[k] = (vistoAnc[k] || 0) + 1;
    const total = totalAnc[k];
    return { x: p.x + lado * p.w2, y: p.y + p.h / 2 + (i - (total + 1) / 2) * Math.min(9, (p.h - 10) / total) };
  };

  const f = n => n.toFixed(1);
  let minX = 0, maxX = 0;   // os extents dos nós entram no desenho deles
  const setas = [], rotulos = [];
  planos.forEach(p => {
    const { a, i } = p;
    let p1, p2, c1, c2;
    if (p.modo === 'reta') {
      const A = pos.get(a.origem), B = pos.get(a.destino);
      p1 = { x: A.x, y: A.y + A.h };
      p2 = { x: B.x, y: B.y };
      c1 = { x: p1.x, y: (2 * p1.y + p2.y) / 3 };
      c2 = { x: p1.x, y: (p1.y + 2 * p2.y) / 3 };
    } else if (p.modo === 's') {
      p1 = ponta(a.origem, p.l1);
      p2 = ponta(a.destino, p.l2);
      const mx = (p1.x + p2.x) / 2;
      c1 = { x: mx, y: p1.y };
      c2 = { x: mx, y: p2.y };
    } else {
      p1 = ponta(a.origem, p.l1);
      p2 = ponta(a.destino, p.l2);
      const arco = (p.modo === 'arcoE' ? -1 : 1) * (34 + Math.min(Math.abs(p2.y - p1.y) * 0.15, 60));
      c1 = { x: p1.x + arco, y: p1.y };
      c2 = { x: p2.x + arco, y: p2.y };
    }
    const d = `M ${f(p1.x)} ${f(p1.y)} C ${f(c1.x)} ${f(c1.y)}, ${f(c2.x)} ${f(c2.y)}, ${f(p2.x)} ${f(p2.y)}`;
    const ang = Math.atan2(p2.y - c2.y, p2.x - c2.x) * 180 / Math.PI;
    minX = Math.min(minX, p1.x, c1.x, c2.x, p2.x);
    maxX = Math.max(maxX, p1.x, c1.x, c2.x, p2.x);
    setas.push(`<g class="fl-rel${feliz.has(i) ? ' feliz' : ''}"
      aria-label="${esc(a.origem)} para ${esc(a.destino)}${a.rotulo ? ': ' + esc(a.rotulo) : ''}">
      <path class="fl-edge" d="${d}"/>
      <path class="fl-seta" transform="translate(${f(p2.x)} ${f(p2.y)}) rotate(${f(ang)})" d="M 0 0 L -7.5 -3.6 L -7.5 3.6 Z"/>
    </g>`);
    if (a.rotulo) {   // ramos da decisão (sim/nao) são parte do desenho, não segredo de hover
      const lxr = bezPt(0.5, p1.x, c1.x, c2.x, p2.x);
      const lyr = bezPt(0.5, p1.y, c1.y, c2.y, p2.y);
      minX = Math.min(minX, lxr - a.rotulo.length * 3.3);
      maxX = Math.max(maxX, lxr + a.rotulo.length * 3.3);
      rotulos.push(`<text class="fl-rotulo" x="${f(lxr)}" y="${f(lyr - 5)}">${esc(a.rotulo)}</text>`);
    }
  });

  const nosSvg = nos.map((n, i) => {
    const p = pos.get(n.id);
    const cy = p.y + p.h / 2;
    minX = Math.min(minX, p.x - p.w2);   // losango na lateral estufa além da coluna
    maxX = Math.max(maxX, p.x + p.w2);
    const classe = n.decisao ? 'fl-no-decisao' : idxE.has(n.id) ? 'fl-no-feliz' : 'fl-no-desvio';
    const forma = n.decisao
      ? `<path d="M ${f(p.x)} ${f(p.y)} L ${f(p.x + DW / 2)} ${f(cy)} L ${f(p.x)} ${f(p.y + p.h)} L ${f(p.x - DW / 2)} ${f(cy)} Z"/>`
      : `<rect x="${f(p.x - FW / 2)}" y="${f(p.y)}" width="${FW}" height="${p.h}" rx="10"/>`;
    const texto = n.linhas.map((l, j) =>
      `<text x="${f(p.x)}" y="${f(cy + (j - (n.linhas.length - 1) / 2) * FLH + 3.8)}">${esc(l)}</text>`).join('');
    return `<g class="fl-no ${classe}" data-n="${esc(n.id)}" style="--i:${Math.min(i, 12)}">${forma}${texto}</g>`;
  }).join('');

  const H = Math.max(fimEspinha, botL) + 6;
  const vx = Math.floor(minX) - 8, vw = Math.ceil(maxX) - vx + 16;
  const vy = Math.floor(Math.min(-8, minY - 8)), vh = H + 8 - vy;
  return `<div class="fl-hint glass-cap">caminho feliz na vertical · desvio na lateral · a decisão em losango tem os ramos rotulados</div>
  <svg class="fl-svg" viewBox="${vx} ${vy} ${vw} ${vh}" role="img"
    aria-label="Fluxograma: caminho feliz de ${esc(porId.get(espinha[0]).linhas[0])} a ${esc(porId.get(alvo.id).linhas[0])}, com ${laterais.length} desvios na lateral">
    <g class="fl-arestas">${setas.join('')}</g>${nosSvg}<g class="fl-rotulos">${rotulos.join('')}</g>
  </svg>`;
}

/* ---------- interface única ---------- */

const RENDERERS = { er: erSvg, seq: seqSvg, estado: estadoSvg, flow: flowSvg };

export function renderDiagrama(diag) {
  const fn = diag && Object.hasOwn(RENDERERS, diag.tipo) && RENDERERS[diag.tipo];
  if (!fn) return null;
  try {
    return fn(diag);
  } catch {
    return null;   // renderer nunca derruba a aba: sem desenho, o chamador mantém o fallback
  }
}

export function wireDiagramas(root) {
  root.querySelectorAll('.er-svg').forEach(wireErMapa);
  root.querySelectorAll('.seq-box').forEach(wireSeq);
  root.querySelectorAll('.st-svg').forEach(wireEstadoHover);
}

/* interações do ER (issue #255): o hover não revela nada, só destaca.
   Card: acende as FKs da tabela (traço animado) e as vizinhas; esmaece o
   resto. Linha de coluna FK: acende só aquela aresta, a tabela destino e a
   PK de lá. Clique/Enter no nome salta pra ficha no ENTIDADES (o data-act
   "ficha" borbulha até o handler delegado do app.js). */
function wireErMapa(svg) {
  const limpar = () => svg.querySelectorAll('.on, .fk-on').forEach(g => g.classList.remove('on', 'fk-on'));

  const focar = nome => {
    svg.classList.add('er-hover');
    limpar();
    const acesas = new Set([nome]);
    svg.querySelectorAll('.er-rel').forEach(g => {
      const liga = g.dataset.a === nome || g.dataset.b === nome;
      g.classList.toggle('on', liga);
      if (liga) { acesas.add(g.dataset.a); acesas.add(g.dataset.b); }
    });
    svg.querySelectorAll('.er-tab').forEach(g => g.classList.toggle('on', acesas.has(g.dataset.t)));
  };
  const restaurar = () => {
    svg.classList.remove('er-hover');
    limpar();
    // se uma tabela segue com foco de teclado, o destaque dela volta
    const focada = svg.querySelector('.er-tab:focus');
    if (focada) focar(focada.dataset.t);
  };
  const focarFk = (de, col, dest) => {
    svg.classList.add('er-hover');
    limpar();
    svg.querySelectorAll('.er-rel').forEach(g =>
      g.classList.toggle('on', g.dataset.a === dest && g.dataset.b === de && g.dataset.col === col));
    svg.querySelectorAll('.er-tab').forEach(g =>
      g.classList.toggle('on', g.dataset.t === de || g.dataset.t === dest));
    const pk = svg.querySelector(`.er-tab[data-t="${CSS.escape(dest)}"] .er-col[data-pk]`);
    if (pk) pk.classList.add('fk-on');
  };

  svg.querySelectorAll('.er-tab').forEach(g => {
    g.addEventListener('mouseenter', () => focar(g.dataset.t));
    g.addEventListener('mouseleave', restaurar);
    g.addEventListener('focus', () => focar(g.dataset.t));
    g.addEventListener('blur', restaurar);
    // Enter/Espaço no card abre a ficha, como o clique no nome
    g.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      const nome = g.querySelector('.er-tab-nome');
      if (nome) nome.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
  });

  svg.querySelectorAll('.er-col-fk').forEach(row => {
    const tab = row.closest('.er-tab');
    if (!tab) return;
    row.addEventListener('mouseenter', () => focarFk(tab.dataset.t, row.dataset.col, row.dataset.dest));
    // sair da linha volta pro destaque de vizinhança do card (ainda sob o mouse)
    row.addEventListener('mouseleave', () => focar(tab.dataset.t));
  });
}

/* hover/foco numa transição da máquina de estados: destaca a aresta e
   mostra o gatilho dela; o resto esmaece. Sair restaura. */
function wireEstadoHover(svg) {
  svg.querySelectorAll('.st-rel').forEach(g => {
    const rotulo = svg.querySelector(`.st-rotulo[data-i="${g.dataset.i}"]`);
    const ligar = on => {
      svg.classList.toggle('st-hover', on);
      g.classList.toggle('on', on);
      if (rotulo) rotulo.classList.toggle('on', on);
    };
    g.addEventListener('mouseenter', () => ligar(true));
    g.addEventListener('mouseleave', () => ligar(false));
    g.addEventListener('focus', () => ligar(true));
    g.addEventListener('blur', () => ligar(false));
  });
}
