'use strict';

/* Fluxo vivo, SPA vanilla. Lê /api/data (agregado) e /api/issue/<n> (comentários lazy). */

import { tip, copyBlock, closeTips, reduceMotion, revealOnScroll } from './ui.js';
import { renderDiagrama, wireDiagramas } from './diagramas.js';
import { renderArea, wireArea } from './areas.js';

const S = {
  data: null,
  tab: 'plano',
  fIssues: { state: 'all', label: '', q: '' },
  expIss: new Set(),
  expPrd: new Set(),
  expDep: new Set(),
  expAdr: new Set(),
  comments: {},
  mapaDoc: null,
  rotasQ: '',
  entTab: null,
  erFull: false,
};

const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');

/* observers de reveal vivos; desconectados antes de cada re-render */
let _ioView = null, _ioList = null;

/* ---------- helpers ---------- */

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

if (window.marked) {
  marked.use({
    gfm: true,
    // HTML cru do markdown (issues/comentários vêm do GitHub) não é interpretado:
    // comentários <!-- --> somem, o resto vira texto escapado.
    renderer: {
      html(html) {
        const s = String(html && html.text != null ? html.text : html);
        return /^\s*<!--[\s\S]*?-->\s*$/.test(s) ? '' : esc(s);
      },
    },
  });
}

const md = s => window.marked ? marked.parse(s || '') : `<pre>${esc(s)}</pre>`;

const MES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function fmtD(iso) {
  if (!iso) return '·';
  const d = new Date(iso);
  return `${d.getDate()} ${MES[d.getMonth()]}`;
}
function fmtDT(iso) {
  if (!iso) return '·';
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0'), mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getDate()} ${MES[d.getMonth()]}, ${hh}:${mm}`;
}
function ago(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 50e3) return `há ${Math.max(1, Math.round(ms / 1e3))}s`;
  if (ms < 3.6e6) return `há ${Math.round(ms / 6e4)} min`;
  if (ms < 48 * 3.6e6) return `há ${Math.round(ms / 3.6e6)} h`;
  return `há ${Math.round(ms / 86.4e6)} dias`;
}
function spanH(msNum) {
  const h = msNum / 3.6e6;
  if (h < 1) return `${Math.max(1, Math.round(msNum / 6e4))} min`;
  if (h < 48) return `${h.toFixed(1).replace('.', ',')} h`;
  return `${(h / 24).toFixed(1).replace('.', ',')} dias`;
}
function durS(sec) {
  if (sec == null) return '·';
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m ? `${m}m${String(s).padStart(2, '0')}s` : `${s}s`;
}

const LABEL_CLS = {
  'ready-for-agent': 'b-green', 'in-progress': 'b-amber', 'blocked': 'b-red',
  'needs-triage': 'b-purple', 'needs-info': 'b-blue', 'ready-for-human': 'b-coral',
  'wontfix': 'b-ghost',
};
function labelBadge(name) {
  const cls = LABEL_CLS[name] ||
    (name.startsWith('type:') ? 'b-indigo' : name.startsWith('area:') ? 'b-blue'
      : name.startsWith('fatia:') ? 'b-indigo' : 'b-ghost');
  return `<span class="badge ${cls}">${esc(name)}</span>`;
}

const ADR_STATUS_CLS = {
  accepted: 'b-green', superseded: 'b-ghost', deprecated: 'b-ghost',
  proposed: 'b-blue', rejected: 'b-red',
};
function adrStatusBadge(status) {
  // Estado fora do conjunto canônico (inclui "?" de ADR sem frontmatter) grita em vermelho.
  return `<span class="badge ${ADR_STATUS_CLS[status] || 'b-red'}">${esc(status)}</span>`;
}
function adrPointerBadge(a) {
  const ptr = a.superseded_by ? `→ ${a.superseded_by}`
    : a.amended_by ? `± ${a.amended_by}` : '';
  return ptr ? `<span class="badge b-ghost">${esc(ptr)}</span>` : '';
}

const issUrl = n => `${S.data.repo_url}/issues/${n}`;
const prUrl = n => `${S.data.repo_url}/pull/${n}`;
const shaUrl = sha => `${S.data.repo_url}/commit/${sha}`;

function stateTag(i) {
  return i.state === 'OPEN'
    ? '<span class="istate"><span class="dot ok"></span>aberta</span>'
    : '<span class="istate"><span class="dot" style="background:var(--purple)"></span>fechada</span>';
}

