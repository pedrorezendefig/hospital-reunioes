'use strict';

/* Componentes de UI reutilizáveis do painel (vanilla, zero-build).
   Importado pelo app.js. Conteúdo dinâmico é sempre escapado com esc(). */

import { TERMS } from './content/glossary.js';

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const reduceMotion = () =>
  window.matchMedia && matchMedia('(prefers-reduced-motion:reduce)').matches;

/* tooltip "?" acessível: abre por hover, foco (Tab+Enter) e tap.
   `key` busca no glossário TERMS; `literal` sobrescreve com texto livre. */
export function tip(key, literal) {
  const txt = literal ?? TERMS[key] ?? key;
  return `<button type="button" class="tip" data-act="tip" aria-label="O que é: ${esc(key)}" aria-expanded="false"><span class="tip-q" aria-hidden="true">?</span><span class="tip-pop" role="tooltip">${esc(txt)}</span></button>`;
}

/* os termos do glossário para marcar texto corrido: o jargão do TERMS (sem
   caixa) e cada `**Termo**:` do CONTEXT.md (com caixa: "Manual" é o termo,
   "manual" não), com a primeira frase como definição curta */
export function termosGlossario(contextMd) {
  const lista = Object.entries(TERMS).filter(([k]) => !k.includes('_'))
    .map(([nome, def]) => ({ nome, def, caixa: false }));
  const linhas = String(contextMd || '').split('\n');
  linhas.forEach((linha, i) => {
    const t = /^\*\*(.+?)\*\*[^:]*:\s*$/.exec(linha);
    const corpo = t && (linhas[i + 1] || '').replace(/\*\*|`|\[|\]/g, '').trim();
    if (!corpo) return;
    const frase = /^(.+?[.!?])(\s|$)/.exec(corpo);
    lista.push({ nome: t[1], def: frase ? frase[1] : corpo, caixa: true });
  });
  return lista;
}

/* escapa o texto e sublinha a primeira ocorrência de cada termo, com a
   definição no hover e no foco; o mais longo ganha ("Fatia de manual" antes
   de "Manual") e pedaço de nome não conta (/onda-enxuta, fechar_onda.py) */
export function marcarTermos(texto, termos) {
  const s = String(texto ?? '');
  const ordem = [...(termos || [])].sort((a, b) => b.nome.length - a.nome.length);
  if (!ordem.length) return esc(s);
  const alt = ordem.map(t => t.nome.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const re = new RegExp(`(?<![\\p{L}\\p{N}_/.-])(?:${alt})(?![\\p{L}\\p{N}_-])`, 'giu');
  const usados = new Set();
  let html = '', i = 0, m;
  while ((m = re.exec(s))) {
    const achado = m[0];
    const t = ordem.find(x => !usados.has(x) && (x.caixa ? x.nome === achado : x.nome.toLowerCase() === achado.toLowerCase()));
    if (!t) continue;
    usados.add(t);
    html += esc(s.slice(i, m.index))
      + `<span class="gl-termo" tabindex="0">${esc(achado)}<span class="gl-def" role="tooltip"><b>${esc(t.nome)}</b>${esc(t.def)}</span></span>`;
    i = m.index + achado.length;
  }
  return html + esc(s.slice(i));
}

/* sub-bloco técnico recolhível (<details> nativo: acessível por teclado) */
export function techDetails(html, label = 'detalhes técnicos') {
  return html
    ? `<details class="techbox"><summary>${esc(label)}</summary><div class="techbox-body">${html}</div></details>`
    : '';
}

/* revela elementos no scroll: adiciona .in ao entrar na viewport.
   Threshold baixo de propósito: elementos mais altos que a viewport (capas,
   SVGs do mapa) nunca atingem ratios grandes e ficariam invisíveis.
   Retorna o observer (ou null) para quem quiser desconectar ao trocar de aba. */
export function revealOnScroll(root, selector, onReveal) {
  const els = [...(root || document).querySelectorAll(selector)];
  if (reduceMotion() || !('IntersectionObserver' in window)) {
    els.forEach(e => { e.classList.add('in'); onReveal && onReveal(e); });
    return null;
  }
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add('in'); onReveal && onReveal(e.target); io.unobserve(e.target); }
    });
  }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });
  els.forEach(e => io.observe(e));
  return io;
}

/* fecha todos os tooltips abertos (Escape / clique-fora) */
export function closeTips() {
  document.querySelectorAll('.tip.open').forEach(t => {
    t.classList.remove('open');
    t.setAttribute('aria-expanded', 'false');
  });
}
