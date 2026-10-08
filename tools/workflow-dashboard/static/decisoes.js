'use strict';

/* Decisões em mapa de miniaturas por tema (issue #1082). O agrupamento é
   puro (testado no Node): cada tema do docs/adr/README.md com as ADRs
   visíveis, as setas do frontmatter dentro do tema e, para vínculo com outro
   tema, um chip nas duas pontas. As setas se desenham depois do layout, por
   cima da grade (desenharSetas). */

/* sem índice parseável, o tema é o prefixo do título (o que vem antes dos
   dois-pontos); sem prefixo, "Outras" */
export function temasPorPrefixo(adrs) {
  const grupos = new Map();
  adrs.forEach(a => {
    const m = /^(.{3,40}?):/.exec(a.title || '');
    const tema = m ? m[1] : 'Outras';
    if (!grupos.has(tema)) grupos.set(tema, []);
    grupos.get(tema).push(a.number);
  });
  return [...grupos].map(([tema, numeros]) => ({ tema, numeros }));
}

/* [{ tema, nos: [adr], setas: [{de, para, tipo}], chips: {n: [{n, tema, sai}]} }]
   na ordem do índice, ADRs em ordem de número; `hist` traz as não aceitas,
   `q` filtra título e corpo. Tema sem ADR visível some. */
export function mapaDecisoes(adrs, temas, arestas, { hist = false, q = '' } = {}) {
  const lista = (temas && temas.length) ? temas : temasPorPrefixo(adrs);
  const busca = q.trim().toLowerCase();
  const visivel = a => (hist || a.status === 'accepted')
    && (!busca || `${a.title} ${a.body_md}`.toLowerCase().includes(busca));
  const porNumero = new Map(adrs.map(a => [a.number, a]));
  const grupos = lista.map(t => ({ tema: t.tema, numeros: t.numeros.filter(n => porNumero.has(n)) }));
  const noIndice = new Set(grupos.flatMap(g => g.numeros));
  const fora = adrs.map(a => a.number).filter(n => !noIndice.has(n));
  if (fora.length) grupos.push({ tema: 'Fora do índice', numeros: fora });

  const temaDe = new Map();
  grupos.forEach(g => g.numeros.forEach(n => {
    if (visivel(porNumero.get(n))) temaDe.set(n, g.tema);
  }));
  const out = grupos.map(g => ({
    tema: g.tema,
    nos: g.numeros.filter(n => temaDe.has(n)).sort((a, b) => a - b).map(n => porNumero.get(n)),
    setas: [],
    chips: {},
  })).filter(g => g.nos.length);
  const doTema = new Map(out.map(g => [g.tema, g]));
  const chip = (g, n, outro, sai) => (g.chips[n] ||= []).push({ n: outro, tema: temaDe.get(outro), sai });
  (arestas || []).forEach(s => {
    const td = temaDe.get(s.de), tp = temaDe.get(s.para);
    if (!td || !tp) return;
    if (td === tp) doTema.get(td).setas.push({ de: s.de, para: s.para, tipo: s.tipo });
    else {
      chip(doTema.get(td), s.de, s.para, true);
      chip(doTema.get(tp), s.para, s.de, false);
    }
  });
  return out;
}

/* as ADRs ligadas a uma pelo frontmatter, com o rótulo de cada lado */
export function vinculosDe(a) {
  return [
    ['emenda', a.emenda], ['substitui', a.substitui],
    ['emendada por', a.emendada_por], ['substituída por', a.substituida_por], ['cita', a.cita],
  ].filter(([, ns]) => ns && ns.length);
}

/* o ponto onde a reta do centro de r até (x, y) cruza a borda de r */
function borda(r, x, y) {
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
  const dx = x - cx, dy = y - cy;
  if (!dx && !dy) return [cx, cy];
  const k = Math.min(Math.abs(r.w / 2 / (dx || 1e-9)), Math.abs(r.h / 2 / (dy || 1e-9)));
  return [cx + dx * k, cy + dy * k];
}

/* desenha as setas do data-setas ("22>68:substitui,21>16:emenda") de cada
   .adr-mapa no <svg class="adr-setas"> dele, medindo as miniaturas já
   dispostas pela grade; tema recolhido não tem layout e fica sem desenho */
export function desenharSetas(root) {
  root.querySelectorAll('.adr-mapa').forEach(box => {
    const svg = box.querySelector('.adr-setas');
    if (!svg) return;
    const i = box.dataset.i;   // marcador por tema: o de um tema recolhido não some dos outros
    svg.innerHTML = '';
    const b = box.getBoundingClientRect();
    if (!b.width) return;
    svg.setAttribute('viewBox', `0 0 ${b.width} ${b.height}`);
    const caixa = n => {
      const el = box.querySelector(`.adr-mini[data-n="${n}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left - b.left, y: r.top - b.top, w: r.width, h: r.height };
    };
    const setas = (box.dataset.setas || '').split(',').filter(Boolean).map(s => {
      const [, de, para, tipo] = /^(\d+)>(\d+):(\w+)$/.exec(s) || [];
      const r1 = caixa(de), r2 = caixa(para);
      if (!r1 || !r2) return '';
      const [x1, y1] = borda(r1, r2.x + r2.w / 2, r2.y + r2.h / 2);
      const [x2, y2] = borda(r2, r1.x + r1.w / 2, r1.y + r1.h / 2);
      // curva leve para a seta não passar reta por cima da vizinha da linha
      const mx = (x1 + x2) / 2 - (y2 - y1) * 0.18, my = (y1 + y2) / 2 + (x2 - x1) * 0.18;
      const f = v => v.toFixed(1);
      return `<path class="adr-seta adr-seta-${tipo}" data-de="${de}" data-para="${para}" marker-end="url(#adr-ponta-${i})" d="M${f(x1)},${f(y1)} Q${f(mx)},${f(my)} ${f(x2)},${f(y2)}"/>`;
    });
    // o svg recebe o desenho como texto (o mesmo caminho do diagramas.js)
    svg.innerHTML = `<defs><marker id="adr-ponta-${i}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z"/></marker></defs>${setas.join('')}`;
  });
}