function spark(vals, w = 360, h = 46) {
  if (vals.length < 2) return '';
  const max = Math.max(...vals), min = Math.min(...vals);
  const pts = vals.map((v, i) => [
    (i / (vals.length - 1)) * (w - 10) + 5,
    h - 7 - ((v - min) / ((max - min) || 1)) * (h - 16),
  ]);
  const poly = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
  const [lx, ly] = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <polyline points="${poly}" fill="none" style="stroke:var(--brand)" stroke-width="1.6" stroke-linejoin="round"/>
    <circle cx="${lx}" cy="${ly}" r="3.2" style="fill:var(--brand-light)"/></svg>`;
}

/* ---------- carga de dados ---------- */

async function load(fresh = false, silent = false) {
  const btn = $('#refresh');
  if (btn) btn.classList.add('spin');
  try {
    const r = await fetch('/api/data' + (fresh ? '?fresh=1' : ''));
    const j = await r.json();
    const changed = !S.data || j.generated_at !== S.data.generated_at;
    S.data = j;
    renderMast(); renderBanner(); renderFoot();
    const typing = document.activeElement && document.activeElement.classList.contains('search');
    if ((changed || !silent) && !typing) render();
  } catch (e) {
    $('#banner').innerHTML =
      `<div class="banner"><b>servidor fora do ar?</b> ${esc(e.message || e)}</div>`;
  } finally {
    if (btn) btn.classList.remove('spin');
  }
}

/* ---------- shell ---------- */

function renderMast() {
  const st = S.data.state || {};
  const svcs = st.services || [];
  const okCount = svcs.filter(s => s.status === 'healthy').length;
  const allOk = svcs.length && okCount === svcs.length;
  $('#mast-status').innerHTML = `
    <span class="capsule"><span class="dot ${allOk ? 'ok pulse' : 'bad'}"></span>
      <b>v${esc(st.last_app_version || '?')}</b>&nbsp;· prod ${allOk ? 'healthy' : `${okCount}/${svcs.length} ok`}</span>
    <span class="ago" id="ago">coletado ${ago(S.data.generated_at)}</span>
    <button class="iconbtn" id="refresh" title="recoletar agora (gh + arquivos)">⟳</button>`;
  $('#refresh').addEventListener('click', () => load(true));
  const hv = $('#hero-version');
  if (hv) hv.textContent = `v${st.last_app_version || '?'} em produção`;
}

function renderBanner() {
  const err = S.data.github && S.data.github.error;
  $('#banner').innerHTML = err
    ? `<div class="banner"><b>GitHub indisponível</b>: ${esc(err)}<br>Mostrando só os dados locais (deploys, snapshots, ADRs, glossário).</div>`
    : '';
}

function renderFoot() {
  $('#foot').innerHTML = `
    <span>tools/workflow-dashboard · somente leitura · fontes: <span class="mono">gh</span> + docs/spec + git</span>
    <span class="foot-right">coletado às ${esc(fmtDT(S.data.generated_at))}
      <a class="btn-pill outline" href="${esc(S.data.repo_url)}" target="_blank" rel="noopener">${esc(S.data.repo_slug)} <span class="btn-arrow">↗</span></a></span>`;
}

function tick() {
  const el = $('#ago');
  if (el && S.data) el.textContent = `coletado ${ago(S.data.generated_at)}`;
}

const TABS = ['plano', 'issues', 'producao', 'mapa', 'dominio', 'guia'];
/* hashes da navegação antiga (bookmarks) caem na aba que herdou o conteúdo */
const TAB_ALIAS = {
  setup: 'guia', workflow: 'guia', fluxo: 'guia', bastidores: 'guia',
  agora: 'producao', deploys: 'producao',
};

function setTab(t) {
  t = TAB_ALIAS[t] || t;
  if (!TABS.includes(t)) t = 'plano';
  S.erFull = false;   // trocar de aba sai da tela cheia; voltar ao Mapa não a reabre
  S.tab = t;
  if (location.hash !== '#' + t) history.replaceState(null, '', '#' + t);
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  render();
  window.scrollTo({ top: 0 });
}

function render() {
  if (!S.data) return;
  const fn = {
    plano: renderPlano, issues: renderIssues, producao: renderProducao,
    mapa: renderMapa, dominio: renderDominio, guia: renderGuia,
  }[S.tab];
  view.innerHTML = fn ? fn() : '';
  if (S.tab === 'issues') wireIssues();
  if (S.tab === 'mapa') {
    try { desenharDiagramas(view); } catch { /* bloco fica no fallback de código cru */ }
    try { wireDiagramas(view); } catch { /* diagrama sem interação > aba quebrada */ }
    const cur = (S.data.snapshots || []).find(s => s.name === S.mapaDoc);
    try { wireArea(view, cur, areaCtx()); } catch { /* capa sem interação > aba quebrada */ }
  }
  // tela cheia do ER só existe na aba mapa; o lock de scroll segue o estado
  document.body.classList.toggle('er-lock', S.tab === 'mapa' && S.erFull);
  if (_ioView) _ioView.disconnect();
  if (_ioList) { _ioList.disconnect(); _ioList = null; }
  _ioView = revealOnScroll(view, '.rv');
}

const sec = (n, title, hint = '') =>
  `<div class="sec rv"><span class="n">${n}</span><h2 class="clip"><span class="clip-inner">${title}</span></h2>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;

/* ---------- PLANO (home) ---------- */

const fmtHoras = h => spanH(h * 3.6e6);

function tempoTipicoHtml(t) {
  if (!t) return '<span class="ftempo vazio">⏱ sem histórico ainda</span>';
  const marca = t.fonte === 'geral'
    ? `<em class="ftempo-fonte">· mediana geral</em>${tip('mediana geral')}` : '';
  return `<span class="ftempo">⏱ ~${esc(fmtHoras(t.horas))} ${marca}</span>`;
}

const ESTADO_FATIA = {
  pronta: { cls: 'pronta', badge: '<span class="badge b-green">pronta</span>' },
  bloqueada: { cls: 'bloq', badge: '<span class="badge b-red">bloqueada</span>' },
  em_andamento: { cls: 'andamento', badge: '<span class="badge b-amber">● em andamento</span>' },
  concluida: { cls: 'feita', badge: '<span class="badge b-purple">concluída ✓</span>' },
  aguardando_triage: { cls: 'triage', badge: '<span class="badge b-blue">aguardando triage</span>' },
};

function fatiaCard(f) {
  const e = ESTADO_FATIA[f.estado] || ESTADO_FATIA.pronta;
  const bloqueio = f.estado === 'bloqueada' && f.bloqueada_por.length
    ? `<span class="fbloq">⛔ espera ${f.bloqueada_por.map(n =>
      `<a href="${issUrl(n)}" target="_blank" rel="noopener">#${n}</a>`).join(', ')}</span>` : '';
  const triage = f.estado === 'aguardando_triage'
    ? '<span class="ftriage">⏳ fora da fila, rode <code>/triage</code> para liberar</span>' : '';
  const copia = f.estado === 'pronta' && f.copiaveis ? `
    <div class="fcopia">
      ${copyBlock(f.copiaveis.terminal, { lang: 'bash' })}
      <a class="fslash" data-act="copytxt" data-txt="${esc(f.copiaveis.slash)}">copiar só o <code>${esc(f.copiaveis.slash)}</code></a>
    </div>` : '';
  return `
  <article class="card fatia f-${e.cls}">
    <div class="fhead">
      <a class="fnum" href="${esc(f.url)}" target="_blank" rel="noopener">#${f.number}</a>
      <a class="ftitle" href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.title)}</a>
    </div>
    <div class="fmeta">${e.badge}${f.tamanho ? labelBadge('fatia:' + f.tamanho) : ''}${tempoTipicoHtml(f.tempo_tipico)}${bloqueio}${triage}</div>
    ${f.explicacao ? `<p class="fexp">${esc(f.explicacao)}</p>` : ''}
    ${copia}
  </article>`;
}

function ondaHtml(onda, i) {
  const hint = i === 0 ? 'dá para começar agora' : `destrava quando a onda ${i} fechar`;
  const paralelo = onda.length > 1 ? ` · ${onda.length} em paralelo` : '';
  return `
  <div class="onda ${onda.length > 1 ? 'paralela' : 'serial'} rv" style="--i:${i + 1}">
    <div class="onda-rotulo"><span class="onda-n">onda ${i + 1}</span><span class="onda-hint">${hint}${paralelo}</span></div>
    <div class="onda-fatias">${onda.map(fatiaCard).join('')}</div>
  </div>`;
}

function levaHtml(leva, idx) {
  const abertas = leva.ondas.reduce((a, o) => a + o.length, 0);
  const cc = leva.caminho_critico_horas;
  const chips = [
    `<span class="capsule"><b>${abertas}</b>&nbsp;aberta${abertas === 1 ? '' : 's'}</span>`,
    leva.concluidas.length ? `<span class="capsule">✓&nbsp;<b>${leva.concluidas.length}</b>&nbsp;entregue${leva.concluidas.length === 1 ? '' : 's'}</span>` : '',
    cc != null ? `<span class="capsule">caminho crítico&nbsp;<b>~${esc(fmtHoras(cc))}</b>${tip('caminho crítico')}</span>` : '',
  ].filter(Boolean).join('');
  const avisos = (leva.avisos || []).map(a => `<div class="banner plano-aviso">⚠ ${esc(a)}</div>`).join('');
  const feitas = leva.concluidas.length ? `
    <div class="feitas rv">
      <span class="k-label">já entregues</span>
      <div class="feitas-row">${leva.concluidas.map(f =>
        `<a class="feita-chip" href="${esc(f.url)}" target="_blank" rel="noopener">✓ #${f.number} ${esc(f.title)}</a>`).join('')}</div>
    </div>` : '';
  return `
  <section class="leva">
    <div class="leva-head rv" style="--i:${idx}">
      <span class="prd-tag">PRD</span>
      <a class="leva-title" href="${esc(leva.prd.url)}" target="_blank" rel="noopener">#${leva.prd.number} · ${esc(leva.prd.title)} ↗</a>
      <div class="leva-chips">${chips}</div>
    </div>
    ${avisos}
    ${leva.ondas.length ? `<div class="ondas">${leva.ondas.map(ondaHtml).join('')}</div>`
      : '<div class="empty">todas as fatias desta leva foram entregues: feche o PRD ou abra a próxima leva</div>'}
    ${feitas}
  </section>`;
}

function avulsasHtml(av) {
  if (!av || !av.ondas.length) return '';
  const avisos = (av.avisos || []).map(a => `<div class="banner plano-aviso">⚠ ${esc(a)}</div>`).join('');
  return `
  <section class="leva">
    <div class="leva-head rv">
      <span class="prd-tag avulsa-tag">AVULSAS</span>
      <span class="leva-title">Issues fora de PRD</span>
    </div>
    ${avisos}
    <div class="ondas">${av.ondas.map(ondaHtml).join('')}</div>
  </section>`;
}

function renderPlano() {
  const cab = sec('', 'Plano', 'a leva atual, em ondas de execução');
  const p = S.data.plano;
  if (!p) {
    return `${cab}<div class="empty">O Plano lê as issues pelo <span class="mono">gh</span>, que está indisponível agora, veja o aviso no topo. As outras abas seguem com os dados locais.</div>`;
  }
  if (p.erro) return `${cab}<div class="banner"><b>Plano indisponível</b>: ${esc(p.erro)}</div>`;
  const temAvulsas = p.avulsas && p.avulsas.ondas.length;
  if (!p.levas.length && !temAvulsas) {
    return `${cab}
    <div class="card plano-vazio rv">
      <h3>Nenhum PRD ativo agora.</h3>
      <p>O plano nasce do pipeline: lapide a ideia, publique o PRD e corte em fatias: esta aba desenha o resto sozinha.</p>
      ${copyBlock('/grill-with-docs\n/to-prd\n/to-issues', { lang: 'text', label: 'numa sessão claude, na ordem' })}
    </div>`;
  }
  const lead = `<p class="lead rv">As fatias do PRD ativo, organizadas em <b>ondas</b>${tip('onda')} pela dependência:
    o que divide uma onda anda <b>em paralelo</b>: cada sessão pega uma fatia (claim atômico${tip('claim atômico')},
    1 worktree por issue${tip('worktree')}). Copie o comando de um card <b>pronta</b> e cole num terminal novo.</p>`;
  return cab + lead + p.levas.map(levaHtml).join('') + avulsasHtml(p.avulsas);
}

/* ---------- PRODUÇÃO (timeline de deploys e releases) ---------- */

function renderProducao() {
  return renderDeploys();
}


/* ---------- ISSUES ---------- */

function leadAvg(iss) {
  const closed = iss.filter(i => i.closed_at && i.created_at);
  if (!closed.length) return null;
  return closed.reduce((a, i) => a + (new Date(i.closed_at) - new Date(i.created_at)), 0) / closed.length;
}

function matchIssue(i) {
  const f = S.fIssues;
  if (f.state !== 'all' && i.state !== f.state) return false;
  if (f.label && !i.labels.includes(f.label)) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!(`#${i.number} ${i.title}`.toLowerCase().includes(q))) return false;
  }
  return true;
}

