'use strict';

/* Fluxo vivo, SPA vanilla. Lê /api/data (agregado), /api/issue/<n> (comentários
   lazy) e /api/issue/<n>/timeline (linha do tempo das fechadas, lazy). */

import { closeTips, reduceMotion, revealOnScroll } from './ui.js';
import { SUBS_DOC, abaValida, aoMudarRota, gravarRota, lerRota, montarHash } from './router.js';
import { renderDiagrama, wireDiagramas } from './diagramas.js';
import { renderArea, wireArea } from './areas.js';
import { corDaPessoa } from './pessoas.js';
import { renderOndas } from './ondas.js';
import { alternarPessoa, filtrosPrsDaRota, filtrosPrsNaRota, filtrosPrsVazios, renderQuadroPrs } from './prs.js';

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
  fProd: { resp: '' },   // filtro da linha do tempo da aba Produção (filtrosProdVazios)
  expIss: new Set(),
  expPrd: new Map(),
  expDep: new Set(),
  expAdr: new Set(),
  adrHist: false,   // Decisões: mostrar também as superseded (esmaecidas)
  adrQ: '',
  fluxo: null,      // static/fluxo.json, carregado na primeira visita à sub-pill Fluxo
  fluxoErro: null,
  fluxoNo: null,    // passo do fluxo aberto no painel
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
/* duração humana: 45s, 1m06s, 2h05m, 3d 4h (as etapas da linha do tempo vão de segundos a dias) */
function durS(sec) {
  if (sec == null) return '·';
  const s = Math.round(sec);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h${String(m).padStart(2, '0')}m`;
  return m ? `${m}m${String(r).padStart(2, '0')}s` : `${r}s`;
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
  const ptr = a.superseded_by ? `substituída pela ${a.superseded_by}`
    : a.amended_by ? `emendada pela ${a.amended_by}` : '';
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

/* Semáforo com três estados: verde só com todo serviço healthy e checado;
   vermelho com algum down/unhealthy ou HTTP fora de 2xx; âmbar no resto
   (warning, sem verificação). O supabase não tem HTTP próprio: a subida deriva
   o status dele do health do backend, e "sem HTTP" deixou de ser vermelho. */
const SERVICO_FORA = ['down', 'unhealthy'];
const checado = s => s.status === 'healthy' && !!s.last_health_check;

function estadoDaProducao(svcs) {
  const fora = s => {
    const http = (s.last_health_check || {}).http_status;
    return SERVICO_FORA.includes(s.status) || (http != null && (http < 200 || http >= 300));
  };
  if (svcs.some(fora)) return 'bad';
  return svcs.length && svcs.every(checado) ? 'ok' : 'warn';
}

function renderMast() {
  const st = S.data.state || {};
  const svcs = st.services || [];
  const okCount = svcs.filter(checado).length;
  const estado = estadoDaProducao(svcs);
  $('#mast-status').innerHTML = `
    <span class="capsule"><span class="dot ${{ ok: 'ok pulse', warn: 'warn', bad: 'bad' }[estado]}"></span>
      <b>v${esc(st.last_app_version || '?')}</b>&nbsp;· prod ${estado === 'ok' ? 'healthy' : `${okCount}/${svcs.length} ok`}</span>
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

/* estado da tela -> hash; os filtros existem nas abas Issues, PRs e Produção */
function sincronizarHash() {
  const filtros = S.tab === 'issues' ? filtrosNaRota(S.fIssues) : S.tab === 'prs' ? filtrosPrsNaRota(S.fPrs)
    : S.tab === 'producao' ? filtrosProdNaRota(S.fProd) : {};
  gravarRota({ aba: S.tab, item: S.item, filtros });
}

/* hash -> estado da tela: no boot, no chip clicado e no voltar do navegador */
function irPara(rota) {
  S.erFull = false;
  S.tab = rota.aba;
  S.item = rota.item;
  if (rota.aba === 'issues') S.fIssues = filtrosDaRota(rota.filtros);
  if (rota.aba === 'prs') S.fPrs = filtrosPrsDaRota(rota.filtros);
  if (rota.aba === 'producao') S.fProd = filtrosProdDaRota(rota.filtros);
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
    issues: renderIssues, prs: renderPrs, producao: renderProducao, documentacao: renderDocumentacao,
  }[S.tab];
  view.innerHTML = fn ? fn() : '';
  if (S.tab === 'issues') wireIssues();
  const sub = S.tab === 'documentacao' ? subDoc() : null;
  if (sub === 'mapa') {
    try { desenharDiagramas(view); } catch { /* bloco fica no fallback de código cru */ }
    try { wireDiagramas(view); } catch { /* diagrama sem interação > aba quebrada */ }
    const cur = (S.data.snapshots || []).find(s => s.name === S.mapaDoc);
    try { wireArea(view, cur, areaCtx()); } catch { /* capa sem interação > aba quebrada */ }
  }
  if (sub === 'fluxo') {
    try { wireDiagramas(view); } catch { /* fluxo sem teclado > aba quebrada */ }
    marcarNoFluxo();
  }
  if (sub === 'decisoes') wireDecisoes();
  // tela cheia do ER só existe no Mapa; o lock de scroll segue o estado
  document.body.classList.toggle('er-lock', sub === 'mapa' && S.erFull);
  if (_ioView) _ioView.disconnect();
  if (_ioList) { _ioList.disconnect(); _ioList = null; }
  _ioView = revealOnScroll(view, '.rv');
}

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

