'use strict';

/* Fluxo vivo — SPA vanilla. Lê /api/data (agregado) e /api/issue/<n> (comentários lazy). */

import { tip, copyBlock, techDetails, closeTips, reduceMotion } from './ui.js';
import { SETUP, OSES, OS_LABEL } from './content/setup.js';
import { METODO, BASTIDORES } from './content/guia.js';

const S = {
  data: null,
  tab: 'plano',
  os: null,
  fIssues: { state: 'all', label: '', q: '' },
  expIss: new Set(),
  expDep: new Set(),
  expAdr: new Set(),
  comments: {},
  mapaDoc: null,
  mermaidP: null,
};

const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');

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
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getDate()} ${MES[d.getMonth()]}`;
}
function fmtDT(iso) {
  if (!iso) return '—';
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
  if (sec == null) return '—';
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
    <polyline points="${poly}" fill="none" stroke="#2B2E7E" stroke-width="1.6" stroke-linejoin="round"/>
    <circle cx="${lx}" cy="${ly}" r="3.2" fill="#DE5630"/></svg>`;
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
}

function renderBanner() {
  const err = S.data.github && S.data.github.error;
  $('#banner').innerHTML = err
    ? `<div class="banner"><b>GitHub indisponível</b> — ${esc(err)}<br>Mostrando só os dados locais (deploys, snapshots, ADRs, glossário).</div>`
    : '';
}

function renderFoot() {
  $('#foot').innerHTML = `
    <span>tools/workflow-dashboard · somente leitura · fontes: <span class="mono">gh</span> + docs/spec + git</span>
    <span>coletado às ${esc(fmtDT(S.data.generated_at))} · <a href="${esc(S.data.repo_url)}" target="_blank" rel="noopener">${esc(S.data.repo_slug)} ↗</a></span>`;
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
  if (S.tab === 'mapa') mermaidify(view);
}

const sec = (n, title, hint = '') =>
  `<div class="sec rv"><span class="n">${n}</span><h2>${title}</h2>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;

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
};

function fatiaCard(f) {
  const e = ESTADO_FATIA[f.estado] || ESTADO_FATIA.pronta;
  const bloqueio = f.estado === 'bloqueada' && f.bloqueada_por.length
    ? `<span class="fbloq">⛔ espera ${f.bloqueada_por.map(n =>
      `<a href="${issUrl(n)}" target="_blank" rel="noopener">#${n}</a>`).join(', ')}</span>` : '';
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
    <div class="fmeta">${e.badge}${f.tamanho ? labelBadge('fatia:' + f.tamanho) : ''}${tempoTipicoHtml(f.tempo_tipico)}${bloqueio}</div>
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
      <a class="leva-title" href="${esc(leva.prd.url)}" target="_blank" rel="noopener">#${leva.prd.number} — ${esc(leva.prd.title)} ↗</a>
      <div class="leva-chips">${chips}</div>
    </div>
    ${avisos}
    ${leva.ondas.length ? `<div class="ondas">${leva.ondas.map(ondaHtml).join('')}</div>`
      : '<div class="empty">todas as fatias desta leva foram entregues — feche o PRD ou abra a próxima leva</div>'}
    ${feitas}
  </section>`;
}

function renderPlano() {
  const cab = sec('', 'Plano', 'a leva atual, em ondas de execução');
  const p = S.data.plano;
  if (!p) {
    return `${cab}<div class="empty">O Plano lê as issues pelo <span class="mono">gh</span>, que está indisponível agora — veja o aviso no topo. As outras abas seguem com os dados locais.</div>`;
  }
  if (p.erro) return `${cab}<div class="banner"><b>Plano indisponível</b> — ${esc(p.erro)}</div>`;
  if (!p.levas.length) {
    return `${cab}
    <div class="card plano-vazio rv">
      <h3>Nenhum PRD ativo agora.</h3>
      <p>O plano nasce do pipeline: lapide a ideia, publique o PRD e corte em fatias — esta aba desenha o resto sozinha.</p>
      ${copyBlock('/grill-with-docs\n/to-prd\n/to-issues', { lang: 'text', label: 'numa sessão claude, na ordem' })}
    </div>`;
  }
  const lead = `<p class="lead rv">As fatias do PRD ativo, organizadas em <b>ondas</b>${tip('onda')} pela dependência:
    o que divide uma onda anda <b>em paralelo</b> — cada sessão pega uma fatia (claim atômico${tip('claim atômico')},
    1 worktree por issue${tip('worktree')}). Copie o comando de um card <b>pronta</b> e cole num terminal novo.</p>`;
  return cab + lead + p.levas.map(levaHtml).join('');
}