function chainHtml(i) {
  const parts = [];
  parts.push(`<span class="node">aberta ${fmtD(i.created_at)}</span>`);
  for (const p of i.prs) {
    parts.push('<span class="arrow">→</span>');
    parts.push(`<a class="node" href="${prUrl(p.number)}" target="_blank" rel="noopener">PR #${p.number}${p.merged_at ? ' ✓ merged' : ` · ${p.state.toLowerCase()}`}</a>`);
  }
  for (const dp of i.deploys) {
    parts.push('<span class="arrow">→</span>');
    const ok = dp.result === 'healthy';
    parts.push(`<span class="node ${ok ? 'deploy' : 'rolled'}">● v${esc(dp.app_version || dp.sha)} · ${fmtD(dp.at)}</span>`);
  }
  if (i.prs.length === 0 && i.state === 'OPEN') parts.push('<span class="arrow">→</span><span class="node">sem PR ainda</span>');
  return parts.join('');
}

function commentsHtml(n) {
  const c = S.comments[n];
  if (!c) return '';
  if (c.loading) return '<div class="comments"><span class="ago">carregando comentários…</span></div>';
  if (c.error) return `<div class="comments"><span class="ago">comentários indisponíveis: ${esc(c.error)}</span></div>`;
  if (!c.list.length) return '<div class="comments"><span class="ago">sem comentários</span></div>';
  return `<div class="comments"><div class="k-label" style="margin-bottom:6px">comentários (${c.list.length})</div>` +
    c.list.map(cm => `
      <div class="comment">
        <div class="who">${esc(cm.author || '?')} <span class="ago">· ${ago(cm.created_at)}</span></div>
        <div class="md">${md(cm.body_md)}</div>
      </div>`).join('') + '</div>';
}