/* Pessoa = quem assumiu (assignee); sem ninguém, quem criou (ADR 0062,
   emenda de 06/10/2026). O card marca "criou" quando a pessoa entrou pelo
   autor. SEM_RESP é o "ninguém assumiu": issues sem assignee. Mesmo valor e
   mesma regra do SEM_RESPONSAVEL e do responsaveis() do fases.py. */
const SEM_RESP = '(sem)';

function responsaveis(i) {
  if (i.assignees.length) return i.assignees;
  return i.author ? [i.author] : [];
}

function doResponsavel(i, resp) {
  return resp === SEM_RESP ? i.assignees.length === 0 : responsaveis(i).includes(resp);
}

function faseDe(i) {
  return ((S.data.fases || {}).issues || {})[i.number] || null;
}

/* matchIssue é passado a .filter, então o segundo parâmetro não pode ser
   o filtro (seria o índice): a variante com filtro explícito é à parte */
const matchIssue = i => matchIssueCom(i, S.fIssues);

function matchIssueCom(i, f) {
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
  return [`para ${esc(resp)}`, 'abertas que assumiu, ou criou e ninguém assumiu'];
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

/* faceta: quantas issues a opção mostraria com os OUTROS filtros como estão;
   zero fica esmaecido, mas continua clicável (a escolhida nunca some) */
function faceta(iss, chave, v) {
  return iss.filter(i => matchIssueCom(i, { ...S.fIssues, [chave]: v })).length;
}

function opcaoContada(act, chave, v, on, txt, extra = '') {
  const n = faceta(S.data.github.issues || [], chave, v);
  return opcao(act, v, on, `${txt}<span class="dd-n">${n}</span>`, `${extra}${n ? '' : ' data-zero="1"'}`);
}

function opcaoPessoa(login) {
  return opcaoContada('fresp', 'resp', login, S.fIssues.resp === login,
    `<span class="pessoa-dot"></span><span class="dd-txt">${nomeDoResponsavel(login)}</span>`,
    ` style="--pessoa:${corDaPessoa(login === SEM_RESP ? null : login)}"`);
}

/* algum filtro fora do padrão da aba (o botão limpar só existe nesse caso) */
function filtroAtivo(f = S.fIssues) {
  const z = filtrosVazios();
  return Object.keys(z).some(k => (f[k] || '') !== (z[k] || ''));
}

const botaoLimpar = act => `<button type="button" class="fchip limpar" data-act="${act}">limpar</button>`;

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
  const pessoas = [...new Set(iss.flatMap(responsaveis))].sort();
  const estados = [['OPEN', 'abertas'], ['CLOSED', 'fechadas'], ['all', 'todas']];
  const prds = iss.filter(i => i.is_prd && i.state === 'OPEN').sort((a, b) => b.number - a.number);
  const txt = t => `<span class="dd-txt">${t}</span>`;
  const todos = (act, chave, on) => opcaoContada(act, chave, '', on, txt('todos'));
  const menus = [
    dropdown('resp', 'responsável', f.resp ? nomeDoResponsavel(f.resp) : '',
      [todos('fresp', 'resp', !f.resp), ...pessoas.map(opcaoPessoa), opcaoPessoa(SEM_RESP)]),
    dropdown('state', 'estado', (estados.find(([v]) => v === f.state) || [, ''])[1],
      estados.map(([v, t]) => opcaoContada('fstate', 'state', v, f.state === v, txt(t)))),
    prds.length ? dropdown('prd', 'PRD', f.prd ? `#${f.prd}` : '',
      [todos('fprd', 'prd', !f.prd), ...prds.map(p => opcaoContada('fprd', 'prd', p.number, f.prd === p.number,
        `<span class="dd-num">#${p.number}</span>${txt(esc(p.title))}`))]) : '',
    ...gruposDeLabels(iss).map(([pref, ls]) => {
      const curta = l => esc(pref === 'outras' ? l : l.slice(pref.length + 1));
      return dropdown(pref, pref, ls.includes(f.label) ? curta(f.label) : '',
        [todos('flabel', 'label', !ls.includes(f.label)),
          ...ls.map(l => opcaoContada('flabel', 'label', l, f.label === l, txt(curta(l))))]);
    }),
  ];
  return `
  <div class="filtros rv">
    ${menus.join('')}
    <input class="search" id="fq" type="search" placeholder="buscar por título ou #número…" value="${esc(f.q)}">
    ${filtroAtivo(f) ? botaoLimpar('flimpar') : ''}
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
  // quem criou aparece como informação; só conta como responsável quando ninguém assumiu
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
    i.demanda ? '<span class="chip chip-demanda" title="nasceu de uma Demanda da aba Tecnologia">Demanda</span>' : '',
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
  const comFiltro = filtroAtivo();

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
      : (comFiltro && kidsShown.length > 0);
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
  ${renderQuadroPrs({ data: S.data, filtros: S.fPrs, item: S.item, depVer, fmtD, fmtDT })}
  </div>`;
}