/* ---------- PRODUÇÃO (estado de produção + timeline de deploys) ---------- */

function renderProducao() {
  return renderAgora() + renderDeploys();
}

function renderAgora() {
  const d = S.data, st = d.state || {}, run = st.last_run || {};
  const dep0 = d.history[0] || {};
  const git = d.git || {};
  const mig = st.migrations || {};
  const stack = (d.project || {}).stack || {};
  let i = 0;
  const rv = () => `class="rv" style="--i:${i++}"`;

  const sig = securitySignal(st);

  const svcResumo = (st.services || []).map(s => `
    <div class="svc-row"><span class="svc-name"><span class="dot ${s.status === 'healthy' ? 'ok pulse' : 'bad'}"></span>${esc(s.id)}</span>
      <span class="svc-meta">no ar ${ago(s.last_deploy_at)}</span></div>`).join('');
  const svcTech = (st.services || []).map(s => `
    <div class="svc-row"><span class="svc-name mono">${esc(s.id)}</span>
      <span class="svc-meta">${s.last_health_check && s.last_health_check.latency_ms != null ? s.last_health_check.latency_ms + 'ms · ' : ''}${s.last_deploy_sha ? `<a href="${shaUrl(s.last_deploy_sha)}" target="_blank" rel="noopener">${esc(s.last_deploy_sha)}</a>` : '—'}</span></div>`).join('');

  const gateList = st.gates || [];
  const okN = gateList.filter(g => g.status === 'ok').length;
  const gateFlag = gateList.some(g => g.status === 'fail') ? ' · <span style="color:var(--red)">há reprovação</span>'
    : gateList.some(g => g.status === 'warn') ? ' · <span style="color:var(--amber)">com ressalva</span>' : '';
  const gatesTech = gateList.map(g => {
    const cls = { ok: 'ok', warn: 'warn', fail: 'bad', skip: 'muted' }[g.status] || 'muted';
    return `<div class="gate"><span class="dot ${cls}"></span><span>${esc(g.name)}</span></div>`;
  }).join('');

  const actions = (st.next_actions || []).map(a => `
    <div class="action a-${esc(a.kind)}">
      <h4>${a.kind === 'ok' ? '✓' : a.kind === 'warn' ? '⚠' : 'ℹ'} ${esc(a.title)}</h4>
      <p>${esc(a.text)}</p>
    </div>`).join('');

  const commits = (git.commits || []).slice(0, 8).map(c =>
    `<li><span class="sha">${esc(c.sha)}</span><span class="s">${esc(c.subject)}</span></li>`).join('');
  const staleHint = git.stale_hint
    ? `<div class="git-stale">⟳ ${git.on_main ? '' : `você está na branch <b>${esc(git.branch)}</b> (não <b>main</b>) — `}${git.dirty ? `${git.dirty} arquivo(s) modificado(s) localmente. ` : ''}produção e deploys vêm da origin/main (sempre frescos); mapa e domínio vêm do seu clone${git.on_main ? '.' : ' — rode <code>git pull</code> no main para atualizá-los.'}</div>`
    : '';

  const stackRows = Object.entries(stack).map(([k, v]) =>
    `<div class="gate"><span class="dot info"></span><span><b>${esc(k)}</b> — ${esc(v)}</span></div>`).join('');

  return `
  ${sec('01', 'Estado de produção', `state.json · ${ago(st.updated_at)}`)}
  <div class="grid g12">
    <div class="card lift sp4 hero-version" ${rv()}>
      <div class="stat"><div class="k">em produção</div>
      <div class="v">v${esc(st.last_app_version || '?')}</div>
      <div class="s">${run.result === 'healthy' ? '🟢' : '🔴'} ${esc(run.result || '?')} · ${ago(dep0.at)}</div></div>
    </div>
    <div class="card lift sp4 sec-flag sec-${sig.cls}" ${rv()}>
      <div class="k-label">segurança</div>
      <div class="sec-big"><span class="dot ${sig.cls} ${sig.cls === 'ok' ? 'pulse' : ''}"></span><b>${sig.status ? esc(sig.status.toUpperCase()) : '—'}</b></div>
      <div class="s">${esc(sig.label)}</div>
    </div>
    <div class="card lift sp4" ${rv()}>
      <div class="k-label">serviços</div><div class="svc">${svcResumo || '<div class="empty">—</div>'}</div>
      ${techDetails('<div class="svc">' + svcTech + '</div>', 'latência e SHA')}
    </div>

    <div class="card lift sp4" ${rv()}>
      <div class="k-label">último deploy</div>
      <p class="agora-subject">${esc(dep0.subject || '—')}</p>
      <div class="agora-deprow">
        <span class="badge ${dep0.result === 'healthy' ? 'b-green' : 'b-red'}">${esc(dep0.result || '?')}</span>
        <span class="ago">${ago(dep0.at)}</span>
      </div>
      ${techDetails(`<div style="display:flex; gap:7px; flex-wrap:wrap; margin-bottom:8px">${dep0.sha ? `<a class="chip" href="${shaUrl(dep0.sha)}" target="_blank" rel="noopener">${esc(dep0.sha)}</a>` : ''}${(dep0.scope || []).map(s => `<span class="chip">${esc(s)}</span>`).join('')}</div><div class="s mono">${esc(fmtDT(dep0.at))} · build ${durS(dep0.duration_seconds)}</div>`, 'SHA, escopo e build')}
    </div>
    <div class="card lift sp4" ${rv()}>
      <div class="k-label">gates do último ship</div>
      <div class="gate-resumo">${gateList.length ? `<b>${okN}/${gateList.length}</b> gates ok${gateFlag}` : 'sem gates registrados'}</div>
      ${techDetails(gatesTech, 'ver cada gate')}
    </div>
    <div class="card lift sp4" ${rv()}><div class="k-label">próximas ações</div><div style="margin-top:12px">${actions || '<div class="empty">nada pendente</div>'}</div></div>

    <div class="card lift sp6" ${rv()}>
      <div class="k-label">git local</div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px">
        <span class="capsule"><b>${esc(git.branch || '?')}</b></span>
        <span class="capsule">${git.dirty ?? '?'} modificados</span>
      </div>
      ${staleHint}
      ${techDetails('<ul class="commits">' + commits + '</ul>', 'últimos commits')}
    </div>
    <div class="card lift sp6" ${rv()}>
      <div class="k-label">banco & stack</div>
      <div class="gate-resumo"><b>${mig.total_applied ?? '?'} migrations</b> aplicadas${(mig.pending_local || []).length ? ` · <span style="color:var(--coral)">${mig.pending_local.length} pendente(s)</span>` : ''}</div>
      ${techDetails(`<div class="gate"><span class="dot ok"></span><span>última: <span class="mono">${esc(mig.last_applied || '—')}</span></span></div>${stackRows}`, 'última migration e stack')}
    </div>
  </div>`;
}