function issueCard(i, idx, prd = false) {
  const open = S.expIss.has(i.number);
  const lead = i.closed_at ? spanH(new Date(i.closed_at) - new Date(i.created_at)) : null;
  const meta = [];
  meta.push(`aberta ${fmtD(i.created_at)}`);
  if (i.closed_at) meta.push(`fechada ${fmtD(i.closed_at)} · ⏱ ${lead}`);
  if (i.assignees.length) meta.push(`👤 ${i.assignees.map(esc).join(', ')}`);
  if (i.criteria.total) meta.push(`✓ ${i.criteria.done}/${i.criteria.total} critérios`);
  const blocked = i.blocked_by.length
    ? `<span class="blocked">⛔ bloqueada por ${i.blocked_by.map(n => `<a href="${issUrl(n)}" target="_blank" rel="noopener">#${n}</a>`).join(', ')}</span>` : '';

  return `
  <article class="card iss lift rv ${prd ? 'prd-head' : ''}" style="--i:${idx}">
    <div class="iss-head" data-act="iss" data-n="${i.number}">
      ${prd ? '<span class="prd-tag">PRD</span>' : ''}
      <span class="inum">#${i.number}</span>
      <span class="ititle">${esc(i.title)}</span>
      ${i.labels.map(labelBadge).join('')}
      ${stateTag(i)}
    </div>
    <div class="iss-meta">${meta.map(m => `<span>${m}</span>`).join('')}${blocked}</div>
    <div class="chain">${chainHtml(i)}</div>
    ${open ? `
    <div class="iss-body">
      <a class="ghlink" href="${issUrl(i.number)}" target="_blank" rel="noopener">abrir no GitHub ↗</a>
      <div class="md" style="margin-top:10px">${md(i.body)}</div>
      ${commentsHtml(i.number)}
    </div>` : ''}
  </article>`;
}

function issueListHtml() {
  const iss = S.data.github.issues || [];
  const byN = Object.fromEntries(iss.map(i => [i.number, i]));
  const prds = iss.filter(i => i.is_prd).sort((a, b) => b.number - a.number);
  const used = new Set();
  let idx = 0;
  const groups = [];
  const f = S.fIssues;
  const filtroAtivo = !!(f.q || f.label || f.state !== 'all');

  for (const prd of prds) {
    used.add(prd.number);
    const kids = prd.children.map(n => byN[n]).filter(Boolean);
    kids.forEach(k => used.add(k.number));
    const kidsShown = kids.filter(matchIssue);
    if (!matchIssue(prd) && !kidsShown.length) continue;
    // colapsadas por padrão; filtro/busca ativos nunca escondem resultado
    const aberto = S.expPrd.has(prd.number) || (filtroAtivo && kidsShown.length > 0);
    const fechadas = kids.filter(k => k.state === 'CLOSED').length;
    const toggle = kids.length ? `
      <button class="fatias-toggle" data-act="prd" data-n="${prd.number}" aria-expanded="${aberto}">
        <span class="ft-caret" aria-hidden="true">${aberto ? '▾' : '▸'}</span>
        ${kids.length} fatia${kids.length === 1 ? '' : 's'} · ${fechadas} fechada${fechadas === 1 ? '' : 's'}
      </button>` : '';
    groups.push(`
      <section class="prd-group">
        ${issueCard(prd, idx++, true)}
        ${toggle}
        ${aberto && kidsShown.length ? `<div class="children">${kidsShown.map(k => issueCard(k, idx++)).join('')}</div>` : ''}
      </section>`);
  }

  const loose = iss.filter(i => !used.has(i.number)).filter(matchIssue)
    .sort((a, b) => b.number - a.number);
  if (loose.length) {
    groups.push(`
      <section class="prd-group">
        <div class="k-label rv" style="margin:4px 0 12px">issues avulsas</div>
        ${loose.map(l => issueCard(l, idx++)).join('')}
      </section>`);
  }
  return groups.join('') || '<div class="empty">nenhuma issue bate com o filtro</div>';
}

function renderIssues() {
  const iss = S.data.github.issues || [];
  const open = iss.filter(i => i.state === 'OPEN');
  const lead = leadAvg(iss);
  const labels = [...new Set(iss.flatMap(i => i.labels))].sort();
  const f = S.fIssues;
  let i = 0;
  const rv = () => `class="rv" style="--i:${i++}"`;

  return `
  ${sec('03', 'Issues, tudo que aconteceu', 'gh · PRD → fatias → PR → deploy')}
  <div class="grid g12" style="margin-bottom:6px">
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">issues</div><div class="v">${iss.length}</div><div class="s">desde ${fmtD(iss[iss.length - 1] && iss[iss.length - 1].created_at)}</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">abertas</div><div class="v" style="color:var(--green)">${open.length}</div><div class="s">${iss.length - open.length} fechadas</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">lead time médio</div><div class="v" style="font-size:30px; padding-top:6px">${lead ? spanH(lead) : '·'}</div><div class="s">da abertura ao fechamento</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">prontas p/ agente</div><div class="v" style="color:var(--coral)">${open.filter(x => x.labels.includes('ready-for-agent')).length}</div><div class="s">fila ready-for-agent</div></div></div>
  </div>

  <div class="controls rv" style="--i:${i++}">
    <button class="fchip ${f.state === 'all' ? 'on' : ''}" data-act="fstate" data-v="all">todas</button>
    <button class="fchip ${f.state === 'OPEN' ? 'on' : ''}" data-act="fstate" data-v="OPEN">abertas</button>
    <button class="fchip ${f.state === 'CLOSED' ? 'on' : ''}" data-act="fstate" data-v="CLOSED">fechadas</button>
    <select class="fsel" id="flabel">
      <option value="">label: todas</option>
      ${labels.map(l => `<option value="${esc(l)}" ${f.label === l ? 'selected' : ''}>${esc(l)}</option>`).join('')}
    </select>
    <input class="search" id="fq" type="search" placeholder="buscar por título ou #número…" value="${esc(f.q)}">
  </div>
  <div id="ilist">${issueListHtml()}</div>`;
}

function wireIssues() {
  const q = $('#fq'), sel = $('#flabel');
  if (q) q.addEventListener('input', () => { S.fIssues.q = q.value; refreshIssueList(); });
  if (sel) sel.addEventListener('change', () => { S.fIssues.label = sel.value; refreshIssueList(); });
}

function refreshIssueList() {
  const el = $('#ilist');
  if (el) {
    el.innerHTML = issueListHtml();
    if (_ioList) _ioList.disconnect();
    _ioList = revealOnScroll(el, '.rv');
  }
}

async function ensureComments(n) {
  if (S.comments[n]) return;
  S.comments[n] = { loading: true };
  try {
    const r = await fetch('/api/issue/' + n);
    const j = await r.json();
    S.comments[n] = { loading: false, list: j.comments || [], error: j.error };
  } catch (e) {
    S.comments[n] = { loading: false, list: [], error: String(e) };
  }
  if (S.tab === 'issues') refreshIssueList();
}

/* ---------- DEPLOYS ---------- */