/* ---------- PRODUÇÃO: linha do tempo do repositório (merges + deploys) ---------- */

/* history.json mistura "v0.45.4" e "0.43.1"; a aba exibe sempre com um v só */
const depVer = v => v ? 'v' + String(v).replace(/^v/, '') : '';

/* filtro da aba <-> rota: só a pessoa (quem mergeou, ou o responsável do deploy) */
const filtrosProdVazios = () => ({ resp: '' });
const filtrosProdDaRota = p => ({ resp: p.resp || '' });
const filtrosProdNaRota = f => ({ resp: f.resp });

const shaCurto = sha => String(sha || '·').slice(0, 7);
/* o responsável do deploy vem do coletor como um login, uma lista deles ou nada */
const pessoasDe = r => (r == null ? [] : [].concat(r));
/* as pessoas de um evento: quem mergeou o PR, ou o responsável do deploy */
const quemFez = ev => (ev.tipo === 'deploy' ? pessoasDe(ev.responsavel) : [ev.mergeado_por].filter(Boolean));

/* o deploy do evento no history.json: o índice que o clique (data-act="dep") e
   o hash (#producao/vX, pelo abrirItem) usam para abrir o card */
const indiceNoHistory = ev => S.data.history.findIndex(d => d.sha === ev.sha && d.at === ev.at);

const passaFiltroProd = ev => !S.fProd.resp || quemFez(ev).includes(S.fProd.resp);

/* o dropdown de pessoa da aba Issues, reaproveitado; a faceta conta eventos */
function filtrosProdHtml(eventos) {
  const f = S.fProd;
  const pessoas = [...new Set(eventos.flatMap(quemFez))].sort();
  const conta = login => eventos.filter(ev => !login || quemFez(ev).includes(login)).length;
  const op = (login, txt) => opcao('lfresp', login, f.resp === login,
    `${login ? '<span class="pessoa-dot"></span>' : ''}<span class="dd-txt">${txt}</span><span class="dd-n">${conta(login)}</span>`,
    `${login ? ` style="--pessoa:${corDaPessoa(login)}"` : ''}${conta(login) ? '' : ' data-zero="1"'}`);
  return `
  <div class="filtros lt-filtros rv">
    ${dropdown('lresp', 'responsável', f.resp ? esc(f.resp) : '', [op('', 'todos'), ...pessoas.map(p => op(p, esc(p)))])}
    ${f.resp ? botaoLimpar('lflimpar') : ''}
  </div>`;
}

/* etapas da barra empilhada: chave -> nome na tela. A largura é log do tempo:
   um build de 1 min ao lado de 3 dias de PR aberto continua visível */
const ETAPAS = { aberto: 'aberto', fila: 'fila até produção', merge: 'merge', build: 'build', health: 'health', total: 'total' };
const LARGURA_MIN_ROTULO = 14;  // % da barra a partir da qual o segmento mostra o rótulo

function segmentosDe(ev) {
  const e = ev.etapas || {};
  const segs = [];
  const add = (k, s, title = '') => { if (s != null && s > 0) segs.push({ k, s, title }); };
  add('aberto', e.aberto_s);
  add('fila', e.fila_s);
  const medido = e.merge_s != null || e.build_s || e.health_s != null;
  if (medido) {
    add('merge', e.merge_s);
    const builds = Object.entries(e.build_s || {}).filter(([, v]) => v != null);
    add('build', Math.max(0, ...builds.map(([, v]) => v)), builds.map(([sid, v]) => `${sid} ${durS(v)}`).join(' · '));
    add('health', e.health_s);
  } else {
    add('total', ev.duration_seconds);   // entrada antiga, sem etapas: só o total da subida
  }
  return segs;
}