function securitySignal(state) {
  const gates = (state && state.gates) || [];
  const g = gates.find(x => String(x.name || '').toLowerCase().includes('security'));
  const MAP = {
    ok: { cls: 'ok', short: 'aprovado', label: 'security-review aprovado no último ship' },
    warn: { cls: 'warn', short: 'ressalvas', label: 'security-review passou com ressalvas' },
    fail: { cls: 'bad', short: 'reprovado', label: 'security-review reprovado no último ship' },
    skip: { cls: 'muted', short: 'pulado', label: 'security-review pulado (mudança cosmética)' },
  };
  if (!g) return { cls: 'muted', short: 'sem dado', label: 'sem security-review registrado neste deploy', status: null };
  return { ...(MAP[g.status] || { cls: 'muted', short: g.status, label: 'security-review: ' + g.status }), status: g.status };
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

  for (const prd of prds) {
    used.add(prd.number);
    const kids = prd.children.map(n => byN[n]).filter(Boolean);
    kids.forEach(k => used.add(k.number));
    const kidsShown = kids.filter(matchIssue);
    if (!matchIssue(prd) && !kidsShown.length) continue;
    groups.push(`
      <section class="prd-group">
        ${issueCard(prd, idx++, true)}
        ${kidsShown.length ? `<div class="children">${kidsShown.map(k => issueCard(k, idx++)).join('')}</div>` : ''}
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
  ${sec('03', 'Issues — tudo que aconteceu', 'gh · PRD → fatias → PR → deploy')}
  <div class="grid g12" style="margin-bottom:6px">
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">issues</div><div class="v">${iss.length}</div><div class="s">desde ${fmtD(iss[iss.length - 1] && iss[iss.length - 1].created_at)}</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">abertas</div><div class="v" style="color:var(--green)">${open.length}</div><div class="s">${iss.length - open.length} fechadas</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">lead time médio</div><div class="v" style="font-size:30px; padding-top:6px">${lead ? spanH(lead) : '—'}</div><div class="s">da abertura ao fechamento</div></div></div>
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
  if (el) el.innerHTML = issueListHtml();
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
        <span class="dep-ver ${dp.app_version ? '' : 'unversioned'}">${dp.app_version ? 'v' + esc(dp.app_version) : esc(dp.sha || '—')}</span>
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
  ${sec('02', 'Deploys & releases', 'history.json + CHANGELOG.md')}
  <div class="grid g12" style="margin-bottom:6px">
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">deploys</div><div class="v">${dep.length}</div><div class="s">${fmtD(first && first.at)} → ${fmtD(last && last.at)}</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">saudáveis</div><div class="v" style="color:var(--green)">${dep.length ? Math.round(healthy.length / dep.length * 100) : 0}<small>%</small></div><div class="s">${dep.length - healthy.length} com problema</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="stat"><div class="k">build médio</div><div class="v" style="font-size:30px; padding-top:6px">${avg ? durS(avg) : '—'}</div><div class="s">duração por deploy</div></div></div>
    <div class="card lift sp3" ${rv()}><div class="k-label">duração (antigo → recente)</div>${spark([...durs].reverse())}</div>
  </div>
  <div class="timeline">${dep.map((d, idx) => deployCard(d, idx)).join('')}</div>`;
}

/* ---------- MAPA ---------- */

function renderMapa() {
  const snaps = S.data.snapshots;
  if (!S.mapaDoc || !snaps.find(s => s.name === S.mapaDoc)) S.mapaDoc = snaps[0] && snaps[0].name;
  const cur = snaps.find(s => s.name === S.mapaDoc);
  return `
  ${sec('04', 'Mapa da app', 'docs/spec/snapshots — regenerado a cada deploy')}
  <div class="docpills rv">
    ${snaps.map(s => `<button class="fchip ${s.name === S.mapaDoc ? 'on' : ''}" data-act="doc" data-doc="${esc(s.name)}">${esc(s.name)}</button>`).join('')}
  </div>
  ${cur ? `
  <div class="docmeta rv" style="--i:1">gerado em ${esc(fmtDT(cur.generated_at))} · ${cur.lines} linhas · <span class="mono">docs/spec/snapshots/${esc(cur.name)}.md</span></div>
  <div class="card md rv" style="--i:2" id="snapdoc">${md(cur.body_md)}</div>` : '<div class="empty">sem snapshots</div>'}`;
}

function loadMermaid() {
  if (window.mermaid) return Promise.resolve();
  if (S.mermaidP) return S.mermaidP;
  S.mermaidP = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js';
    s.onload = () => {
      window.mermaid.initialize({
        startOnLoad: false, theme: 'neutral', fontFamily: 'IBM Plex Sans',
        themeVariables: { primaryColor: '#e7e7f4', primaryBorderColor: '#2B2E7E', lineColor: '#3c3d62' },
      });
      resolve();
    };
    s.onerror = () => { S.mermaidP = null; reject(new Error('cdn')); };
    document.head.appendChild(s);
  });
  return S.mermaidP;
}