function deployCard(dp, idx) {
  const open = S.expDep.has(idx);
  const ok = dp.result === 'healthy';
  const maxDur = Math.max(...S.data.history.map(x => x.duration_seconds || 0), 1);
  const cl = S.data.changelog.find(c =>
    (dp.app_version && c.version === dp.app_version) || (c.sha && dp.sha && c.sha === dp.sha));

  const chipsResumo = [
    `<span class="badge ${ok ? 'b-green' : 'b-red'}">${esc(dp.result || '?')}</span>`,
    ...(dp.migrations_applied || []).map(m => `<span class="badge b-coral">⛁ ${esc(m)}</span>`),
    ...(dp.pr_numbers || []).map(n => `<a class="chip" href="${prUrl(n)}" target="_blank" rel="noopener">PR #${n}</a>`),
    ...(dp.issue_numbers || []).map(n => `<a class="chip" href="${issUrl(n)}" target="_blank" rel="noopener">#${n}</a>`),
    dp.rollback_target_sha ? `<span class="badge b-red">rollback → ${esc(dp.rollback_target_sha)}</span>` : '',
  ].filter(Boolean).join('');
  const chipsTech = [
    dp.sha ? `<a class="chip" href="${shaUrl(dp.sha)}" target="_blank" rel="noopener">${esc(dp.sha)}</a>` : '',
    ...(dp.scope || []).map(s => `<span class="chip">${esc(s)}</span>`),
  ].filter(Boolean).join('');

  return `
  <div class="tl-item rv ${ok ? '' : 'bad'}" style="--i:${Math.min(idx, 12)}">
    <article class="card dep lift">
      <div class="dep-head" data-act="dep" data-i="${idx}">
        <span class="dep-ver ${dp.app_version ? '' : 'unversioned'}">${dp.app_version ? 'v' + esc(dp.app_version) : esc(dp.sha || '·')}</span>
        <span class="dep-subject">${esc(dp.subject || dp.raw_subject || '')}</span>
        <span class="dep-when">${esc(fmtDT(dp.at))}</span>
      </div>
      <div class="dep-meta">${chipsResumo}</div>
      ${dp.duration_seconds ? `
      <div class="durbar">
        <span class="rail"><span class="fill" style="width:${Math.round((dp.duration_seconds / maxDur) * 100)}%"></span></span>
        <span class="t">${durS(dp.duration_seconds)}</span>
      </div>` : ''}
      ${open ? `
      <div class="dep-body">
        ${chipsTech ? `<div class="dep-meta" style="padding:0 0 12px">${chipsTech}</div>` : ''}
        ${dp.notes ? `<p class="dep-notes">${esc(dp.notes)}</p>` : ''}
        ${(dp.env_changes || []).length ? `<p class="dep-notes mono" style="font-size:12px">env: ${dp.env_changes.map(e => `${esc(e.service)} ${esc(e.action)} ${e.keys.map(esc).join(', ')}`).join(' · ')}</p>` : ''}
        ${cl && cl.body_md ? `<div class="k-label" style="margin:14px 0 6px">changelog</div><div class="md">${md(cl.body_md)}</div>` : ''}
      </div>` : ''}
    </article>
  </div>`;
}

function renderDeploys() {
  const dep = S.data.history;
  const healthy = dep.filter(x => x.result === 'healthy');
  const durs = dep.map(x => x.duration_seconds).filter(x => x != null);
  const avg = durs.length ? durs.reduce((a, b) => a + b, 0) / durs.length : null;
  const first = dep[dep.length - 1], last = dep[0];
  let i = 0;
  const rv = () => `class="rv" style="--i:${i++}"`;

  return `
  ${sec('01', 'Deploys & releases', 'history.json + CHANGELOG.md')}
  <div class="grid g12" style="margin-bottom:6px">
    <div class="card lift sp3 has-desc" ${rv()}><div class="stat"><div class="k">deploys</div><div class="v">${dep.length}</div><div class="s">${fmtD(first && first.at)} → ${fmtD(last && last.at)}</div></div><span class="desc-pop" role="tooltip">Total de deploys registrados no history.json, do primeiro ao mais recente.</span></div>
    <div class="card lift sp3 has-desc" ${rv()}><div class="stat"><div class="k">saudáveis</div><div class="v" style="color:var(--green)">${dep.length ? Math.round(healthy.length / dep.length * 100) : 0}<small>%</small></div><div class="s">${dep.length - healthy.length} com problema</div></div><span class="desc-pop" role="tooltip">Percentual de deploys que passaram no health check. O restante teve falha ou rollback.</span></div>
    <div class="card lift sp3 has-desc" ${rv()}><div class="stat"><div class="k">build médio</div><div class="v" style="font-size:30px; padding-top:6px">${avg ? durS(avg) : '·'}</div><div class="s">duração por deploy</div></div><span class="desc-pop" role="tooltip">Duração média do build no Coolify entre todos os deploys.</span></div>
    <div class="card lift sp3 has-desc" ${rv()}><div class="k-label">duração (antigo → recente)</div>${spark([...durs].reverse())}<span class="desc-pop" role="tooltip">Cada ponto é a duração de um deploy, do mais antigo ao recente. Ponto baixo é build rápido.</span></div>
  </div>
  <div class="timeline">${dep.map((d, idx) => deployCard(d, idx)).join('')}</div>`;
}

/* ---------- MAPA ---------- */

/* o diagrama ER parseado do SCHEMA (capa da aba e fonte das relações) */
function erDiag() {
  const schema = (S.data.snapshots || []).find(s => s.name === 'SCHEMA');
  return schema && (schema.diagramas || []).find(d => d.tipo === 'er');
}

/* capa da aba: ER interativo desenhado pelo renderer próprio (ADR 0025).
   A estrutura vem parseada do /api/data: a SPA não parseia Mermaid. */
function erCapaHtml() {
  const er = erDiag();
  const svg = er && renderDiagrama(er);
  if (!svg) return '';   // sem ER parseado: a aba segue só com as pills
  return `
  <div class="card er-capa rv ${S.erFull ? 'er-full' : ''}" id="er-capa" style="--i:1">
    <div class="er-capa-head">
      <span class="k-label">banco de dados · ${er.tabelas.length} tabelas · ${er.relacoes.length} relações</span>
      <span class="er-capa-hint">todas as colunas aparentes · hover destaca as relações · clique no nome abre a ficha</span>
      <button type="button" class="fchip er-expandir" data-act="erfull">${S.erFull ? '✕ fechar' : '⛶ tela cheia'}</button>
    </div>
    ${svg}
  </div>`;
}

