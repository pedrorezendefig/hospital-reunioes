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

/* bloco de comando copia-e-cola. opts: {label, note, lang} */
let _cp = 0;
export function copyBlock(code, opts = {}) {
  const id = 'cp' + (++_cp);
  const label = opts.label ? `<div class="cmd-label">${esc(opts.label)}</div>` : '';
  const note = opts.note ? `<div class="cmd-note">${esc(opts.note)}</div>` : '';
  return `${label}<div class="cmd" data-lang="${esc(opts.lang || 'bash')}">
    <button class="cmd-copy" data-act="copy" data-cp="${id}" aria-label="Copiar comando"><span class="cc-ico" aria-hidden="true">⧉</span><span class="cc-txt">copiar</span></button>
    <pre class="cmd-code" id="${id}"><code>${esc(code)}</code></pre>
  </div>${note}`;
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
