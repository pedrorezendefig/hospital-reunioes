'use strict';

/* Renderers próprios de diagrama em SVG (ADR 0025): zero lib, zero CDN.

   Interface única por tipo: renderDiagrama(diag) devolve o HTML do desenho,
   ou null quando o tipo ainda não tem renderer (o chamador mantém o fallback
   de código cru). Depois que o HTML entra no DOM, wireDiagramas(root) liga a
   interatividade. As fatias seguintes do PRD #212 registram novos tipos em
   RENDERERS sem tocar nos chamadores. */

import { esc, reduceMotion } from './ui.js';

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
const COR_DOMINIO = {
  Pessoas: 'var(--indigo)', 'Reuniões': 'var(--coral)', POPs: 'var(--green)',
  Infra: 'var(--amber)', Outras: 'var(--purple)',
};
const dominioDe = t => (Object.hasOwn(DOMINIO_DE, t) ? DOMINIO_DE[t]
  : t === 'pops' || t.startsWith('pops_') ? 'POPs' : 'Outras');

/* layout fechado, sem motor de grafo: cards de tamanho fixo em grade de 2
   colunas dentro de cada cluster; clusters em 2 colunas (sempre a mais curta) */
const CW = 200, CH = 46;          // card
const GX = 12, GY = 10;           // gap entre cards
const PAD = 14, HEAD = 30;        // respiro interno e cabeçalho do cluster
const GCX = 30, GCY = 30;         // gap entre clusters
const CLW = 2 * CW + GX + 2 * PAD;

function erSvg(diag) {
  const tabelas = diag.tabelas || [];
  const relacoes = diag.relacoes || [];
  if (!tabelas.length) return null;

  const grupos = new Map(DOMINIOS.map(d => [d, []]));
  tabelas.forEach(t => grupos.get(dominioDe(t.nome)).push(t));

  const colY = [0, 0];
  const clusters = [];
  const pos = Object.create(null);   // sem prototype: tabela "__proto__" vira chave comum
  let seq = 0;
  for (const nome of DOMINIOS) {
    const ts = grupos.get(nome);
    if (!ts.length) continue;
    const linhas = Math.ceil(ts.length / 2);
    const alto = HEAD + 2 * PAD + linhas * CH + (linhas - 1) * GY;
    const col = colY[0] <= colY[1] ? 0 : 1;
    const x = col * (CLW + GCX), y = colY[col];
    colY[col] += alto + GCY;
    clusters.push({ nome, x, y, w: CLW, h: alto, n: ts.length });
    ts.forEach((t, i) => {
      pos[t.nome] = {
        t,
        x: x + PAD + (i % 2) * (CW + GX),
        y: y + HEAD + PAD + Math.floor(i / 2) * (CH + GY),
        i: seq++,
      };
    });
  }
  const W = 2 * CLW + GCX;
  const H = Math.max(colY[0], colY[1]) - GCY;

  /* arestas: bezier entre bordas dos cards; quando os dois estão na mesma
     prumada, a curva faz um arco pelo lado externo. Âncoras na mesma borda
     abrem em leque pra não se sobreporem. */
  const planos = relacoes.map(r => {
    const a = pos[r.origem], b = pos[r.destino];
    if (!a || !b) return null;
    const dx = (b.x + CW / 2) - (a.x + CW / 2);
    let ladoA, ladoB;
    if (Math.abs(dx) > CW) { ladoA = dx > 0 ? 1 : -1; ladoB = -ladoA; }
    else { ladoA = ladoB = (a.x + CW / 2) <= W / 2 ? -1 : 1; }
    return { r, a, b, ladoA, ladoB };
  }).filter(Boolean);

  const chave = (t, lado) => `${t}|${lado}`;
  const totalAncora = {}, vistoAncora = {};
  planos.forEach(p => {
    totalAncora[chave(p.r.origem, p.ladoA)] = (totalAncora[chave(p.r.origem, p.ladoA)] || 0) + 1;
    totalAncora[chave(p.r.destino, p.ladoB)] = (totalAncora[chave(p.r.destino, p.ladoB)] || 0) + 1;
  });
  const yAncora = (t, lado, base) => {
    const k = chave(t, lado);
    const i = vistoAncora[k] = (vistoAncora[k] || 0) + 1;
    const n = totalAncora[k];
    return base + (i - (n + 1) / 2) * Math.min(8, (CH - 12) / n);
  };

  let minX = 0, maxX = W;   // arcos laterais e rótulos podem sair do retângulo dos clusters
  const arestas = [], rotulos = [];
  planos.forEach(p => {
    const x1 = p.a.x + (p.ladoA > 0 ? CW : 0), y1 = yAncora(p.r.origem, p.ladoA, p.a.y + CH / 2);
    const x2 = p.b.x + (p.ladoB > 0 ? CW : 0), y2 = yAncora(p.r.destino, p.ladoB, p.b.y + CH / 2);
    let c1x, c2x, tl;
    if (p.ladoA !== p.ladoB) { c1x = c2x = (x1 + x2) / 2; tl = 0.72; }   // rótulo perto do destino (a FK mora lá)
    else {
      const arco = p.ladoA * (26 + Math.min(Math.abs(y2 - y1) * 0.12, 40));
      c1x = x1 + arco; c2x = x2 + arco;
      tl = 0.5;                                                          // arco lateral: rótulo no ápice, longe dos cards
    }
    // ponto da bezier cúbica em t = tl; os controles têm x = c1x/c2x e y = y1/y2
    const bez = (t, p0, p1, p2, p3) => {
      const u = 1 - t;
      return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
    };
    const lx = bez(tl, x1, c1x, c2x, x2);
    const ly = bez(tl, y1, y1, y2, y2);
    const meioRotulo = p.r.rotulo.length * 3.1;      // ~6.2px/caractere na fonte de 10px
    minX = Math.min(minX, lx - meioRotulo);
    maxX = Math.max(maxX, lx + meioRotulo);
    const f = n => n.toFixed(1);
    arestas.push(`<g class="er-rel" data-a="${esc(p.r.origem)}" data-b="${esc(p.r.destino)}">
      <path class="er-edge" d="M ${f(x1)} ${f(y1)} C ${f(c1x)} ${f(y1)}, ${f(c2x)} ${f(y2)}, ${f(x2)} ${f(y2)}"/>
      <circle class="er-edge-pt" cx="${f(x2)}" cy="${f(y2)}" r="3"/>
    </g>`);
    rotulos.push(`<text class="er-rel-label" data-a="${esc(p.r.origem)}" data-b="${esc(p.r.destino)}"
      x="${f(lx)}" y="${f(ly - 6)}">${esc(p.r.rotulo)}</text>`);
  });

  const caixas = clusters.map(c => `
    <g class="er-cluster">
      <rect x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="14"/>
      <text x="${c.x + PAD}" y="${c.y + 20}" style="fill:${COR_DOMINIO[c.nome]}">${esc(c.nome.toUpperCase())} · ${c.n}</text>
    </g>`).join('');

  const cards = Object.values(pos).map(p => {
    const total = p.t.colunas.length + (p.t.extras || 0);
    const pk = p.t.colunas.find(c => c.pk);
    const sub = [
      total ? `${total} coluna${total === 1 ? '' : 's'}` : 'colunas fora do snapshot',
      pk ? `PK ${pk.nome}` : '',
    ].filter(Boolean).join(' · ');
    return `<g class="er-tab" data-t="${esc(p.t.nome)}" tabindex="0" style="--i:${Math.min(p.i, 12)}">
      <rect x="${p.x}" y="${p.y}" width="${CW}" height="${CH}" rx="9"/>
      <text class="er-tab-nome" x="${p.x + 12}" y="${p.y + 19}">${esc(p.t.nome)}</text>
      <text class="er-tab-sub" x="${p.x + 12}" y="${p.y + 35}">${esc(sub)}</text>
    </g>`;
  }).join('');

  const vx = Math.floor(minX) - 8, vw = Math.ceil(maxX) - vx + 8;
  return `<svg class="er-svg" viewBox="${vx} -8 ${vw} ${H + 16}"
    role="img" aria-label="Diagrama do banco de dados: tabelas agrupadas por domínio">
    ${caixas}<g class="er-arestas">${arestas.join('')}</g>${cards}<g class="er-rotulos">${rotulos.join('')}</g>
  </svg>`;
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
    minX = Math.min(minX, bezPt(0.5, p1.x, c1.x, c2.x, p2.x) - 20);
    maxX = Math.max(maxX, bezPt(0.5, p1.x, c1.x, c2.x, p2.x) + 20);
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
  return `<div class="st-hint">caminho feliz na vertical · desvios na lateral · passe o mouse numa seta para ver o gatilho</div>
  <svg class="st-svg" viewBox="${vx} -8 ${vw} ${H + 16}" role="img"
    aria-label="Máquina de estados: caminho feliz de ${esc(espinha[0])} a ${esc(alvo)}, com ${laterais.length} desvios na lateral">
    <g class="st-arestas">${arestas.join('')}</g>${marcadores}${nos}<g class="st-rotulos">${rotulos.join('')}</g>
  </svg>`;
}