function etapasHtml(ev) {
  const segs = segmentosDe(ev);
  if (!segs.length) return '';
  const pesos = segs.map(x => Math.log10(1 + x.s));
  const soma = pesos.reduce((a, b) => a + b, 0);
  return `<div class="etapas" role="img" aria-label="etapas do deploy">${segs.map((x, j) => {
    const pct = (pesos[j] / soma) * 100;
    const rot = `${ETAPAS[x.k]} ${durS(x.s)}`;
    const title = x.title ? `${rot} (${x.title})` : rot;
    return `<span class="etapa etapa-${x.k}" style="flex-basis:${pct.toFixed(1)}%" title="${esc(title)}">${
      pct >= LARGURA_MIN_ROTULO ? `<span class="etapa-rot">${esc(rot)}</span>` : ''}</span>`;
  }).join('')}</div>`;
}

/* chip de PR com a bolinha de quem mergeou (como a aba PRs faz com a issue) */
function chipPr(n, mergePorPr) {
  const m = mergePorPr.get(n);
  const cor = m && m.mergeado_por ? corDaPessoa(m.mergeado_por) : null;
  return `<a class="chip chip-pr" href="${rotaDe('prs', n)}"${m ? ` title="${esc(m.titulo)}"` : ''}${
    cor ? ` style="--pessoa:${cor}"` : ''}>${cor ? '<span class="pessoa-dot"></span>' : ''}PR #${n}</a>`;
}

const chipIssue = n => `<a class="chip" href="${rotaDe('issues', n)}">#${n}</a>`;

/* o deploy aberto: commit, escopo, duração da subida, env e notas */
function detalheDoDeploy(dp) {
  const env = (dp.env_changes || []).map(e => `${esc(e.service)} ${esc(e.action)} ${(e.keys || []).map(esc).join(', ')}`);
  return `
  <div class="pd-dep">
    <div class="pd-chips">
      ${dp.sha ? `<span class="chip">${esc(shaCurto(dp.sha))}</span>` : ''}
      ${(dp.scope || []).map(s => `<span class="chip">${esc(s)}</span>`).join('')}
      <span class="chip" title="duração da subida">${durS(dp.duration_seconds)}</span>
    </div>
    ${env.length ? `<p class="pd-notes mono">env: ${env.join(' · ')}</p>` : ''}
    ${dp.notes ? `<p class="pd-notes">${esc(dp.notes)}</p>` : ''}
  </div>`;
}

/* card cheio do deploy: versão, subject, resultado, responsável, data, PRs e
   issues que entraram, migrations e a barra das etapas; aberto, o detalhe */
function deployCardHtml(ev, pos, mergePorPr, alvo) {
  const i = indiceNoHistory(ev);
  const dp = S.data.history[i] || {};
  const ver = depVer(ev.app_version);
  const ok = ev.result === 'healthy';
  const open = S.expDep.has(i);
  const chips = [
    `<span class="badge ${ok ? 'b-green' : 'b-red'}">${esc(ev.result || '?')}</span>`,
    ...pessoasDe(ev.responsavel).map(pessoaHtml),
    ...(ev.prs || []).map(n => chipPr(n, mergePorPr)),
    ...(ev.issues || []).map(chipIssue),
    ...(ev.migrations_applied || []).map(m => `<span class="badge b-amber">⛁ ${esc(m)}</span>`),
    ev.rollback_target_sha ? `<span class="badge b-amber">rollback para ${esc(shaCurto(ev.rollback_target_sha))}</span>` : '',
  ].filter(Boolean).join('');
  return `
  <li class="lt-no lt-deploy rv ${ok ? '' : 'bad'}" style="--i:${Math.min(pos, 12)}">
    <article class="card pd-card lift"${alvo ? ' aria-current="true"' : ''}>
      <div class="pd-head" data-act="dep" data-i="${i}">
        <span class="pd-ver ${ver ? '' : 'unversioned'}">${esc(ver || shaCurto(ev.sha))}</span>
        <span class="pd-subject">${esc(ev.subject || '')}</span>
        <span class="pd-when">${esc(fmtDT(ev.at))}</span>
        ${ev.sha ? `<a class="pd-gh" href="${shaUrl(esc(ev.sha))}" target="_blank" rel="noopener" aria-label="abrir o commit ${esc(ev.sha)} no GitHub">↗</a>` : ''}
      </div>
      <div class="pd-chips">${chips}</div>
      ${etapasHtml(ev)}
      ${open ? `<div class="pd-body">${detalheDoDeploy(dp)}</div>` : ''}
    </article>
  </li>`;
}

