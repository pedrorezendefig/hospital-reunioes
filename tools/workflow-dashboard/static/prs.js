'use strict';

/* Aba PRs do Hospital OS (ADR 0062, decisão 7; issue #946): quadro com as
   seis fases do PR em colunas e uma raia por pessoa, na cor dela. A fase vem
   pronta do fases.py (S.data.fases.prs); aqui só se agrupa, filtra e desenha.
   A pessoa do PR é quem assumiu a issue que ele fecha (assignee, emenda de
   06/10/2026 da ADR 0062); sem assignee, a raia é "ninguém assumiu". */

import { esc } from './ui.js';
import { corDaPessoa } from './pessoas.js';
import { montarHash } from './router.js';

/* [fase do fases.py, nome na tela], na ordem do quadro */
export const COLUNAS = [
  ['aberto_sem_ci', 'Aberto sem CI'],
  ['ci_vermelho', 'CI vermelho'],
  ['esperando_revisor', 'Esperando revisor'],
  ['verde_esperando_merge', 'Verde esperando merge'],
  ['mergeado_sem_deploy', 'Mergeado sem deploy'],
  ['em_producao', 'Em produção'],
];

/* mesmo valor do SEM_RESP do app.js e do SEM_RESPONSAVEL do fases.py */
const SEM_RESP = '(sem)';
/* card parado há mais dias que isto na mesma coluna ganha destaque */
export const LIMITE_DIAS = 3;
/* Em produção é o fim do caminho: não é gargalo nem envelhece, e guarda o
   histórico inteiro; o quadro mostra só a última semana dela, a não ser com
   um PRD filtrado (aí todos os PRs do PRD) ou com o PR apontado pelo hash */
const FIM = 'em_producao';
export const JANELA_PRODUCAO_DIAS = 7;

/* filtros da aba <-> filtros da rota (texto; vazio = sem filtro). resp é
   uma lista: várias pessoas ao mesmo tempo, uma raia para cada */
export const filtrosPrsVazios = () => ({ resp: [], prd: null, abertos: false });
export const filtrosPrsDaRota = p => ({
  resp: p.resp ? p.resp.split(',').filter(Boolean) : [], prd: Number(p.prd) || null, abertos: p.abertos === '1',
});
export const filtrosPrsNaRota = f => ({ resp: f.resp.join(','), prd: f.prd ? String(f.prd) : '', abertos: f.abertos ? '1' : '' });

/* liga/desliga uma pessoa no filtro (o chip clicado de novo sai) */
export const alternarPessoa = (f, login) => ({
  ...f, resp: f.resp.includes(login) ? f.resp.filter(p => p !== login) : [...f.resp, login],
});

/* quem assumiu as issues que o PR fecha; ninguém = SEM_RESP */
function pessoasDoPr(pr, issues) {
  const quem = [...new Set(pr.closes.flatMap(n => (issues[n] || {}).assignees || []))].sort();
  return quem.length ? quem : [SEM_RESP];
}

/* o PR fecha o PRD ou uma fatia dele */
const doPrd = (pr, prd, issues) => pr.closes.some(n => n === prd || (issues[n] || {}).parent === prd);

/* mais tempo na coluna primeiro: o card parado aparece em cima */
const porIdade = (a, b) => (b.fase.dias_na_coluna ?? -1) - (a.fase.dias_na_coluna ?? -1) || b.pr.number - a.pr.number;

/* a coluna com mais cards que cada uma das outras; empate não tem gargalo */
function colunaMaisCheia(contagem) {
  const [[k, max], [, segundo]] = COLUNAS.filter(([c]) => c !== FIM)
    .map(([c]) => [c, contagem[c]]).sort((a, b) => b[1] - a[1]);
  return max > segundo ? k : null;
}

const ehVelho = fase => fase.fase !== FIM && fase.dias_na_coluna > LIMITE_DIAS;

const diasTxt = d => d == null ? '' : d === 0 ? 'hoje na coluna' : `${d} ${d === 1 ? 'dia' : 'dias'} na coluna`;

const nomeDe = login => (login === SEM_RESP ? 'ninguém assumiu' : esc(login));
const corDe = login => corDaPessoa(login === SEM_RESP ? null : login);

/* chip navega dentro do painel pelo hash; o GitHub fica no ↗ do card. O
   chip da issue leva o título dela no title: o que o PR entrega, sem sair */
const chip = (aba, item, txt, cls = '', title = '') =>
  `<a class="chip${cls}" href="${esc(montarHash({ aba, item }))}"${title ? ` title="${esc(title)}"` : ''}>${esc(txt)}</a>`;

const chipDaIssue = (n, ctx) => chip('issues', String(n), `#${n}`, '', (ctx.issues[n] || {}).title || '');

const ghLink = (ctx, n) =>
  `<a class="pr-gh" href="${esc(ctx.data.repo_url)}/pull/${esc(n)}" target="_blank" rel="noopener" aria-label="abrir o PR #${esc(n)} no GitHub">↗</a>`;