async function mermaidify(root) {
  const blocks = [...root.querySelectorAll('code.language-mermaid')];
  if (!blocks.length) return;
  try { await loadMermaid(); } catch { return; /* offline: fica o código no <pre> */ }
  blocks.forEach(c => {
    const box = document.createElement('div');
    box.className = 'mermaid-box';
    const m = document.createElement('pre');
    m.className = 'mermaid';
    m.textContent = c.textContent;
    box.appendChild(m);
    c.closest('pre').replaceWith(box);
  });
  try { await window.mermaid.run({ querySelector: '.mermaid-box .mermaid' }); } catch { /* mantém fallback */ }
}

/* ---------- DOMÍNIO ---------- */

function renderDominio() {
  const adrs = S.data.adrs;
  return `
  ${sec('05', 'Decisões de arquitetura', 'docs/adr — curado por humano')}
  <div class="grid g12">
    ${adrs.map((a, i) => `
      <article class="card adr lift sp6 rv" style="--i:${i}" data-act="adr" data-i="${i}">
        <span class="ghostnum">${String(a.number ?? '').padStart(2, '0')}</span>
        <h3>${esc(a.title)}</h3>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
          <span class="badge ${a.status === 'accepted' ? 'b-green' : 'b-amber'}">${esc(a.status)}</span>
          <span class="file">${esc(a.file)}</span>
        </div>
        ${S.expAdr.has(i) ? `<div class="adr-body md">${md(a.body_md)}</div>` : ''}
      </article>`).join('')}
  </div>
  ${sec('06', 'Glossário do domínio', 'CONTEXT.md — o que as palavras significam aqui')}
  <div class="card md rv">${md(S.data.context_md || '_CONTEXT.md não encontrado_')}</div>`;
}