/* merge que não entrou em deploy nenhum: nó pequeno, contorno tracejado na cor
   de quem mergeou. Ferramenta (nada em hospital-reunioes/) nunca entra; PR do
   app espera o próximo deploy */
function mergeNoHtml(ev, pos, versaoDoDeploy) {
  const etiqueta = ev.ferramenta ? 'só merge · ferramenta'
    : ev.deploy_sha ? `no ar na ${versaoDoDeploy(ev.deploy_sha) || shaCurto(ev.deploy_sha)}` : 'mergeado · sem deploy';
  return `
  <li class="lt-no lt-merge rv" style="--i:${Math.min(pos, 12)};--pessoa:${corDaPessoa(ev.mergeado_por)}">
    <div class="lt-merge-corpo">
      <a class="chip chip-pr" href="${rotaDe('prs', ev.pr)}">PR #${ev.pr}</a>
      <span class="lt-merge-tit">${esc(ev.titulo)}</span>
      <span class="chip lt-etiqueta">${esc(etiqueta)}</span>
      ${(ev.issues || []).map(chipIssue).join('')}
      ${ev.mergeado_por ? pessoaHtml(ev.mergeado_por) : ''}
      <span class="pd-when">${esc(fmtDT(ev.at))}</span>
    </div>
  </li>`;
}

/* a trilha: deploys como cards, merges sem deploy como nós; o merge que entrou
   num deploy visível aparece dentro do card dele, como chip de PR */
function trilhaHtml(eventos) {
  const mergePorPr = new Map(eventos.filter(e => e.tipo === 'merge').map(e => [e.pr, e]));
  const visiveis = eventos.filter(passaFiltroProd);
  if (!visiveis.length) return '<div class="empty rv">nenhum merge nem deploy na janela com este filtro</div>';
  const deploys = visiveis.filter(e => e.tipo === 'deploy');
  const shas = new Set(deploys.map(d => d.sha));
  const versaoDoDeploy = sha => depVer((eventos.find(d => d.tipo === 'deploy' && d.sha === sha) || {}).app_version);
  const alvo = deploys.find(e => depVer(e.app_version) === S.item) || null;
  const nos = visiveis.filter(e => e.tipo === 'deploy' || !shas.has(e.deploy_sha));
  return `<ol class="lt">${nos.map((ev, pos) => (ev.tipo === 'deploy'
    ? deployCardHtml(ev, pos, mergePorPr, ev === alvo)
    : mergeNoHtml(ev, pos, versaoDoDeploy))).join('')}</ol>`;
}

const STATUS_CLS = { healthy: 'prod-ok', warning: 'prod-warn' };

/* health do serviço pelo último check gravado no state.json. Serviço sem HTTP
   próprio (health_path nulo) é verificado pelo backend: "via backend" quando o
   corpo do health do backend disse ok, "sem verificação" quando não */
function healthTxt(s) {
  const h = s.last_health_check || {};
  const http = h.http_status ? `HTTP ${h.http_status}`
    : s.health_path == null ? (h.body_ok ? 'via backend' : 'sem verificação') : 'sem HTTP';
  return [http, h.latency_ms != null ? `${h.latency_ms} ms` : '', h.at ? fmtDT(h.at) : ''].filter(Boolean).join(' · ');
}