/* ---------- interface única ---------- */

const RENDERERS = { er: erSvg, seq: seqSvg, estado: estadoSvg };

export function renderDiagrama(diag) {
  const fn = diag && Object.hasOwn(RENDERERS, diag.tipo) && RENDERERS[diag.tipo];
  if (!fn) return null;
  try {
    return fn(diag);
  } catch {
    return null;   // renderer nunca derruba a aba: sem desenho, o chamador mantém o fallback
  }
}

/* hover/foco numa tabela: acende as FKs dela (traço animado) e as tabelas
   na outra ponta; esmaece o resto. Sair restaura. */
export function wireDiagramas(root) {
  root.querySelectorAll('.er-svg').forEach(svg => {
    const focar = nome => {
      svg.classList.add('er-hover');
      const acesas = new Set([nome]);
      svg.querySelectorAll('.er-rel, .er-rel-label').forEach(g => {
        const liga = g.dataset.a === nome || g.dataset.b === nome;
        g.classList.toggle('on', liga);
        if (liga) { acesas.add(g.dataset.a); acesas.add(g.dataset.b); }
      });
      svg.querySelectorAll('.er-tab').forEach(g => g.classList.toggle('on', acesas.has(g.dataset.t)));
    };
    const restaurar = () => {
      svg.classList.remove('er-hover');
      svg.querySelectorAll('.on').forEach(g => g.classList.remove('on'));
      // se uma tabela segue com foco de teclado, o destaque dela volta
      const focada = svg.querySelector('.er-tab:focus');
      if (focada) focar(focada.dataset.t);
    };
    svg.querySelectorAll('.er-tab').forEach(g => {
      g.addEventListener('mouseenter', () => focar(g.dataset.t));
      g.addEventListener('mouseleave', restaurar);
      g.addEventListener('focus', () => focar(g.dataset.t));
      g.addEventListener('blur', restaurar);
    });
  });
  root.querySelectorAll('.seq-box').forEach(wireSeq);

  /* hover/foco numa transição da máquina de estados: destaca a aresta e
     mostra o gatilho dela; o resto esmaece. Sair restaura. */
  root.querySelectorAll('.st-svg').forEach(svg => {
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
  });
}