/* contexto que as capas de área recebem (valores puros, sem o estado S) */
function areaCtx() {
  const er = erDiag();
  return {
    er,
    relacoes: (er && er.relacoes) || [],
    rotasQ: S.rotasQ,
    entTab: S.entTab,
    aoBuscarRota: q => { S.rotasQ = q; },
  };
}

function renderMapa() {
  const snaps = S.data.snapshots;
  if (!S.mapaDoc || !snaps.find(s => s.name === S.mapaDoc)) S.mapaDoc = snaps[0] && snaps[0].name;
  const cur = snaps.find(s => s.name === S.mapaDoc);
  const capa = cur && renderArea(cur, areaCtx());
  const fonte = cur ? `
  <details class="techbox fonte-doc rv"><summary>ver fonte (docs/spec/snapshots/${esc(cur.name)}.md)</summary>
    <div class="techbox-body md">${md(cur.body_md)}</div>
  </details>` : '';
  const corpo = !cur ? '<div class="empty">sem snapshots</div>'
    : capa != null ? capa + fonte
      : `<div class="card md rv" style="--i:4" id="snapdoc">${md(cur.body_md)}</div>`;
  return `
  ${sec('04', 'Mapa da app', 'docs/spec/snapshots · regenerado a cada deploy')}
  ${erCapaHtml()}
  <div class="docpills rv" style="--i:2">
    ${snaps.map(s => `<button class="fchip ${s.name === S.mapaDoc ? 'on' : ''}" data-act="doc" data-doc="${esc(s.name)}">${esc(s.name)}</button>`).join('')}
  </div>
  ${cur ? `<div class="docmeta rv" style="--i:3">gerado em ${esc(fmtDT(cur.generated_at))} · ${cur.lines} linhas · <span class="mono">docs/spec/snapshots/${esc(cur.name)}.md</span></div>` : ''}
  ${corpo}`;
}

/* troca cada bloco ```mermaid do doc pelo renderer próprio (ADR 0025), na
   ordem em que o coletor parseou. Tipo sem renderer (ou fora do subset) fica
   no <pre> como código cru, o fallback definitivo. */
function desenharDiagramas(root) {
  const doc = (S.data.snapshots || []).find(s => s.name === S.mapaDoc);
  const diagramas = (doc && doc.diagramas) || [];
  const blocos = [...root.querySelectorAll('#snapdoc code.language-mermaid')];
  // o pareamento é posicional (i-ésimo bloco ↔ i-ésima estrutura); se o marked
  // e o coletor divergirem na contagem, melhor nenhum desenho que o desenho errado
  if (blocos.length !== diagramas.length) return;
  blocos.forEach((c, i) => {
    const html = renderDiagrama(diagramas[i]);
    const pre = c.closest('pre');
    if (!html || !pre) return;
    const box = document.createElement('div');
    box.className = 'diagrama-box';
    box.innerHTML = html;
    pre.replaceWith(box);
  });
}

/* ---------- DOMÍNIO ---------- */

function renderDominio() {
  const adrs = S.data.adrs;
  return `
  ${sec('05', 'Decisões de arquitetura', 'docs/adr · curado por humano')}
  <div class="grid g12">
    ${adrs.map((a, i) => `
      <article class="card adr lift sp6 rv" style="--i:${i}" data-act="adr" data-i="${i}">
        <span class="ghostnum">${String(a.number ?? '').padStart(2, '0')}</span>
        <h3>${esc(a.title)}</h3>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
          ${adrStatusBadge(a.status)}${adrPointerBadge(a)}
          <span class="file">${esc(a.file)}</span>
        </div>
        ${S.expAdr.has(i) ? `<div class="adr-body md">${md(a.body_md)}</div>` : ''}
      </article>`).join('')}
  </div>
  ${sec('06', 'Glossário do domínio', 'CONTEXT.md · o que as palavras significam aqui')}
  <div class="card md rv">${md(S.data.context_md || '_CONTEXT.md não encontrado_')}</div>`;
}

/* ---------- GUIA (fluxograma do pipeline) ---------- */

const FLX_ICONS = {
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 2a7 7 0 0 0-4 12c1 1 1 2 1 3h6c0-1 0-2 1-3a7 7 0 0 0-4-12z"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="3.6" cy="6" r="1"/><circle cx="3.6" cy="12" r="1"/><circle cx="3.6" cy="18" r="1"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
  file: '<path d="M7 2h8l4 4v16H7z"/><path d="M15 2v4h4"/><path d="M10 12h6M10 16h6"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="9" r="2"/><path d="M6 7v10M6 13h6a4 4 0 0 0 4-4"/>',
  claim: '<path d="M6 3h12v19l-6-4-6 4z"/>',
  flask: '<path d="M9 2h6M10 2v6l-5 10a2 2 0 0 0 2 4h10a2 2 0 0 0 2-4l-5-10V2"/><path d="M7.5 15h9"/>',
  rocket: '<path d="M12 2c3 2.5 4.5 6.5 4.5 10L14 15h-4l-2.5-3c0-3.5 1.5-7.5 4.5-10z"/><path d="M9.5 15L7 19M14.5 15L17 19"/><circle cx="12" cy="9" r="1.4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.5-4.5"/>',
  shield: '<path d="M12 2l8 3v6c0 5-3.5 8.5-8 10.5C7.5 19.5 4 16 4 11V5z"/><path d="M9 11.5l2 2 4-4"/>',
  check: '<path d="M4 12.5l5 5L20 6.5"/>',
  usercheck: '<circle cx="9" cy="7" r="4"/><path d="M2 21c0-4 3.5-6 7-6c1.4 0 2.7.3 3.8.9"/><path d="M15.5 12l2 2 4-4"/>',
  cloud: '<path d="M7 18a4 4 0 0 1-.5-8 6 6 0 0 1 11.5 1.5A3.5 3.5 0 0 1 18 18"/><path d="M12 21v-8M9 15l3-3 3 3"/>',
  live: '<circle cx="12" cy="12" r="2.4"/><path d="M7.5 7.5a6 6 0 0 0 0 9M16.5 7.5a6 6 0 0 1 0 9"/>',
  rewind: '<path d="M11 6L5 12l6 6M19 6l-6 6 6 6"/>',
  camera: '<path d="M4 8h3l1.5-2.5h7L17 8h3v12H4z"/><circle cx="12" cy="13" r="3.4"/>',
};
const flxIcon = n => (n && FLX_ICONS[n])
  ? `<svg class="flx-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${FLX_ICONS[n]}</svg>`
  : '';