function renderDeploys() {
  const dep = S.data.history;
  const durs = dep.map(x => x.duration_seconds).filter(x => x != null);
  const st = S.data.state || {};
  // faixa do topo: a versão no ar e cada serviço com o health, do state.json
  const cells = [
    { k: 'no ar', v: depVer(st.last_app_version) || '·', s: `atualizado ${fmtDT(st.updated_at)}` },
    ...(st.services || []).map(s => ({
      k: s.id, v: s.status || '?', s: healthTxt(s), cls: STATUS_CLS[s.status] || 'prod-bad',
    })),
  ];
  const eventos = S.data.linha_do_tempo || [];

  return `
  <div class="tab-producao">
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
    <div class="k-label">duração dos builds (antigo ao recente)</div>
    ${spark([...durs].reverse())}
  </div>
  <div class="lt-cab rv">
    <span class="k-label">linha do tempo do repositório</span>
    <span class="lt-fonte">merges do GitHub (gh) e deploys do history.json, costurados pelo número do PR · últimos 60 dias ou 40 deploys</span>
  </div>
  ${filtrosProdHtml(eventos)}
  ${trilhaHtml(eventos)}
  </div>`;
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
  ${cabecalho('mapear', 'Mapa da app', 'docs/spec/snapshots · regenerado a cada deploy')}
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

/* ---------- DOCUMENTAÇÃO (fluxo · mapa · decisões · glossário) ---------- */

const ROTULO_SUB = { fluxo: 'Fluxo', mapa: 'Mapa', decisoes: 'Decisões', glossario: 'Glossário' };

/* a sub-pill é o item da rota (#documentacao/decisoes); o Glossário leva o
   termo depois dela (#documentacao/glossario/ata); sem item, abre no Fluxo */
function subDoc() {
  const sub = String(S.item || '').split('/')[0];
  return SUBS_DOC.includes(sub) ? sub : 'fluxo';
}

function renderDocumentacao() {
  const sub = subDoc();
  const corpo = { fluxo: renderFluxo, mapa: renderMapa, decisoes: renderDecisoes, glossario: renderGlossario }[sub]();
  return `
  <div class="docpills doc-subs rv" style="--i:0">
    ${SUBS_DOC.map(k => `<button class="fchip ${k === sub ? 'on' : ''}" data-act="docsub" data-sub="${k}">${ROTULO_SUB[k]}</button>`).join('')}
  </div>
  ${corpo}`;
}

/* ----- Fluxo: static/fluxo.json desenhado pelo renderer próprio ----- */

function ensureFluxo() {
  if (S.fluxo || S.fluxoPedido) return;
  S.fluxoPedido = true;
  fetch('/fluxo.json').then(r => r.json()).then(j => {
    S.fluxo = j;
    if (S.tab === 'documentacao' && subDoc() === 'fluxo') render();
  }).catch(e => {
    S.fluxoErro = String(e.message || e);
    S.fluxoPedido = false;
    if (S.tab === 'documentacao' && subDoc() === 'fluxo') render();
  });
}

const CLASSE_FLUXO = {
  auto: ['b-indigo', 'automático'], humano: ['b-amber', 'parada humana'],
  decisao: ['b-ghost', 'decisão'], fim: ['b-green', 'produção'],
};

/* o painel do passo aberto: a regra (campo detalhe do fluxo.json) e, em nó de
   skill, o link secundário para o SKILL.md no GitHub */
function painelFluxoHtml() {
  const n = S.fluxo && S.fluxoNo && (S.fluxo.nos || []).find(x => x.id === S.fluxoNo);
  if (!n) return '<div class="empty">clique num passo do fluxo para ler a regra dele; os passos de skill levam ao SKILL.md</div>';
  const [cls, rotulo] = CLASSE_FLUXO[n.classe] || CLASSE_FLUXO.auto;
  const subs = Array.isArray(n.sub) ? n.sub : n.sub ? [n.sub] : [];
  return `<div class="card fx-painel">
    <div class="fx-painel-head"><span class="badge ${cls}">${esc(rotulo)}</span><span class="k-label">${esc(subs.join(' · '))}</span></div>
    <h3>${esc(n.titulo)}</h3>
    <p>${esc(n.detalhe || '')}</p>
    ${n.skill ? `<a class="btn-pill outline" href="${esc(S.data.repo_url)}/blob/main/.claude/skills/${esc(n.skill)}/SKILL.md" target="_blank" rel="noopener">.claude/skills/${esc(n.skill)}/SKILL.md <span class="btn-arrow">↗</span></a>` : ''}
  </div>`;
}

function marcarNoFluxo() {
  view.querySelectorAll('.fx-no').forEach(g => g.classList.toggle('on', g.dataset.id === S.fluxoNo));
  const painel = $('#fluxo-painel');
  if (painel) painel.innerHTML = painelFluxoHtml();
}

function renderFluxo() {
  const cab = cabecalho('trabalhar', 'Do pedido à produção', 'ADR 0068 · static/fluxo.json, mantido junto com o /ask-pedro');
  if (!S.fluxo) {
    ensureFluxo();
    return `${cab}<div class="empty">${S.fluxoErro ? `fluxo.json indisponível: ${esc(S.fluxoErro)}` : 'carregando o fluxo…'}</div>`;
  }
  const svg = renderDiagrama(S.fluxo) || '<div class="empty">fluxo.json fora do formato que o renderer entende</div>';
  const legenda = (S.fluxo.legenda || []).map(l =>
    `<span><span class="sw sw-${esc(l.classe)}"></span>${esc(l.texto)}</span>`).join('');
  const portas = (S.fluxo.portas || []).map(pt =>
    `<tr><td><b>${esc(pt.porta)}</b></td><td>${esc(pt.quando)}</td><td class="mono">${esc(pt.caminho)}</td></tr>`).join('');
  return `${cab}
  <div class="card fx-capa rv" style="--i:1">
    <div class="fx-hint glass-cap">clique num passo para ler a regra · âmbar é onde alguém precisa agir</div>
    ${svg}
  </div>
  <div id="fluxo-painel" class="rv" style="--i:2">${painelFluxoHtml()}</div>
  <div class="fx-legenda rv" style="--i:3">${legenda}</div>
  ${portas ? `<div class="card md rv" style="--i:4">
    <span class="k-label">as três portas</span>
    <table class="fx-portas"><thead><tr><th>Porta</th><th>Quando</th><th>Caminho</th></tr></thead><tbody>${portas}</tbody></table>
  </div>` : ''}`;
}

/* ----- Decisões: ADRs agrupadas pelo tema do docs/adr/README.md ----- */

/* sem índice parseável, o tema é o prefixo do título (o que vem antes dos
   dois-pontos); sem prefixo, "Outras" */
function temasPorPrefixo(adrs) {
  const grupos = new Map();
  adrs.forEach(a => {
    const m = /^(.{3,40}?):/.exec(a.title || '');
    const tema = m ? m[1] : 'Outras';
    if (!grupos.has(tema)) grupos.set(tema, []);
    grupos.get(tema).push(a.number);
  });
  return [...grupos].map(([tema, numeros]) => ({ tema, numeros }));
}

function adrGrupos() {
  const adrs = S.data.adrs || [];
  const temas = (S.data.adr_temas && S.data.adr_temas.length) ? S.data.adr_temas : temasPorPrefixo(adrs);
  const q = S.adrQ.trim().toLowerCase();
  const visivel = a => (S.adrHist || a.status === 'accepted')
    && (!q || `${a.title} ${a.body_md}`.toLowerCase().includes(q));
  const porNumero = new Map(adrs.map((a, i) => [a.number, i]));
  const grupos = temas.map(t => ({ tema: t.tema, idx: t.numeros.map(n => porNumero.get(n)).filter(i => i != null) }));
  const noIndice = new Set(grupos.flatMap(g => g.idx));
  const fora = adrs.map((_, i) => i).filter(i => !noIndice.has(i));
  if (fora.length) grupos.push({ tema: 'Fora do índice', idx: fora });
  return grupos.map(g => ({ tema: g.tema, idx: g.idx.filter(i => visivel(adrs[i])) })).filter(g => g.idx.length);
}

function adrCard(a, i, k) {
  return `
      <article class="card tst adr lift sp6 rv ${a.status === 'accepted' ? '' : 'adr-hist'}" style="--i:${Math.min(k, 12)}" data-act="adr" data-i="${i}">
        <span class="tst-quote" aria-hidden="true">&ldquo;</span>
        <h3 class="tst-corpo">${esc(a.title)}</h3>
        ${a.decisao ? `<div class="adr-frase md">${md(a.decisao)}</div>` : ''}
        ${S.expAdr.has(i) ? `<div class="adr-body md">${md(a.body_md)}</div>` : ''}
        <div class="tst-foot">
          <span class="tst-ref">ADR ${String(a.number ?? '').padStart(2, '0')} · ${esc(a.file)}</span>
          ${adrStatusBadge(a.status)}${adrPointerBadge(a)}
        </div>
      </article>`;
}

function listaAdrsHtml() {
  const adrs = S.data.adrs || [];
  const grupos = adrGrupos();
  if (!grupos.length) return '<div class="empty">nenhuma decisão bate com a busca</div>';
  return grupos.map(g => `
    <div class="adr-tema rv"><span class="k-label">${esc(g.tema)} · ${g.idx.length}</span></div>
    <div class="grid g12">${g.idx.map((i, k) => adrCard(adrs[i], i, k)).join('')}</div>`).join('');
}

function renderDecisoes() {
  const hist = (S.data.adrs || []).filter(a => a.status !== 'accepted').length;
  return `
  ${cabecalho('decidir', 'Decisões de arquitetura', 'docs/adr · curado por humano · só as aceitas, por tema')}
  <div class="adr-tools rv">
    <input class="search" id="adrq" type="search" placeholder="buscar no título e no corpo" value="${esc(S.adrQ)}" autocomplete="off">
    <button class="fchip ${S.adrHist ? 'on' : ''}" data-act="adrhist" aria-pressed="${S.adrHist}">ver histórico (${hist})</button>
  </div>
  <div id="adrlist">${listaAdrsHtml()}</div>`;
}

/* a busca redesenha só a lista: o campo mantém o foco e o texto */
function wireDecisoes() {
  const q = $('#adrq');
  if (!q) return;
  q.addEventListener('input', () => {
    S.adrQ = q.value;
    const el = $('#adrlist');
    if (!el) return;
    el.innerHTML = listaAdrsHtml();
    if (_ioList) _ioList.disconnect();
    _ioList = revealOnScroll(el, '.rv');
  });
}

/* ----- Glossário: CONTEXT.md com um índice de termos e âncora por termo ----- */

const slugDe = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

/* os termos do CONTEXT.md: cada `**Termo**:` no começo de linha, agrupado
   pela seção `## X` em que está */
function termosDoGlossario(mdTexto) {
  const secoes = [];
  let atual = null;
  String(mdTexto || '').split('\n').forEach(linha => {
    const h = /^## (.+?)\s*$/.exec(linha);
    if (h) { atual = { titulo: h[1], termos: [] }; secoes.push(atual); return; }
    const t = /^\*\*(.+?)\*\*/.exec(linha);
    if (t && atual) atual.termos.push({ nome: t[1], slug: slugDe(t[1]) });
  });
  return secoes.filter(s => s.termos.length);
}

function renderGlossario() {
  const src = S.data.context_md || '';
  const secoes = termosDoGlossario(src);
  const alvo = String(S.item || '').startsWith('glossario/') ? S.item.slice('glossario/'.length) : '';
  let html = md(src || '_CONTEXT.md não encontrado_');
  secoes.forEach(sec => sec.termos.forEach(t => {
    const abre = `<p><strong>${esc(t.nome)}</strong>`;
    const atual = t.slug === alvo;
    html = html.replace(abre, `<p id="g-${t.slug}" class="g-termo${atual ? ' g-alvo' : ''}"${atual ? ' aria-current="true"' : ''}><strong>${esc(t.nome)}</strong>`);
  }));
  const indice = secoes.map(sec => `
    <div class="g-secao"><span class="k-label">${esc(sec.titulo)}</span>
      <div class="g-chips">${sec.termos.map(t => `<a class="chip" href="${rotaDe('documentacao', `glossario/${t.slug}`)}">${esc(t.nome)}</a>`).join('')}</div>
    </div>`).join('');
  return `
  ${cabecalho('entender', 'Glossário do domínio', 'CONTEXT.md · o que as palavras significam aqui')}
  ${indice ? `<div class="card g-indice rv" style="--i:1">${indice}</div>` : ''}
  <div class="card tst rv" style="--i:2">
    <span class="tst-quote" aria-hidden="true">&ldquo;</span>
    <div class="md">${html}</div>
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
    S.fPrs = alternarPessoa(S.fPrs, t.dataset.v);
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
  } else if (act === 'adrhist') {
    S.adrHist = !S.adrHist;
    render();
  } else if (act === 'docsub') {
    // sub-pill de Documentação: vira o item da rota; o termo do glossário cai
    S.item = t.dataset.sub;
    S.erFull = false;
    render();
    window.scrollTo({ top: 0 });
  } else if (act === 'fluxono') {
    // passo do fluxo: só o painel e o destaque mudam, sem redesenhar o SVG
    S.fluxoNo = S.fluxoNo === t.dataset.id ? null : t.dataset.id;
    marcarNoFluxo();
  } else if (act === 'menu') {
    S.menu = S.menu === t.dataset.v ? null : t.dataset.v;
    marcarMenu();
  } else if (['fstate', 'fresp', 'fprd', 'flabel'].includes(act)) {
    // opção do dropdown: escolhe e fecha; "todos" (v vazio) limpa
    const chave = { fstate: 'state', fresp: 'resp', fprd: 'prd', flabel: 'label' }[act];
    S.fIssues[chave] = act === 'fprd' ? (Number(t.dataset.v) || null) : t.dataset.v;
    S.menu = null;
    render();
  } else if (act === 'flimpar') {
    S.fIssues = filtrosVazios();
    render();
  } else if (act === 'pflimpar') {
    S.fPrs = filtrosPrsVazios();
    render();
  } else if (act === 'lfresp') {
    // o dropdown de pessoa da linha do tempo: escolhe e fecha; "todos" (v vazio) limpa
    S.fProd.resp = t.dataset.v;
    S.menu = null;
    render();
  } else if (act === 'lflimpar') {
    S.fProd = filtrosProdVazios();
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