/* o card que o hash aponta fica em destaque (e é o alvo da rolagem do app.js) */
const destaque = (ctx, n) => (ctx.item === String(n) ? ' aria-current="true"' : '');

/* Em produção é histórico: uma linha por PR (número, issue e versão), o
   título fica no title; a raia de produção cresce sem engolir o quadro */
function miniHtml({ pr, fase }, ctx) {
  const versao = fase.versao ? ctx.depVer(fase.versao) : '';
  const chips = [
    ...pr.closes.map(n => chipDaIssue(n, ctx)),
    versao ? chip('producao', versao, versao, ' chip-versao') : '',
  ].join('');
  return `<article class="pr-card pr-mini" data-act="pr" data-n="${pr.number}" title="${esc(pr.title)}"${destaque(ctx, pr.number)}>
    <span class="pr-num">PR #${pr.number}</span>${chips}${ghLink(ctx, pr.number)}
  </article>`;
}

function cardHtml(c, ctx) {
  if (c.fase.fase === FIM) return miniHtml(c, ctx);
  const { pr, fase } = c;
  const versao = fase.versao ? ctx.depVer(fase.versao) : '';
  const chips = [
    ...pr.closes.map(n => chipDaIssue(n, ctx)),
    versao ? chip('producao', versao, versao, ' chip-versao') : '',
    fase.conflito ? '<span class="badge b-red pr-conflito">conflito</span>' : '',
  ].filter(Boolean).join('');
  const velho = ehVelho(fase);
  return `<article class="pr-card${velho ? ' pr-velho' : ''}" data-act="pr" data-n="${pr.number}"${velho ? ` title="parado há mais de ${LIMITE_DIAS} dias na coluna"` : ''}${destaque(ctx, pr.number)}>
    <div class="pr-card-topo"><span class="pr-num">PR #${pr.number}</span>${ghLink(ctx, pr.number)}</div>
    <div class="pr-tit">${esc(pr.title)}</div>
    ${chips ? `<div class="pr-chips">${chips}</div>` : ''}
    <div class="pr-meta"><span class="pr-branch">${esc(pr.head_ref || '')}</span><span class="pr-dias">${diasTxt(fase.dias_na_coluna)}</span></div>
  </article>`;
}

/* tentativa: PR fechado sem merge, fora das colunas, na faixa cinza */
function tentativaHtml({ pr, fase }, ctx) {
  const issues = pr.closes.length
    ? pr.closes.map(n => chipDaIssue(n, ctx)).join('')
    : '<span class="chip">sem issue</span>';
  return `<article class="pr-tentativa" data-act="pr" data-n="${pr.number}"${destaque(ctx, pr.number)}>
    <span class="pr-num">PR #${pr.number}</span><span class="pr-tit">${esc(pr.title)}</span>
    <span class="chip">fechado ${esc(ctx.fmtD(fase.desde))}</span>${issues}${ghLink(ctx, pr.number)}
  </article>`;
}

function faixaHtml(tentativas, ctx) {
  if (!tentativas.length) return '';
  const recentes = [...tentativas].sort((a, b) => String(b.fase.desde || '').localeCompare(String(a.fase.desde || '')));
  return `<section class="pr-tentativas rv">
    <div class="k-label">tentativas · fechados sem merge (${tentativas.length})</div>
    <div class="pr-tentativas-lista">${recentes.map(c => tentativaHtml(c, ctx)).join('')}</div>
  </section>`;
}

function filtroChip(act, v, on, txt, attrs = '') {
  return `<button type="button" class="fchip${on ? ' on' : ''}" data-act="${act}" data-v="${esc(v)}" aria-pressed="${on}"${attrs}>${txt}</button>`;
}

const filtroAtivo = f => JSON.stringify(f) !== JSON.stringify(filtrosPrsVazios());