/* respaldo de cada skill: resumo curto + de onde vem (SKILL.md real ou skill nativa) */
function flxPop(o) {
  const title = o.cmd || o.t;
  const src = o.src
    ? `<div class="flx-pop-src">fonte <code>${o.src}</code></div>`
    : `<div class="flx-pop-src flx-pop-rule">${o.rule || 'regra do fluxo'}</div>`;
  return `<div class="flx-pop ${o.up ? 'flx-pop-up' : ''}" role="tooltip">
    <div class="flx-pop-h">${flxIcon(o.icon)}<span>${title}</span></div>
    <p>${o.tip}</p>${src}</div>`;
}
function flxNode(o) {
  const head = o.cmd
    ? `<span class="cmdpill ${o.hot ? 'cmdpill-hot' : ''}">${o.cmd}</span>`
    : `<span class="flx-et">${o.t}</span>`;
  const sub = o.sub ? `<div class="flx-nd">${o.sub}</div>` : '';
  const inter = o.tip ? 'tabindex="0" data-tip' : '';
  return `<div class="flx-node ${o.cls || ''}" ${inter} style="--d:${o.d || 0}">
    ${flxIcon(o.icon)}<div class="flx-nbody">${head}${sub}</div>${o.tip ? flxPop(o) : ''}</div>`;
}

function fluxoHtml() {
  let d = 0;
  const conn = (cls = '', label = '') =>
    `<div class="flx-conn ${cls}" style="--d:${d++}"><i></i><b></b>${label ? `<em>${label}</em>` : ''}</div>`;
  const phase = (n, txt) =>
    `<div class="flx-phase" style="--d:${d++}"><span class="flx-phase-n">${n}</span>${txt}</div>`;
  return `
  <div class="flx">
    ${phase('1', 'planejar')}
    <div class="flx-entries">
      <div class="flx-lane flx-left">
        ${flxNode({ t: 'Tenho uma ideia nova', sub: 'feature · melhoria · mudança', icon: 'bulb', cls: 'flx-is-entry', d: d++,
          tip: 'A porta de entrada quando o trabalho ainda não existe: uma feature, melhoria ou mudança que vira plano, PRD e issues.', rule: 'ponto de partida do fluxo' })}
        ${conn()}
        ${flxNode({ cmd: '/grill-with-docs', sub: 'afia a ideia contra o domínio', icon: 'target', d: d++,
          tip: 'Sessão de grilling: te entrevista sem dó sobre cada ramo do plano, uma decisão por vez com recomendação destacada, desafiando contra o domínio. Atualiza CONTEXT.md e ADRs inline conforme as decisões fecham.', src: '.claude/skills/grill-with-docs' })}
        ${conn()}
        ${flxNode({ cmd: '/to-prd', sub: 'vira 1 issue PRD (ready-for-agent)', icon: 'file', d: d++,
          tip: 'Sintetiza a conversa atual num PRD (não te entrevista de novo): problema, solução, histórias de usuário e critérios de aceite, em pt-BR com a terminologia do CONTEXT.md. Publica como 1 issue ready-for-agent no GitHub.', src: '.claude/skills/to-prd' })}
        ${conn()}
        ${flxNode({ cmd: '/to-issues', sub: 'corta em N fatias verticais', icon: 'branch', d: d++,
          tip: 'Quebra o PRD em fatias verticais independentes (tracer bullets), cada uma pegável sozinha, com tamanho (P/M/G) e "Bloqueada por: #X" explícito.', src: '.claude/skills/to-issues' })}
        ${conn()}
      </div>
      <div class="flx-lane">
        ${flxNode({ t: 'Vou pegar da fila', sub: 'issue já especificada', icon: 'list', cls: 'flx-is-entry', d: 1,
          tip: 'Atalho pra quando a issue já está especificada e triada: você entra direto na fila, sem passar pelo planejamento.', rule: 'ponto de partida do fluxo' })}
        ${conn('flx-tall')}
      </div>
    </div>

    <div class="flx-fila" tabindex="0" data-tip style="--d:${d++}">
      ${flxIcon('list')}
      <div class="flx-nbody"><div class="flx-ft">Fila de issues <code>ready-for-agent</code></div><div class="flx-es">sem dono · sem bloqueio aberto</div></div>
      ${flxPop({ t: 'Fila ready-for-agent', icon: 'list', tip: 'Só entram issues sem dono e sem bloqueio aberto ("Bloqueada por: #X"). É daqui que cada sessão puxa trabalho, com claim atômico pra não colidir.', src: 'docs/agents/issue-tracker.md' })}
    </div>
    ${conn('flx-dash', 'claim + 1 worktree')}

    ${phase('2', 'desenvolver · em paralelo')}
    <div class="flx-group" style="--d:${d++}">
      <div class="flx-cap"><span class="flx-em">×N em paralelo</span>, 1 worktree por issue</div>
      <div class="flx-row">
        ${flxNode({ cmd: '/pegar-issue', sub: 'claim + branch', icon: 'claim', d: d++,
          tip: 'Entry point de desenvolvimento: pega uma issue da fila, dá claim atômico (label + assignee) pra não colidir com sessões paralelas, cria a branch e carrega a spec no contexto pro /tdd.', src: '.claude/skills/pegar-issue' })}
        <span class="flx-chev">›</span>
        ${flxNode({ cmd: '/tdd', sub: 'red → green → refactor', icon: 'flask', d: d++,
          tip: 'Red-green-refactor: cada critério de aceite da issue vira um teste que falha primeiro; o código vem só pra fazê-lo passar. Nomes de teste descrevem o comportamento de domínio em pt-BR.', src: '.claude/skills/tdd' })}
        <span class="flx-chev">›</span>
        ${flxNode({ cmd: '/ship', sub: 'roda os 3 gates → PR', icon: 'rocket', d: d++,
          tip: 'Orquestra a mudança end-to-end: branch, commit, PR, 3 gates, approval, merge e deploy num comando só. Dispara /code-review e /security-review automaticamente. Trabalho ancorado na issue (Closes #N fecha no merge).', src: '.claude/skills/ship' })}
      </div>

      <div class="flx-subcap">o <code>/ship</code> dispara os 3 gates, em sequência</div>
      <div class="flx-gaterow">
        ${flxNode({ cmd: '/code-review', sub: 'bugs + limpezas', icon: 'search', cls: 'flx-gate-step', d: d++,
          tip: 'Revisa o diff atual atrás de bugs de correção e limpezas de reuso, simplificação e eficiência, no nível de esforço pedido. Primeiro gate do /ship.', src: 'Claude Code (skill nativa)' })}
        <span class="flx-chev flx-chev-sm">›</span>
        ${flxNode({ cmd: '/security-review', sub: 'segurança do diff', icon: 'shield', cls: 'flx-gate-step flx-gate-hot', hot: true, d: d++,
          tip: 'Revisão de segurança das mudanças pendentes da branch. Segundo gate do /ship. Atenção conhecida: em worktree lê o diff da árvore principal (incidente #112); o agente escopa o diff manualmente.', src: 'Claude Code (skill nativa)' })}
        <span class="flx-chev flx-chev-sm">›</span>
        ${flxNode({ cmd: 'CI verde', sub: 'testes + lint', icon: 'check', cls: 'flx-gate-step flx-gate-ci', d: d++,
          tip: 'A suite de testes e o lint (ruff no backend, ESLint no front) precisam ficar verdes no GitHub Actions antes do merge. Terceiro gate.', src: '.github/workflows' })}
      </div>
    </div>
    ${conn()}

    ${phase('3', 'revisão humana & deploy')}
    ${flxNode({ t: 'Gate humano: OK de merge', sub: 'push na main é ação humana · merge sequencial', icon: 'usercheck', cls: 'flx-humangate', d: d++,
      tip: 'O único toque humano obrigatório: você aprova o lote uma vez. Push na main é ação humana porque merge dispara deploy em produção; o merge é sequencial, com bump de versão um a um.', rule: 'regra: push na main = ação humana' })}
    ${conn()}

    ${flxNode({ cmd: '/deploy · Coolify', sub: 'build a partir da main → health check', icon: 'cloud', cls: 'flx-wide', d: d++,
      tip: 'Deploy via Coolify: build a partir da main, health check e rollback automático se falhar. Lê e escreve docs/spec/deploy/*.json e faz prepend no CHANGELOG.', src: '.claude/skills/deploy' })}
    ${conn()}

    <div class="flx-fork" style="--d:${d++}">
      ${flxNode({ t: 'No ar (produção)', sub: 'health verde · /snapshot atualiza o mapa', icon: 'live', cls: 'flx-out flx-ok', up: true,
        tip: 'Health check verde: a versão nova assume produção. Logo depois o /snapshot regenera o mapa vivo da app (rotas, entidades, schema) direto do código.', src: '.claude/skills/snapshot' })}
      ${flxNode({ t: 'Rollback automático', sub: 'health vermelho · volta à versão anterior', icon: 'rewind', cls: 'flx-out flx-bad', up: true,
        tip: 'Health check vermelho: o /deploy reverte sozinho pra versão anterior. Produção nunca fica quebrada esperando intervenção.', src: '.claude/skills/deploy' })}
    </div>
  </div>`;
}

