'use strict';

/* Fluxo vivo, SPA vanilla. Lê /api/data (agregado), /api/issue/<n> (comentários
   lazy) e /api/issue/<n>/timeline (linha do tempo das fechadas, lazy). */

import { closeTips, reduceMotion, revealOnScroll } from './ui.js';
import { abaValida, aoMudarRota, gravarRota, lerRota, montarHash } from './router.js';
import { renderDiagrama, wireDiagramas } from './diagramas.js';
import { renderArea, wireArea } from './areas.js';
import { corDaPessoa } from './pessoas.js';
import { renderOndas } from './ondas.js';
import { filtrosPrsDaRota, filtrosPrsNaRota, filtrosPrsVazios, renderQuadroPrs } from './prs.js';

/* a aba abre no que está pendente: só as abertas */
const filtrosVazios = () => ({ state: 'OPEN', fase: '', resp: '', prd: null, label: '', q: '' });

/* filtros da aba Issues <-> filtros da rota (texto; vazio = padrão). O
   humana=1 dos links antigos (chip ready-for-human) vira a fase Humana. */
const filtrosDaRota = p => ({
  state: p.state || 'OPEN', fase: p.fase || (p.humana === '1' ? 'humana' : ''), resp: p.resp || '',
  prd: Number(p.prd) || null, label: p.label || '', q: p.q || '',
});
const filtrosNaRota = f => ({
  state: f.state === 'OPEN' ? '' : f.state, fase: f.fase, resp: f.resp, prd: f.prd ? String(f.prd) : '',
  label: f.label, q: f.q,
});