function filtrosHtml(pessoas, prds, f) {
  const linha = (rot, chips) => chips
    ? `<div class="filtro"><span class="filtro-rot">${rot}</span><div class="filtro-chips">${chips}</div></div>` : '';
  const pessoa = login => `<button type="button" class="fchip fpessoa${f.resp.includes(login) ? ' on' : ''}" data-act="pfresp" data-v="${esc(login)}" aria-pressed="${f.resp.includes(login)}" style="--pessoa:${corDe(login)}"><span class="pessoa-dot"></span>${nomeDe(login)}</button>`;
  return `
  <div class="filtros rv">
    ${linha('pessoa', pessoas.map(pessoa).join(''))}
    ${linha('PRD', prds.map(p => filtroChip('pfprd', p.number, f.prd === p.number, `#${p.number}`, ` title="${esc(p.title)}"`)).join(''))}
    ${linha('estado', filtroChip('pfabertos', '1', f.abertos, 'só abertos')
      + (filtroAtivo(f) ? '<button type="button" class="fchip limpar" data-act="pflimpar">limpar</button>' : ''))}
  </div>`;
}

function indisponivel(data) {
  const fases = data.fases;
  const motivo = fases && fases.erro
    ? `quadro indisponível: ${esc(fases.erro)}`
    : 'o quadro lê os PRs pelo <span class="mono">gh</span>, que está indisponível agora, veja o aviso no topo';
  return `<div class="empty rv">${motivo}</div>`;
}

/* ctx: { data, filtros, item, depVer, fmtD } (valores puros, sem o estado do app.js) */
export function renderQuadroPrs(ctx) {
  const { data, filtros: f, item } = ctx;
  if (!data.fases || !data.fases.prs || data.fases.erro) return indisponivel(data);
  const fases = data.fases.prs;
  const issues = Object.fromEntries((data.github.issues || []).map(i => [i.number, i]));
  ctx = { ...ctx, issues };
  const todos = (data.github.prs || [])
    .filter(pr => fases[pr.number])
    .map(pr => ({ pr, fase: fases[pr.number], pessoas: pessoasDoPr(pr, issues) }));
  const passa = c => (!f.resp.length || c.pessoas.some(p => f.resp.includes(p))) && (!f.prd || doPrd(c.pr, f.prd, issues))
    && (!f.abertos || c.pr.state === 'OPEN');
  const naJanela = c => c.fase.fase !== FIM || f.prd || item === String(c.pr.number)
    || (c.fase.dias_na_coluna ?? Infinity) <= JANELA_PRODUCAO_DIAS;

  const noQuadro = todos.filter(c => COLUNAS.some(([k]) => k === c.fase.fase));
  const filtrados = noQuadro.filter(passa);
  const cards = filtrados.filter(naJanela).sort(porIdade);
  const foraDaJanela = filtrados.length - cards.length;
  const tentativas = todos.filter(c => c.fase.fase === 'fechado_sem_merge' && passa(c));

  const raias = new Map();
  for (const c of cards) {
    for (const p of c.pessoas.filter(p => !f.resp.length || f.resp.includes(p))) {
      if (!raias.has(p)) raias.set(p, []);
      raias.get(p).push(c);
    }
  }
  const porNome = (a, b) => (a === SEM_RESP) - (b === SEM_RESP) || a.localeCompare(b);
  const contagem = Object.fromEntries(COLUNAS.map(([k]) => [k, cards.filter(c => c.fase.fase === k).length]));
  const cheia = colunaMaisCheia(contagem);
  const naCheia = k => (k === cheia ? ' pr-col-cheia' : '');

  const cabecalho = `<div class="pr-linha pr-cab"><div class="pr-raia-nome"></div>${COLUNAS.map(([k, nome]) =>
    `<div class="pr-col-cab${naCheia(k)}" data-col="${k}"><span>${nome}</span><span class="pr-col-n">${contagem[k]}</span></div>`).join('')}</div>`;
  const linhas = [...raias.keys()].sort(porNome).map(login => `
    <div class="pr-raia pr-linha" data-raia="${esc(login)}" style="--pessoa:${corDe(login)}">
      <div class="pr-raia-nome"><span class="pessoa-dot"></span>${nomeDe(login)}</div>
      ${COLUNAS.map(([k]) => `<div class="pr-celula${naCheia(k)}" data-col="${k}">${
        raias.get(login).filter(c => c.fase.fase === k).map(c => cardHtml(c, ctx)).join('')}</div>`).join('')}
    </div>`).join('');

  const pessoas = [...new Set(noQuadro.flatMap(c => c.pessoas).filter(p => p !== SEM_RESP))].sort(porNome);
  const prds = (data.github.issues || [])
    .filter(i => i.is_prd && (i.state === 'OPEN' || i.number === f.prd) && todos.some(c => doPrd(c.pr, i.number, issues)))
    .sort((a, b) => b.number - a.number);
  const nota = foraDaJanela
    ? `<div class="pr-nota rv">Em produção mostra só a última semana: ${foraDaJanela} ${foraDaJanela === 1 ? 'PR mais antigo fica fora' : 'PRs mais antigos ficam fora'}; com um PRD filtrado, aparecem todos os dele.</div>`
    : '';
  const visiveis = new Set([...cards, ...tentativas].map(c => String(c.pr.number)));
  const fora = item && !visiveis.has(item)
    ? `<div class="pr-fora rv">O PR #${esc(item)} não aparece no quadro com estes filtros. ${ghLink(ctx, item)}</div>`
    : '';

  return `${filtrosHtml([...pessoas, SEM_RESP], prds, f)}
  ${fora}
  <div class="pr-quadro-rolagem rv"><div class="pr-quadro">${cabecalho}${linhas}</div></div>
  ${nota}
  ${faixaHtml(tentativas, ctx)}`;
}