function renderGuia() {
  return `
  ${sec('', 'Guia', 'o fluxo inteiro, do brainstorm ao deploy')}
  <div class="card rv guia-flow-card">
    <h2 class="guia-flow-title">O fluxo inteiro, num desenho</h2>
    ${fluxoHtml()}
  </div>`;
}

/* ---------- eventos ---------- */

function writeClipboard(text, done) {
  const fallback = () => {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch { /* sem clipboard */ }
    ta.remove();
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  } else fallback();
}

function copyCmd(btn) {
  const pre = document.getElementById(btn.dataset.cp);
  writeClipboard(pre ? pre.innerText : '', () => {
    btn.classList.add('ok');
    const txt = btn.querySelector('.cc-txt');
    const prev = txt ? txt.textContent : '';
    if (txt) txt.textContent = 'copiado ✓';
    setTimeout(() => { btn.classList.remove('ok'); if (txt) txt.textContent = prev; }, 1400);
  });
}

view.addEventListener('click', e => {
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const link = e.target.closest('a');
  if (link && link !== t) return;          // link real dentro do card → deixa navegar
  const act = t.dataset.act;
  if (act === 'tip') {
    document.querySelectorAll('.tip.open').forEach(x => {
      if (x !== t) { x.classList.remove('open'); x.setAttribute('aria-expanded', 'false'); }
    });
    const on = t.classList.toggle('open');
    t.setAttribute('aria-expanded', on ? 'true' : 'false');
  } else if (act === 'copy') {
    copyCmd(t);
  } else if (act === 'copytxt') {
    if (t.classList.contains('ok')) return;  // clique duplo: não capturar o "copiado ✓" como prev
    writeClipboard(t.dataset.txt || '', () => {
      const prev = t.innerHTML;
      t.classList.add('ok');
      t.textContent = 'copiado ✓';
      setTimeout(() => { t.classList.remove('ok'); t.innerHTML = prev; }, 1400);
    });
  } else if (act === 'iss') {
    const n = Number(t.dataset.n);
    if (S.expIss.has(n)) S.expIss.delete(n);
    else { S.expIss.add(n); ensureComments(n); }
    refreshIssueList();
  } else if (act === 'prd') {
    const n = Number(t.dataset.n);
    S.expPrd.has(n) ? S.expPrd.delete(n) : S.expPrd.add(n);
    refreshIssueList();
  } else if (act === 'dep') {
    const i = Number(t.dataset.i);
    S.expDep.has(i) ? S.expDep.delete(i) : S.expDep.add(i);
    render();
  } else if (act === 'adr') {
    const i = Number(t.dataset.i);
    S.expAdr.has(i) ? S.expAdr.delete(i) : S.expAdr.add(i);
    render();
  } else if (act === 'fstate') {
    S.fIssues.state = t.dataset.v;
    render();
  } else if (act === 'doc') {
    S.mapaDoc = t.dataset.doc;
    render();
  } else if (act === 'erfull') {
    S.erFull = !S.erFull;
    render();
  } else if (act === 'ficha') {
    // salto do popover do mapa pra ficha completa da tabela em ENTIDADES
    S.mapaDoc = 'ENTIDADES';
    S.entTab = t.dataset.t;
    S.erFull = false;
    render();
  } else if (act === 'enttab') {
    S.entTab = t.dataset.t;
    render();
  } else if (act === 'gotab') {
    S.fIssues = { state: 'all', label: t.dataset.label || '', q: '' };
    setTab(t.dataset.go);
  }
});

$('#tabs').addEventListener('click', e => {
  const b = e.target.closest('button[data-tab]');
  if (b) setTab(b.dataset.tab);
});

window.addEventListener('hashchange', () => {
  const t = location.hash.slice(1);
  if (t && t !== S.tab) setTab(t);
});

/* tooltips: fecham com Escape ou clique fora; Escape também sai da tela cheia */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeTips();
  if (S.erFull) { S.erFull = false; render(); }
});
document.addEventListener('click', e => { if (!e.target.closest('.tip')) closeTips(); });

/* ---------- boot ---------- */

(async function init() {
  const t = location.hash.slice(1);
  if (t) S.tab = TAB_ALIAS[t] || (TABS.includes(t) ? t : S.tab);
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
  await load(false);
  setInterval(tick, 5000);
  setInterval(() => load(false, true), 60000);
})();