/* ---------- GUIA (método · setup · bastidores) ---------- */

function currentOs() {
  if (S.os && OSES.includes(S.os)) return S.os;
  try {
    const saved = localStorage.getItem('dash.os');
    if (saved && OSES.includes(saved)) { S.os = saved; return saved; }
  } catch { /* localStorage bloqueado */ }
  const ua = (navigator.userAgentData && navigator.userAgentData.platform) ||
    navigator.platform || navigator.userAgent || '';
  S.os = /mac/i.test(ua) ? 'mac' : /win/i.test(ua) ? 'windows' : 'linux';
  return S.os;
}

const cmdFor = (b, os) =>
  b.all != null ? b.all : b.os ? (b.os[os] ?? b.os.mac ?? Object.values(b.os)[0]) : '';

function setupHtml() {
  const os = currentOs();
  const osTabs = OSES.map(o =>
    `<button class="fchip ${o === os ? 'on' : ''}" data-act="os" data-os="${o}">${esc(OS_LABEL[o])}</button>`).join('');
  const steps = SETUP.map((st, i) => `
    <article class="card setup-step" style="--i:${i}">
      <div class="setup-head"><span class="setup-n">${esc(st.n)}</span>
        <h3>${esc(st.title)}${st.tip ? tip(st.tip) : ''}</h3></div>
      ${st.intro ? `<p class="setup-intro">${esc(st.intro)}</p>` : ''}
      ${st.blocks.map(b => copyBlock(cmdFor(b, os), { label: b.label, note: b.note, lang: b.lang })).join('')}
    </article>`).join('');
  return `
  <p class="setup-intro">Do zero ao fluxo rodando em ~15-30 min. Siga os passos na ordem; cada bloco tem botão <b>copiar</b>. Escolha seu sistema:</p>
  <div class="setup-os"><span class="setup-os-label">sistema:</span>${osTabs}</div>
  <div class="setup-steps">${steps}</div>`;
}

function renderGuia() {
  const passos = METODO.map((p, i) => `
    <li class="met-passo">
      <span class="met-n">${i + 1}</span>
      <div class="met-corpo"><span class="cmdpill">${esc(p.cmd)}</span>
      <span class="met-frase">${esc(p.frase)}</span></div>
    </li>`).join('');
  return `
  ${sec('', 'Guia', 'o método, a máquina e os bastidores')}
  <details class="guia-sec card rv" open>
    <summary>O método em 6 passos</summary>
    <div class="guia-body">
      <ol class="metodo">${passos}</ol>
      <p class="guia-foot">Veja o método em ação: a aba <a data-act="gotab" data-go="plano">Plano</a> mostra as fatias reais da leva atual, em ondas.</p>
    </div>
  </details>
  <details class="guia-sec card rv" style="--i:1">
    <summary>Preparar uma máquina nova</summary>
    <div class="guia-body">${setupHtml()}</div>
  </details>
  <details class="guia-sec card rv" style="--i:2">
    <summary>Bastidores do painel</summary>
    <div class="guia-body"><p class="guia-paragrafo">${esc(BASTIDORES)}</p></div>
  </details>`;
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
  } else if (act === 'os') {
    if (S.os !== t.dataset.os) {
      S.os = t.dataset.os;
      try { localStorage.setItem('dash.os', S.os); } catch { /* localStorage bloqueado */ }
      render();
    }
  } else if (act === 'iss') {
    const n = Number(t.dataset.n);
    if (S.expIss.has(n)) S.expIss.delete(n);
    else { S.expIss.add(n); ensureComments(n); }
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

/* tooltips: fecham com Escape ou clique fora */
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeTips(); });
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