const S = {
  data: null,
  tab: 'issues',
  item: null,   // item aberto que o hash aponta (#issues/930, #producao/v0.161.0)
  fIssues: filtrosVazios(),
  fPrs: filtrosPrsVazios(),
  expIss: new Set(),
  expPrd: new Map(),
  expDep: new Set(),
  expAdr: new Set(),
  comments: {},
  timelines: {},
  mapaDoc: null,
  rotasQ: '',
  entTab: null,
  erFull: false,
  menu: null,   // dropdown de filtro aberto na aba Issues
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
const shaUrl = sha => `${S.data.repo_url}/commit/${sha}`;
/* chip navega dentro do painel pelo hash; o GitHub fica no ↗ de cada card */
const rotaDe = (aba, item) => esc(montarHash({ aba, item }));

function spark(vals, w = 360, h = 46) {
  if (vals.length < 2) return '';
  const max = Math.max(...vals), min = Math.min(...vals);
  const pts = vals.map((v, i) => [
    (i / (vals.length - 1)) * (w - 10) + 5,
    h - 7 - ((v - min) / ((max - min) || 1)) * (h - 16),
  ]);
  const poly = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
  const [lx, ly] = pts[pts.length - 1];
  const area = `${poly} ${(w - 5).toFixed(1)},${h - 3} 5,${h - 3}`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <polygon points="${area}" style="fill:var(--brand-wash)"/>
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
}

function renderBanner() {
  const err = S.data.github && S.data.github.error;
  $('#banner').innerHTML = err
    ? `<div class="banner"><b>GitHub indisponível</b>: ${esc(err)}<br>Mostrando só os dados locais (deploys, snapshots, ADRs, glossário).</div>`
    : '';
}

function renderFoot() {
  $('#foot').innerHTML = `
    <span>Hospital OS · somente leitura · fontes: <span class="mono">gh</span> + docs/spec + git</span>
    <span class="foot-right">coletado às ${esc(fmtDT(S.data.generated_at))}
      <a class="btn-pill outline" href="${esc(S.data.repo_url)}" target="_blank" rel="noopener">${esc(S.data.repo_slug)} <span class="btn-arrow">↗</span></a></span>`;
}

function tick() {
  const el = $('#ago');
  if (el && S.data) el.textContent = `coletado ${ago(S.data.generated_at)}`;
}

/* ---------- rota (o hash é do router.js; aqui só o estado da tela) ---------- */

function setTab(t) {
  S.erFull = false;   // trocar de aba sai da tela cheia; voltar ao Mapa não a reabre
  S.tab = abaValida(t);
  S.item = null;      // o item aberto é da aba que ficou para trás
  sincronizarHash();
  marcarAba();
  render();
  window.scrollTo({ top: 0 });
}

function marcarAba() {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
}

/* estado da tela -> hash; os filtros existem nas abas Issues e PRs */
function sincronizarHash() {
  const filtros = S.tab === 'issues' ? filtrosNaRota(S.fIssues) : S.tab === 'prs' ? filtrosPrsNaRota(S.fPrs) : {};
  gravarRota({ aba: S.tab, item: S.item, filtros });
}

/* hash -> estado da tela: no boot, no chip clicado e no voltar do navegador */
function irPara(rota) {
  S.erFull = false;
  S.tab = rota.aba;
  S.item = rota.item;
  if (rota.aba === 'issues') S.fIssues = filtrosDaRota(rota.filtros);
  if (rota.aba === 'prs') S.fPrs = filtrosPrsDaRota(rota.filtros);
  abrirItem();
  sincronizarHash();
  marcarAba();
  render();
  const alvo = view.querySelector('[aria-current="true"]');
  if (alvo) alvo.scrollIntoView({ block: 'center' });
  else window.scrollTo({ top: 0 });
}

/* o card que o hash aponta fica em destaque (e é o alvo da rolagem do irPara) */
const destaque = item => (S.item && S.item === String(item) ? ' aria-current="true"' : '');

/* o item da rota abre expandido; a fatia aparece com o PRD dela aberto */
function abrirItem() {
  if (!S.item || !S.data) return;
  if (S.tab === 'issues') {
    const n = Number(S.item);
    const i = (S.data.github.issues || []).find(x => x.number === n);
    if (!i) return;
    mostrarNaLista(i);
    S.expIss.add(n);
    ensureComments(n);
    ensureTimeline(n);
    if (i.parent) S.expPrd.set(i.parent, true);
  } else if (S.tab === 'producao') {
    const idx = S.data.history.findIndex(d => depVer(d.app_version) === S.item);
    if (idx >= 0) S.expDep.add(idx);
  }
}

function render() {
  if (!S.data) return;
  const fn = {
    issues: renderIssues, prs: renderPrs, producao: renderProducao, mapa: renderMapa, dominio: renderDominio,
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

/* cabeçalho de seção com eyebrow (padrão Baseline, #260) */
function cabecalho(eyebrow, titulo, hint = '') {
  return `<div class="sec-ey rv">
    <span class="eyebrow">${eyebrow}</span>
    <div class="sec-ey-row"><h2 class="clip"><span class="clip-inner">${titulo}</span></h2>${hint ? `<span class="hint">${hint}</span>` : ''}</div>
  </div>`;
}

/* ---------- PRODUÇÃO (versão no ar e lista de versões, ADR 0062 decisão 2) ---------- */

function renderProducao() {
  return renderDeploys();
}


/* ---------- ISSUES (home: pendente por pessoa, filtros em dropdown, card compacto) ---------- */

/* Régua de nove fases do fases.py (ADR 0062, decisão 4), na ordem do funil:
   [chave do payload, nome na tela, badge]. */
const FASES = [
  ['triagem', 'Triagem', 'b-ghost'],
  ['fila', 'Fila', 'b-indigo'],
  ['bloqueada', 'Bloqueada', 'b-red'],
  ['em_andamento', 'Em andamento', 'b-amber'],
  ['pr_aberto', 'PR aberto', 'b-blue'],
  ['mergeada', 'Mergeada', 'b-purple'],
  ['em_producao', 'Em produção', 'b-green'],
  ['humana', 'Humana', 'b-coral'],
  ['encerrada_sem_pr', 'Encerrada sem PR', 'b-ghost'],
];
/* o funil conta só as abertas; "encerrada sem PR" é sempre fechada e não entra */
const FASES_PENDENTES = FASES.filter(([k]) => k !== 'encerrada_sem_pr');
const PREFIXOS_LABEL = ['type', 'area', 'fatia'];
const LABEL_HUMANA = 'ready-for-human';

/* Pessoa = quem assumiu (assignee) ou quem criou: tudo que ela tem que olhar.
   O card marca "criou" quando a pessoa entrou pelo autor. SEM_RESP é o
   "ninguém assumiu": issues sem assignee. Mesmo valor e mesma regra do
   SEM_RESPONSAVEL do fases.py, chave das contagens do funil. */
const SEM_RESP = '(sem)';

function responsaveis(i) {
  return [...new Set([...i.assignees, ...(i.author ? [i.author] : [])])];
}

function doResponsavel(i, resp) {
  return resp === SEM_RESP ? i.assignees.length === 0 : responsaveis(i).includes(resp);
}

function faseDe(i) {
  return ((S.data.fases || {}).issues || {})[i.number] || null;
}

function matchIssue(i) {
  const f = S.fIssues;
  if (f.state !== 'all' && i.state !== f.state) return false;
  if (f.fase && (faseDe(i) || {}).fase !== f.fase) return false;
  if (f.resp && !doResponsavel(i, f.resp)) return false;
  if (f.prd && i.number !== f.prd && i.parent !== f.prd) return false;
  if (f.label && !i.labels.includes(f.label)) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!(`#${i.number} ${i.title}`.toLowerCase().includes(q))) return false;
  }
  return true;
}

/* contagens do payload: o total, ou as da pessoa filtrada (zeradas se ela não tem nenhuma) */
function contagensDoFunil(funil, resp) {
  if (!resp) return funil.total;
  return funil.por_responsavel[resp] || {};
}

const somaDasFases = n => FASES_PENDENTES.reduce((t, [k]) => t + (n[k] || 0), 0);

function nomeDoResponsavel(resp) {
  return resp === SEM_RESP ? 'ninguém assumiu' : esc(resp);
}

function donoDoPendente(resp) {
  if (!resp) return ['no time', 'todas as issues abertas'];
  if (resp === SEM_RESP) return ['sem ninguém', 'abertas que ninguém assumiu'];
  return [`para ${esc(resp)}`, 'abertas que assumiu ou criou'];
}

/* card grande = tudo que está pendente; os pequenos destrincham por fase e somam o grande */
function funilHtml() {
  const fases = S.data.fases;
  if (!fases || !fases.funil) {
    const motivo = fases && fases.erro
      ? `funil indisponível: ${esc(fases.erro)}`
      : 'o funil lê as issues pelo <span class="mono">gh</span>, que está indisponível agora, veja o aviso no topo';
    return `<div class="empty funil-vazio rv">${motivo}</div>`;
  }
  const f = S.fIssues;
  const n = contagensDoFunil(fases.funil, f.resp);
  const tudo = f.state === 'OPEN' && !f.fase;
  const [dono, sub] = donoDoPendente(f.resp);
  return `
  <div class="funil rv" role="group" aria-label="pendente por fase">
    <button type="button" class="funil-total ${tudo ? 'on' : ''}" data-act="fpendente" aria-pressed="${tudo}">
      <span class="funil-total-n">${somaDasFases(n)}</span>
      <span class="funil-total-nome">pendente ${dono}</span>
      <span class="funil-total-sub">${sub}</span>
    </button>
    ${FASES_PENDENTES.map(([k, nome]) => `
    <button type="button" class="funil-passo ${f.fase === k ? 'on' : ''} ${n[k] ? '' : 'zero'}" data-act="ffase" data-v="${k}" aria-pressed="${f.fase === k}">
      <span class="funil-n">${n[k] || 0}</span><span class="funil-nome">${nome}</span>
    </button>`).join('')}
  </div>`;
}

/* dropdown de filtro: o menu fica sempre no DOM e abre pela classe (S.menu) */
function dropdown(chave, rotulo, valor, opcoes) {
  const aberto = S.menu === chave;
  return `
  <div class="dd ${aberto ? 'open' : ''}" data-menu="${chave}">
    <button type="button" class="dd-btn ${valor ? 'on' : ''}" data-act="menu" data-v="${chave}" aria-haspopup="listbox" aria-expanded="${aberto}">
      <span class="dd-rot">${rotulo}</span><span class="dd-val">${valor || 'todos'}</span>
    </button>
    <div class="dd-menu" role="listbox" aria-label="${rotulo}">${opcoes.join('')}</div>
  </div>`;
}

function opcao(act, v, on, txt, extra = '') {
  return `<button type="button" class="dd-opt ${on ? 'on' : ''}" data-act="${act}" data-v="${esc(v)}" role="option" aria-selected="${on}"${extra}>${txt}</button>`;
}

function opcaoPessoa(login, pendentes) {
  const on = S.fIssues.resp === login;
  const n = pendentes[login] || 0;
  return opcao('fresp', login, on,
    `<span class="pessoa-dot"></span><span class="dd-txt">${nomeDoResponsavel(login)}</span><span class="dd-n">${n}</span>`,
    ` style="--pessoa:${corDaPessoa(login === SEM_RESP ? null : login)}"`);
}

/* labels das issues agrupadas por prefixo (type:, area:, fatia:) e o resto;
   ready-for-human é a fase Humana, card próprio no funil */
function gruposDeLabels(iss) {
  const todas = [...new Set(iss.flatMap(i => i.labels))].filter(l => l !== LABEL_HUMANA).sort();
  const doPrefixo = p => todas.filter(l => l.startsWith(p + ':'));
  const grupos = PREFIXOS_LABEL.map(p => [p, doPrefixo(p)]);
  grupos.push(['outras', todas.filter(l => !PREFIXOS_LABEL.some(p => l.startsWith(p + ':')))]);
  return grupos.filter(([, ls]) => ls.length);
}

function filtrosHtml(iss) {
  const f = S.fIssues;
  const funil = (S.data.fases || {}).funil;
  const pendentes = Object.fromEntries(Object.entries((funil || {}).por_responsavel || {})
    .map(([p, n]) => [p, somaDasFases(n)]));
  const pessoas = [...new Set(iss.flatMap(responsaveis))].sort();
  const estados = [['OPEN', 'abertas'], ['CLOSED', 'fechadas'], ['all', 'todas']];
  const prds = iss.filter(i => i.is_prd && i.state === 'OPEN').sort((a, b) => b.number - a.number);
  const todos = (act, on) => opcao(act, '', on, '<span class="dd-txt">todos</span>');
  const menus = [
    dropdown('resp', 'responsável', f.resp ? nomeDoResponsavel(f.resp) : '',
      [todos('fresp', !f.resp), ...pessoas.map(p => opcaoPessoa(p, pendentes)), opcaoPessoa(SEM_RESP, pendentes)]),
    dropdown('state', 'estado', (estados.find(([v]) => v === f.state) || [, ''])[1],
      estados.map(([v, t]) => opcao('fstate', v, f.state === v, `<span class="dd-txt">${t}</span>`))),
    prds.length ? dropdown('prd', 'PRD', f.prd ? `#${f.prd}` : '',
      [todos('fprd', !f.prd), ...prds.map(p => opcao('fprd', p.number, f.prd === p.number,
        `<span class="dd-num">#${p.number}</span><span class="dd-txt">${esc(p.title)}</span>`))]) : '',
    ...gruposDeLabels(iss).map(([pref, ls]) => {
      const curta = l => esc(pref === 'outras' ? l : l.slice(pref.length + 1));
      return dropdown(pref, pref, ls.includes(f.label) ? curta(f.label) : '',
        [todos('flabel', !ls.includes(f.label)), ...ls.map(l => opcao('flabel', l, f.label === l, `<span class="dd-txt">${curta(l)}</span>`))]);
    }),
  ];
  return `
  <div class="filtros rv">
    ${menus.join('')}
    <input class="search" id="fq" type="search" placeholder="buscar por título ou #número…" value="${esc(f.q)}">
  </div>`;
}

/* ---------- card da issue ---------- */

const SINAL_CI = { vermelho: 'CI vermelho', verde: 'CI verde', pendente: 'CI pendente', sem_ci: 'sem CI' };

function detalheDaFase(fs, i) {
  if (fs.sub === 'branch_criada') return 'branch criada';
  if (fs.fase === 'bloqueada' && i.blocked_by.length) return `espera ${i.blocked_by.map(n => `#${n}`).join(', ')}`;
  if (fs.fase !== 'pr_aberto' || !fs.sinal) return '';
  const s = fs.sinal;
  return [
    SINAL_CI[s.ci] || '',
    s.veredito === 'must_fix' ? 'revisor: must-fix' : s.veredito === 'limpo' ? 'revisor: limpo' : '',
    s.conflito ? 'conflito' : '',
    s.tentativa_anterior ? 'nova tentativa' : '',
  ].filter(Boolean).join(' · ');
}

function faseBadge(fs, i) {
  if (!fs) return '';
  const [, nome, cls] = FASES.find(([k]) => k === fs.fase) || [fs.fase, fs.fase, 'b-ghost'];
  const det = detalheDaFase(fs, i);
  return `<span class="badge ${cls}">${esc(nome)}${det ? ` · ${esc(det)}` : ''}</span>`;
}

function pessoaHtml(login) {
  return `<span class="pessoa" style="--pessoa:${corDaPessoa(login)}"><span class="pessoa-dot"></span>${login ? esc(login) : 'ninguém assumiu'}</span>`;
}

function pessoasDoCard(i) {
  const quem = i.assignees.length ? i.assignees.map(pessoaHtml).join('') : pessoaHtml(null);
  // quem criou e não assumiu também tem a issue na fila dele: a marca diz por quê
  const criou = i.author && !i.assignees.includes(i.author);
  return quem + (criou ? `<span class="chip autor">✎ criou: ${esc(i.author)}</span>` : '');
}

const idadeTxt = i => i.state === 'OPEN' ? `aberta ${ago(i.created_at)}` : `fechada ${fmtD(i.closed_at)}`;

/* ---------- linha do tempo (ADR 0062, decisão 6) ---------- */

const LENTE = { revisao: 'revisão', seguranca: 'segurança' };

function eventoTexto(e) {
  const pr = e.pr ? `PR #${e.pr}` : 'PR';
  const vezes = n => `${n} ${n === 1 ? 'vez' : 'vezes'}`;
  const txt = {
    criada: () => 'criada',
    designada: () => e.quem ? `designada para ${e.quem}` : 'designada',
    branch: () => `branch ${e.branch}`,
    pr_aberto: () => `${pr} aberto`,
    novo_pr: () => `novo ${pr}`,
    ci_vermelho: () => `CI vermelho ${vezes(e.vezes || 1)} no ${pr}`,
    revisor_comentou: () => `revisor de ${LENTE[e.lente] || e.lente} comentou: ${e.veredito === 'must_fix' ? 'must-fix' : 'limpo'}`,
    pr_fechado: () => `${pr} fechado sem merge`,
    mergeado: () => `${pr} mergeado`,
    em_producao: () => `em produção${e.versao ? ` na ${depVer(e.versao)}` : ''}`,
    fechada: () => 'issue fechada',
    reaberta: () => 'issue reaberta',
  }[e.tipo];
  return esc(txt ? txt() : e.tipo);
}

/* abertas: a linha vem na coleta; fechadas (ou coleta sem ela): busca ao expandir */
function timelineDe(n) {
  const pronta = ((S.data.fases || {}).timelines || {})[n];
  return pronta ? { list: pronta } : S.timelines[n];
}

function linhaDoTempoHtml(n) {
  const t = timelineDe(n);
  const cab = '<div class="k-label">linha do tempo</div>';
  let corpo;
  if (!t || t.loading) corpo = '<span class="ago">carregando a linha do tempo…</span>';
  else if (t.error) corpo = `<span class="ago">linha do tempo indisponível: ${esc(t.error)}</span>`;
  else if (!t.list.length) corpo = '<span class="ago">sem eventos</span>';
  else {
    corpo = `<ol class="eventos">${t.list.map(e => `
      <li class="evento"><span class="evento-quando">${e.em ? esc(fmtDT(e.em)) : 'sem data'}</span>
        <span class="evento-o-que">${eventoTexto(e)}</span></li>`).join('')}</ol>`;
  }
  return `<div class="linha-tempo">${cab}${corpo}</div>`;
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

/* card compacto (ADR 0062, decisão 6): fase, pessoa, idade, critérios, PR e
   versão; aberto, a linha do tempo, as labels, o corpo e os comentários */
function issueCard(i, idx, prd = false) {
  const open = S.expIss.has(i.number);
  const fs = faseDe(i);
  const chips = [
    faseBadge(fs, i),
    pessoasDoCard(i),
    `<span class="chip">${idadeTxt(i)}</span>`,
    i.criteria.total ? `<span class="chip" title="critérios de aceite">✓ ${i.criteria.done}/${i.criteria.total}</span>` : '',
    fs && fs.pr ? `<a class="chip" href="${rotaDe('prs', fs.pr)}">PR #${fs.pr}</a>` : '',
    fs && fs.versao ? `<a class="chip chip-versao" href="${rotaDe('producao', depVer(fs.versao))}">${esc(depVer(fs.versao))}</a>` : '',
  ].filter(Boolean).join('');

  return `
  <article class="nrow ${prd ? 'prd-row' : ''} rv" style="--i:${idx}"${destaque(i.number)}>
    <span class="nrow-idx">${String(idx + 1).padStart(2, '0')}</span>
    <div class="nrow-main">
      <div class="iss-head" data-act="iss" data-n="${i.number}">
        ${prd ? '<span class="prd-tag">PRD</span>' : ''}
        <span class="inum">#${i.number}</span>
        <span class="ititle">${esc(i.title)}</span>
      </div>
      <div class="iss-chips">${chips}</div>
      ${prd ? renderOndas(i, S.data, FASES) : ''}
      ${open ? `
      <div class="iss-body">
        ${linhaDoTempoHtml(i.number)}
        ${i.labels.length ? `<div class="iss-labels">${i.labels.map(labelBadge).join('')}</div>` : ''}
        <a class="ghlink" href="${issUrl(i.number)}" target="_blank" rel="noopener">abrir no GitHub ↗</a>
        <div class="md" style="margin-top:10px">${md(i.body)}</div>
        ${commentsHtml(i.number)}
      </div>` : ''}
    </div>
    <a class="nrow-go" href="${issUrl(i.number)}" target="_blank" rel="noopener" aria-label="abrir a issue #${i.number} no GitHub"><span class="nrow-arrow">↗</span></a>
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
  const filtroAtivo = !!(f.q || f.fase || f.resp || f.prd || f.label || f.state !== 'OPEN');

  for (const prd of prds) {
    used.add(prd.number);
    const kids = prd.children.map(n => byN[n]).filter(Boolean);
    kids.forEach(k => used.add(k.number));
    const kidsShown = kids.filter(matchIssue);
    if (!matchIssue(prd) && !kidsShown.length) continue;
    // colapsadas por padrão; filtro/busca expandem por default, mas a
    // escolha explícita do usuário (expPrd: numero -> bool) sempre vence (#268)
    const aberto = S.expPrd.has(prd.number)
      ? S.expPrd.get(prd.number)
      : (filtroAtivo && kidsShown.length > 0);
    const fechadas = kids.filter(k => k.state === 'CLOSED').length;
    const toggle = kids.length ? `
      <button class="fatias-toggle" data-act="prd" data-n="${prd.number}" data-open="${aberto ? 1 : 0}" aria-expanded="${aberto}">
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
  return `
  <div class="tab-issues">
  ${cabecalho('acompanhar', 'Issues', 'gh · cada issue na sua fase, do pedido à produção')}
  ${filtrosHtml(iss)}
  ${funilHtml()}
  <div id="ilist">${issueListHtml()}</div>
  </div>`;
}

function wireIssues() {
  const q = $('#fq');
  if (q) q.addEventListener('input', () => { S.fIssues.q = q.value; sincronizarHash(); refreshIssueList(); });
}

/* filtro que esconderia a issue pedida sai do caminho; fechada pede "todas" */
function mostrarNaLista(i) {
  if (matchIssue(i)) return;
  S.fIssues = { ...filtrosVazios(), state: i.state === 'OPEN' ? 'OPEN' : 'all' };
}

/* card de fase clicado de novo desliga o filtro */
function alternarFiltro(chave, v) {
  S.fIssues[chave] = S.fIssues[chave] === v ? filtrosVazios()[chave] : v;
  render();
}

/* abre/fecha o dropdown sem redesenhar a aba */
function marcarMenu() {
  view.querySelectorAll('.dd').forEach(d => {
    const on = d.dataset.menu === S.menu;
    d.classList.toggle('open', on);
    const b = d.querySelector('.dd-btn');
    if (b) b.setAttribute('aria-expanded', String(on));
  });
}

function fecharMenu() {
  if (S.menu === null) return;
  S.menu = null;
  marcarMenu();
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

async function ensureTimeline(n) {
  const t = timelineDe(n);
  if (t && !t.error) return;  // erro não fica no cache: reabrir o card tenta de novo
  S.timelines[n] = { loading: true };
  try {
    const r = await fetch(`/api/issue/${n}/timeline`);
    const j = await r.json();
    S.timelines[n] = { loading: false, list: j.timeline || [], error: j.error };
  } catch (e) {
    S.timelines[n] = { loading: false, list: [], error: String(e) };
  }
  if (S.tab === 'issues') refreshIssueList();
}

/* nó do desenho das ondas (#943): abre o card da fatia na lista, com as
   fatias do PRD à mostra; filtro que esconderia a fatia sai do caminho */
function abrirFatia(n, prd) {
  const fatia = (S.data.github.issues || []).find(i => i.number === n);
  if (fatia) mostrarNaLista(fatia);
  S.expPrd.set(prd, true);
  if (!S.expIss.has(n)) { S.expIss.add(n); ensureComments(n); ensureTimeline(n); }
  render();
  const card = view.querySelector(`.iss-head[data-n="${n}"]`);
  if (card) card.scrollIntoView({ block: 'center', behavior: reduceMotion() ? 'auto' : 'smooth' });
}

/* ---------- PRS (quadro por fase, uma raia por pessoa: prs.js) ---------- */

function renderPrs() {
  return `
  <div class="tab-prs">
  ${cabecalho('acompanhar', 'PRs', 'gh · cada PR na sua fase, uma raia por pessoa')}
  ${renderQuadroPrs({ data: S.data, filtros: S.fPrs, item: S.item, depVer, fmtD })}
  </div>`;
}

/* ---------- DEPLOYS ---------- */

/* history.json mistura "v0.45.4" e "0.43.1"; a aba exibe sempre com um v só */
const depVer = v => v ? 'v' + String(v).replace(/^v/, '') : '';

/* Deploys da mesma versão juntos, na ordem do history.json (o rabo grava o
   mais recente em [0]); deploy sem versão é linha própria. A chave da versão
   é o índice do deploy mais recente dela no history: o mesmo que o abrirItem
   acha pelo hash e o clique (data-act="dep") expande. */
function versoesDoHistorico(history) {
  const porVer = new Map(), lista = [];
  history.forEach((dp, i) => {
    const ver = depVer(dp.app_version);
    if (ver && porVer.has(ver)) { porVer.get(ver).deploys.push(dp); return; }
    const v = { i, ver, deploys: [dp] };
    if (ver) porVer.set(ver, v);
    lista.push(v);
  });
  return lista;
}

const unicos = xs => [...new Set(xs)];
const shaCurto = sha => String(sha || '·').slice(0, 7);

/* um deploy da versão, aberto: quando, health, build, env e notas */
function deployDaVersao(dp) {
  const env = (dp.env_changes || []).map(e => `${esc(e.service)} ${esc(e.action)} ${(e.keys || []).map(esc).join(', ')}`);
  return `
  <div class="pd-dep">
    <div class="pd-chips">
      <span class="pd-when">${esc(fmtDT(dp.at))}</span>
      <span class="badge ${dp.result === 'healthy' ? 'b-green' : 'b-red'}">${esc(dp.result || '?')}</span>
      <span class="chip" title="duração do build">${durS(dp.duration_seconds)}</span>
      ${dp.sha ? `<span class="chip">${esc(shaCurto(dp.sha))}</span>` : ''}
      ${(dp.scope || []).map(s => `<span class="chip">${esc(s)}</span>`).join('')}
      ${dp.rollback_target_sha ? `<span class="badge b-amber">rollback → ${esc(dp.rollback_target_sha)}</span>` : ''}
    </div>
    ${env.length ? `<p class="pd-notes mono">env: ${env.join(' · ')}</p>` : ''}
    ${dp.notes ? `<p class="pd-notes">${esc(dp.notes)}</p>` : ''}
  </div>`;
}

/* card da versão: fechado, o que entrou (PRs, issues, migration) e o health
   do deploy mais recente; aberto, cada deploy da versão */
function versaoCard(v, pos) {
  const dp = v.deploys[0];
  const open = S.expDep.has(v.i);
  const ok = dp.result === 'healthy';
  const maxDur = Math.max(...S.data.history.map(x => x.duration_seconds || 0), 1);
  const de = campo => unicos(v.deploys.flatMap(d => d[campo] || []));

  const chipsResumo = [
    `<span class="badge ${ok ? 'b-green' : 'b-red'}">${esc(dp.result || '?')}</span>`,
    v.deploys.length > 1 ? `<span class="chip">${v.deploys.length} deploys</span>` : '',
    ...de('migrations_applied').map(m => `<span class="badge b-amber">⛁ ${esc(m)}</span>`),
    ...de('pr_numbers').map(n => `<a class="chip" href="${rotaDe('prs', n)}">PR #${n}</a>`),
    ...de('issue_numbers').map(n => `<a class="chip" href="${rotaDe('issues', n)}">#${n}</a>`),
  ].filter(Boolean).join('');

  return `
  <div class="pd-item rv ${ok ? '' : 'bad'}" style="--i:${Math.min(pos, 12)}">
    <article class="card pd-card lift"${destaque(v.ver)}>
      <div class="pd-head" data-act="dep" data-i="${v.i}">
        <span class="pd-ver ${v.ver ? '' : 'unversioned'}">${esc(v.ver || shaCurto(dp.sha))}</span>
        <span class="pd-subject">${esc(dp.subject || dp.raw_subject || '')}</span>
        <span class="pd-when">${esc(fmtDT(dp.at))}</span>
        ${dp.sha ? `<a class="pd-gh" href="${shaUrl(esc(dp.sha))}" target="_blank" rel="noopener" aria-label="abrir o commit ${esc(dp.sha)} no GitHub">↗</a>` : ''}
      </div>
      <div class="pd-chips">${chipsResumo}</div>
      ${dp.duration_seconds ? `
      <div class="pd-durbar">
        <span class="rail"><span class="fill" style="width:${Math.round((dp.duration_seconds / maxDur) * 100)}%"></span></span>
        <span class="t">${durS(dp.duration_seconds)}</span>
      </div>` : ''}
      ${open ? `<div class="pd-body">${v.deploys.map(deployDaVersao).join('')}</div>` : ''}
    </article>
  </div>`;
}

const STATUS_CLS = { healthy: 'prod-ok', warning: 'prod-warn' };

/* health do serviço pelo último check gravado no state.json */
function healthTxt(hc) {
  const h = hc || {};
  return [h.http_status ? `HTTP ${h.http_status}` : 'sem HTTP', h.latency_ms != null ? `${h.latency_ms} ms` : '',
    h.at ? fmtDT(h.at) : ''].filter(Boolean).join(' · ');
}

function renderDeploys() {
  const dep = S.data.history;
  const durs = dep.map(x => x.duration_seconds).filter(x => x != null);
  const st = S.data.state || {};
  // faixa do topo: a versão no ar e cada serviço com o health, do state.json
  const cells = [
    { k: 'no ar', v: depVer(st.last_app_version) || '·', s: `atualizado ${fmtDT(st.updated_at)}` },
    ...(st.services || []).map(s => ({
      k: s.id, v: s.status || '?', s: healthTxt(s.last_health_check), cls: STATUS_CLS[s.status] || 'prod-bad',
    })),
  ];

  return `
  <section class="prod-band rv" style="--i:0">
    <div class="prod-band-head">
      <span class="eyebrow">produção · versão no ar e serviços</span>
      <span class="prod-band-src">history.json + state.json</span>
    </div>
    <div class="prod-stats">
      ${cells.map((c, i) => `
      <div class="prod-cell rv ${c.cls || ''}" style="--i:${i + 1}">
        <div class="prod-v">${esc(c.v)}</div>
        <div class="prod-k">${esc(c.k)}</div>
        <div class="prod-s">${esc(c.s)}</div>
      </div>`).join('')}
    </div>
  </section>
  <div class="card prod-spark rv" style="--i:5">
    <div class="k-label">duração dos builds (antigo → recente)</div>
    ${spark([...durs].reverse())}
  </div>
  <div class="pd-timeline">${versoesDoHistorico(dep).map(versaoCard).join('')}</div>`;
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
  ${cabecalho('decidir', 'Decisões de arquitetura', 'docs/adr · curado por humano')}
  <div class="grid g12">
    ${adrs.map((a, i) => `
      <article class="card tst adr lift sp6 rv" style="--i:${i}" data-act="adr" data-i="${i}">
        <span class="tst-quote" aria-hidden="true">&ldquo;</span>
        <h3 class="tst-corpo">${esc(a.title)}</h3>
        ${S.expAdr.has(i) ? `<div class="adr-body md">${md(a.body_md)}</div>` : ''}
        <div class="tst-foot">
          <span class="tst-ref">ADR ${String(a.number ?? '').padStart(2, '0')} · ${esc(a.file)}</span>
          ${adrStatusBadge(a.status)}${adrPointerBadge(a)}
        </div>
      </article>`).join('')}
  </div>
  ${cabecalho('entender', 'Glossário do domínio', 'o que as palavras significam aqui')}
  <div class="card tst rv">
    <span class="tst-quote" aria-hidden="true">&ldquo;</span>
    <div class="md">${md(S.data.context_md || '_CONTEXT.md não encontrado_')}</div>
    <div class="tst-foot"><span class="tst-ref">CONTEXT.md · curado por humano</span></div>
  </div>`;
}

/* ---------- eventos ---------- */

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
  } else if (act === 'iss') {
    const n = Number(t.dataset.n);
    if (S.expIss.has(n)) { S.expIss.delete(n); if (S.item === String(n)) S.item = null; }
    else { S.expIss.add(n); S.item = String(n); ensureComments(n); ensureTimeline(n); }
    refreshIssueList();
  } else if (act === 'prd') {
    const n = Number(t.dataset.n);
    S.expPrd.set(n, t.dataset.open !== '1');
    refreshIssueList();
  } else if (act === 'onda') {
    abrirFatia(Number(t.dataset.n), Number(t.dataset.prd));
  } else if (act === 'pr') {
    S.item = S.item === t.dataset.n ? null : t.dataset.n;
    render();
  } else if (act === 'pfresp') {
    S.fPrs.resp = S.fPrs.resp === t.dataset.v ? '' : t.dataset.v;
    render();
  } else if (act === 'pfprd') {
    const n = Number(t.dataset.v);
    S.fPrs.prd = S.fPrs.prd === n ? null : n;
    render();
  } else if (act === 'pfabertos') {
    S.fPrs.abertos = !S.fPrs.abertos;
    render();
  } else if (act === 'dep') {
    const i = Number(t.dataset.i);
    const ver = depVer(S.data.history[i].app_version);
    if (S.expDep.has(i)) { S.expDep.delete(i); if (S.item === ver) S.item = null; }
    else { S.expDep.add(i); if (ver) S.item = ver; }
    render();
  } else if (act === 'adr') {
    const i = Number(t.dataset.i);
    S.expAdr.has(i) ? S.expAdr.delete(i) : S.expAdr.add(i);
    render();
  } else if (act === 'menu') {
    S.menu = S.menu === t.dataset.v ? null : t.dataset.v;
    marcarMenu();
  } else if (['fstate', 'fresp', 'fprd', 'flabel'].includes(act)) {
    // opção do dropdown: escolhe e fecha; "todos" (v vazio) limpa
    const chave = { fstate: 'state', fresp: 'resp', fprd: 'prd', flabel: 'label' }[act];
    S.fIssues[chave] = act === 'fprd' ? (Number(t.dataset.v) || null) : t.dataset.v;
    S.menu = null;
    render();
  } else if (act === 'fpendente') {
    // o card grande: tudo que está pendente, sem recorte de fase
    S.fIssues.state = 'OPEN';
    S.fIssues.fase = '';
    render();
  } else if (act === 'ffase') {
    // a contagem do card é das abertas: a lista mostra as mesmas
    S.fIssues.state = 'OPEN';
    alternarFiltro('fase', t.dataset.v);
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
    S.fIssues = { ...filtrosVazios(), label: t.dataset.label || '' };
    setTab(t.dataset.go);
  }
  sincronizarHash();   // card aberto e filtro trocado vão para o hash
});

$('#tabs').addEventListener('click', e => {
  const b = e.target.closest('button[data-tab]');
  if (b) setTab(b.dataset.tab);
});

aoMudarRota(irPara);

/* tooltips: fecham com Escape ou clique fora; Escape também sai da tela cheia */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeTips();
  fecharMenu();
  if (S.erFull) { S.erFull = false; render(); }
});
document.addEventListener('click', e => {
  if (!e.target.closest('.tip')) closeTips();
  if (!e.target.closest('.dd')) fecharMenu();
});

/* ---------- boot ---------- */

(async function init() {
  S.tab = lerRota().aba;   // a aba certa já marcada enquanto coleta
  marcarAba();
  await load(false);
  irPara(lerRota());       // relido: uma aba clicada durante a coleta vale
  setInterval(tick, 5000);
  setInterval(() => load(false, true), 60000);
})();
