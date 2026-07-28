'use strict';

/* Capas visuais das áreas da aba Mapa (visual-first): cada snapshot ganha uma
   visualização própria como conteúdo principal (explorador de rotas, catálogo
   de fichas, timeline de migrations, diagrama de contexto, árvore anotada) e
   o markdown original fica no "ver fonte". Os dados estruturados chegam
   prontos do coletor (areas.py); doc sem dados cai no markdown renderizado de
   sempre (renderArea devolve null). Conteúdo dinâmico é sempre escapado. */

import { esc } from './ui.js';
import { TABELAS } from './content/tabelas.js';
import { COR_DOMINIO, dominioDe } from './diagramas.js';

/* ---------- ROTAS: explorador por domínio funcional ---------- */

const ORDEM_DOM_ROTAS = ['Reuniões', 'POPs', 'Pessoas', 'Infra'];
const ROTAS_DESC_DOM = {
  'Reuniões': 'agendar, processar com IA, validar, assinar',
  POPs: 'setores, elaboração, revisão, publicação',
  Pessoas: 'cadastro, login, perfis e preferências',
  Infra: 'admin, notificações, webhooks e saúde',
};

function dominioRota(rota) {
  if (rota.startsWith('/pops')) return 'POPs';
  if (/^\/(reunioes|pendencias|transcricao|webhooks)/.test(rota)) return 'Reuniões';
  if (/^\/(participantes|auth|perfil|configuracoes)/.test(rota)) return 'Pessoas';
  return 'Infra';
}

const METODO_CLS = { GET: 'rt-get', POST: 'rt-post', PATCH: 'rt-patch', PUT: 'rt-patch', DELETE: 'rt-del' };

function rotasFlat(dados) {
  return dados.grupos.flatMap(g => g.rotas.map(r => ({ ...r, arquivo: g.arquivo })));
}

export function rotasListHtml(dados, q) {
  const todas = rotasFlat(dados);
  const query = (q || '').toLowerCase();
  const bate = r => !query || `${r.metodo} ${r.rota} ${r.desc}`.toLowerCase().includes(query);
  const blocos = [];
  for (const dom of ORDEM_DOM_ROTAS) {
    const rotas = todas.filter(r => dominioRota(r.rota) === dom).filter(bate)
      .sort((a, b) => a.rota.localeCompare(b.rota) || a.metodo.localeCompare(b.metodo));
    if (!rotas.length) continue;
    blocos.push(`
    <section class="card rt-dom rv" style="--dom:${COR_DOMINIO[dom] || 'var(--purple)'}">
      <div class="rt-dom-head">
        <span class="rt-dom-nome">${esc(dom.toUpperCase())} · ${rotas.length}</span>
        <span class="rt-dom-desc">${esc(ROTAS_DESC_DOM[dom] || '')}</span>
      </div>
      ${rotas.map(r => `
      <div class="rt-row">
        <span class="rt-met ${METODO_CLS[r.metodo] || ''}">${esc(r.metodo)}</span>
        <code class="rt-path">${esc(r.rota)}</code>
        <span class="rt-desc">${esc(r.desc)}</span>
        <span class="rt-auth ${r.auth ? 'rt-lock' : ''}" title="${r.auth ? 'exige login (JWT)' : 'sem exigência de login neste endpoint'}">${r.auth ? '🔒' : 'livre'}</span>
        <span class="rt-file">${esc(r.arquivo)}</span>
      </div>`).join('')}
    </section>`);
  }
  return blocos.join('') || '<div class="empty">nenhuma rota bate com a busca</div>';
}

function renderRotas(dados, ctx) {
  const todas = rotasFlat(dados);
  const auth = todas.filter(r => r.auth).length;
  return `
  <div class="grid g12 rv" style="margin-bottom:14px">
    <div class="card sp4"><div class="stat"><div class="k">endpoints</div><div class="v">${todas.length}</div><div class="s">${dados.grupos.length} routers no backend</div></div></div>
    <div class="card sp4"><div class="stat"><div class="k">exigem login</div><div class="v" style="color:var(--indigo)">${Math.round(auth / todas.length * 100)}<small>%</small></div><div class="s">${todas.length - auth} abertos (webhook, health…)</div></div></div>
    <div class="card sp4"><div class="stat"><div class="k">domínios</div><div class="v" style="color:var(--coral)">4</div><div class="s">mesmos grupos e cores do mapa</div></div></div>
  </div>
  <div class="controls rv">
    <input class="search" id="rt-q" type="search" placeholder="buscar rota ou descrição…" value="${esc(ctx.rotasQ || '')}">
    <span class="rt-hint">agrupado por domínio funcional · passe o mouse numa linha para ver o arquivo de origem</span>
  </div>
  <div id="rt-list">${rotasListHtml(dados, ctx.rotasQ)}</div>`;
}

/* ---------- ENTIDADES: catálogo de fichas ligado ao mapa ---------- */

function renderEntidades(dados, ctx) {
  const grupos = new Map();
  dados.tabelas.forEach(t => {
    const d = dominioDe(t.nome);
    if (!grupos.has(d)) grupos.set(d, []);
    grupos.get(d).push(t);
  });
  const sel = dados.tabelas.find(t => t.nome === ctx.entTab) || dados.tabelas[0];
  const nav = [...grupos.entries()].map(([dom, ts]) => `
    <div class="ent-grupo" style="--dom:${COR_DOMINIO[dom] || 'var(--purple)'}">
      <div class="ent-grupo-nome">${esc(dom.toUpperCase())} · ${ts.length}</div>
      ${ts.map(t => `<button class="ent-item ${t.nome === sel.nome ? 'on' : ''}" data-act="enttab" data-t="${esc(t.nome)}">${esc(t.nome)}</button>`).join('')}
    </div>`).join('');
  return `
  <div class="ent-capa rv">
    <nav class="ent-nav card">${nav}</nav>
    ${fichaHtml(sel, ctx)}
  </div>`;
}

function fichaHtml(t, ctx) {
  const cur = TABELAS[t.nome] || {};
  const notas = cur.colunas || {};
  const dom = dominioDe(t.nome);
  const rels = (ctx.relacoes || []).filter(r => r.origem === t.nome || r.destino === t.nome);
  const linhas = t.colunas.map(c => {
    const chave = c.pk ? '<span class="er-k er-k-pk">PK</span>' : c.fk_ref ? '<span class="er-k er-k-fk">FK</span>' : '';
    const nota = notas[c.nome] ? `<div class="ent-nota">${esc(notas[c.nome])}</div>` : '';
    return `<tr class="${c.pk || c.nn ? '' : 'opcional'}">
      <td class="ent-chave">${chave}</td>
      <td class="ent-campo"><code>${esc(c.nome)}</code>${nota}</td>
      <td class="ent-tipo">${esc(c.tipo)}</td>
      <td class="ent-def">${esc(c.default || '')}</td>
      <td class="ent-fk">${c.fk_ref ? `→ ${esc(c.fk_ref)}` : ''}</td>
    </tr>`;
  }).join('');
  const alteradas = t.alteradas.map(a => `<span class="chip">${esc(a)}</span>`).join('');
  return `
  <article class="card ent-ficha" style="--dom:${COR_DOMINIO[dom] || 'var(--purple)'}">
    <div class="ent-head">
      <h3>${esc(t.nome)}</h3>
      <span class="badge b-ghost">${esc(dom)}</span>
      <span class="badge b-ghost">${t.colunas.length} colunas</span>
      <span class="badge b-ghost">${rels.length} relaç${rels.length === 1 ? 'ão' : 'ões'}</span>
    </div>
    ${cur.resumo ? `<p class="ent-resumo">${esc(cur.resumo)}</p>` : '<p class="ent-resumo ent-sem-verbete">sem verbete funcional ainda (static/content/tabelas.js)</p>'}
    <div class="ent-origem">nasceu em <span class="chip">${esc(t.origem || '?')}</span>${alteradas ? ` · mexeram nela: ${alteradas}` : ''}</div>
    <table class="ent-tab">
      <thead><tr><th></th><th>campo</th><th>tipo</th><th>default</th><th>aponta pra</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    <div class="ent-legenda">campos apagados são opcionais · PK identifica a linha · FK aponta pra outra tabela</div>
    ${t.indexes.length ? `<details class="techbox"><summary>${t.indexes.length} indexes</summary><div class="techbox-body">
      ${t.indexes.map(i => `<div class="ent-idx"><code>${esc(i.nome)}</code> em <code>${esc(i.campos)}</code>${i.de ? ` <span class="ent-idx-de">(de ${esc(i.de)})</span>` : ''}</div>`).join('')}
    </div></details>` : ''}
  </article>`;
}

/* ---------- MIGRATIONS: timeline vertical com marcos ---------- */

function dominioMigration(m) {
  const s = `${m.arquivo} ${m.resumo}`.toLowerCase();
  if (s.includes('pop')) return 'POPs';
  if (/participante|super_admin|access_profile|taxonomy|cargo|user_preferences|email_nullable|secretaria|signup/.test(s)) return 'Pessoas';
  if (/reunio|pendencia|token|comentario|nota|ata|lembrete|assinatura|clicksign|soft_delete|importacao|recorrencia|aprovada|facilitador|prompts/.test(s)) return 'Reuniões';
  return 'Infra';
}

function migBadges(m) {
  const b = [];
  if (m.criadas) b.push(`<span class="badge b-green">criou ${m.criadas} tabela${m.criadas === 1 ? '' : 's'}</span>`);
  if (m.alteradas) b.push(`<span class="badge b-amber">alterou ${m.alteradas}</span>`);
  if (m.drops) b.push(`<span class="badge b-red">removeu ${m.drops}</span>`);
  if (m.indexes) b.push(`<span class="badge b-ghost">${m.indexes} índice${m.indexes === 1 ? '' : 's'}</span>`);
  if (!b.length) b.push('<span class="badge b-ghost">só dados / regras</span>');
  return b.join('');
}

function renderMigrations(dados) {
  const vistos = new Set();
  const itens = dados.migrations.map(m => {
    const dom = dominioMigration(m);
    const marco = !vistos.has(dom);
    vistos.add(dom);
    return `
    ${marco ? `<div class="mg-marco rv" style="--dom:${COR_DOMINIO[dom] || 'var(--purple)'}">nasce o domínio ${esc(dom)}</div>` : ''}
    <div class="mg-item rv" style="--dom:${COR_DOMINIO[dom] || 'var(--purple)'}">
      <span class="mg-n">${m.n}</span>
      <div class="mg-corpo">
        <div class="mg-resumo">${esc(m.resumo)}</div>
        <div class="mg-meta">${migBadges(m)}<span class="mg-arquivo">${esc(m.arquivo)}</span></div>
      </div>
    </div>`;
  }).join('');
  return `
  <div class="grid g12 rv" style="margin-bottom:14px">
    <div class="card sp4"><div class="stat"><div class="k">migrations</div><div class="v">${dados.migrations.length}</div><div class="s">a história do banco, em ordem</div></div></div>
    <div class="card sp4"><div class="stat"><div class="k">tabelas criadas</div><div class="v" style="color:var(--green)">${dados.migrations.reduce((a, m) => a + m.criadas, 0)}</div><div class="s">${dados.migrations.reduce((a, m) => a + m.drops, 0)} removidas depois</div></div></div>
    <div class="card sp4"><div class="stat"><div class="k">última</div><div class="v" style="font-size:26px; padding-top:8px">#${dados.migrations[dados.migrations.length - 1].n}</div><div class="s">${esc(dados.migrations[dados.migrations.length - 1].arquivo)}</div></div></div>
  </div>
  <div class="mg-timeline">${itens}</div>`;
}

/* ---------- INTEGRACOES: diagrama de contexto ---------- */

/* papel funcional curto de cada serviço na seta (o card traz o completo);
   serviço novo sem verbete usa o início do "pra que serve" do snapshot */
const PAPEL_CURTO = {
  OpenRouter: 'gera as atas com IA',
  ClickSign: 'colhe as assinaturas',
  Resend: 'envia os emails',
  Fireflies: 'traz as transcrições',
};
const ENTRADA = new Set(['Fireflies']);   // seta chegando no app (webhook)

function renderIntegracoes(dados) {
  const svcs = dados.servicos;
  const esq = svcs.filter((_, i) => i % 2 === 0), dir = svcs.filter((_, i) => i % 2 === 1);
  const linhas = Math.max(esq.length, dir.length);
  const H = Math.max(200, 60 + linhas * 96);
  const W = 760, BW = 168, BH = 56, AW = 216, AH = 72;
  const ax = W / 2 - AW / 2, ay = H / 2 - AH / 2;
  const rotulos = [];
  const caixa = (s, x, y, lado) => {
    const entra = ENTRADA.has(s.nome);
    const x1 = lado < 0 ? x + BW : x, x2 = lado < 0 ? ax : ax + AW;
    const [xa, xb] = entra ? [x1, x2] : [x2, x1];   // sentido da seta
    // rótulos pintam por último (num grupo próprio) pra não sumirem atrás do app
    rotulos.push(`<text class="ctx-rotulo" data-svc="${esc(s.nome)}" x="${(x1 + x2) / 2}" y="${y + BH / 2 - 9}">${esc(PAPEL_CURTO[s.nome] || s.papel.slice(0, 32))}</text>`);
    return `
    <g class="ctx-svc" data-svc="${esc(s.nome)}" tabindex="0" role="button" aria-label="${esc(s.nome)}: ${esc(PAPEL_CURTO[s.nome] || s.papel)}">
      <path class="ctx-seta" d="M ${xa} ${y + BH / 2} H ${xb}" marker-end="url(#ctxPonta)"/>
      <rect x="${x}" y="${y}" width="${BW}" height="${BH}" rx="12"/>
      <text class="ctx-nome" x="${x + BW / 2}" y="${y + 25}">${esc(s.nome)}</text>
      <text class="ctx-sub" x="${x + BW / 2}" y="${y + 42}">${esc(s.secret || '')}</text>
    </g>`;
  };
  const boxes = [
    ...esq.map((s, i) => caixa(s, 24, 40 + i * 96, -1)),
    ...dir.map((s, i) => caixa(s, W - BW - 24, 40 + i * 96, 1)),
  ].join('');
  const cards = svcs.map(s => `
    <article class="card ctx-card sp6 lift" data-svc="${esc(s.nome)}">
      <h3>${esc(s.nome)}</h3>
      <p class="ctx-papel">${esc(s.papel)}</p>
      <div class="ctx-meta">
        ${s.onde.map(o => `<span class="chip">${esc(o)}</span>`).join('')}
      </div>
      <div class="ctx-envs">${[s.secret, ...s.relacionadas].filter(Boolean).map(v => `<code>${esc(v)}</code>`).join(' ')}</div>
    </article>`).join('');
  return `
  <div class="card ctx-capa rv">
    <div class="er-capa-head">
      <span class="k-label">quem conversa com o app · ${svcs.length} serviços externos</span>
      <span class="er-capa-hint">passe o mouse num serviço para acender o caminho dele</span>
    </div>
    <svg class="ctx-svg" viewBox="0 0 ${W} ${H}" role="group" aria-label="Diagrama de contexto: o Hospital Reuniões no centro e os serviços externos em volta">
      <defs><marker id="ctxPonta" markerWidth="9" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0 0 L9 4 L0 8 Z"/></marker></defs>
      ${boxes}
      <g class="ctx-app"><rect x="${ax}" y="${ay}" width="${AW}" height="${AH}" rx="16"/>
        <text class="ctx-app-nome" x="${W / 2}" y="${ay + 32}">Hospital Reuniões</text>
        <text class="ctx-app-sub" x="${W / 2}" y="${ay + 52}">backend FastAPI</text></g>
      <g class="ctx-rotulos">${rotulos.join('')}</g>
    </svg>
  </div>
  <div class="grid g12 rv" style="margin-top:14px">${cards}</div>`;
}

/* ---------- ESTRUTURA: árvore de pastas anotada ---------- */

const PASTAS_CHAVE = new Set(['routers/', 'services/', 'pipeline/', 'cron/', 'migrations/', 'app/', 'components/', 'hooks/']);

function renderEstrutura(dados) {
  const cards = dados.secoes.map(sec => `
  <article class="card tr-sec sp6">
    <h3>${esc(sec.titulo)}</h3>
    ${sec.local ? `<div class="tr-local">${esc(sec.local)}</div>` : ''}
    <div class="tr-arvore">
      ${sec.nos.map(no => `
      <div class="tr-no ${no.dir ? 'tr-dir' : ''} ${PASTAS_CHAVE.has(no.nome) ? 'tr-chave' : ''}" style="--n:${no.nivel}">
        <span class="tr-nome">${esc(no.nome)}</span>
        ${no.comentario ? `<span class="tr-com">${esc(no.comentario)}</span>` : ''}
      </div>`).join('')}
    </div>
  </article>`).join('');
  return `<div class="grid g12 rv">${cards}</div>
  <div class="tr-legenda rv">pastas com a bolinha coral são o coração de cada camada · as notas humanas curadas ficam no "ver fonte"</div>`;
}

/* ---------- SCHEMA: o desenho é a capa da aba ---------- */

function renderSchema(_dados, ctx) {
  const er = ctx.er;
  if (!er) return null;
  return `
  <div class="card rv sc-nota">
    O desenho grande no topo da aba <b>é</b> este snapshot: ${er.tabelas.length} tabelas e ${er.relacoes.length} relações,
    agrupadas por domínio. Passe o mouse numa tabela para ver todas as colunas; clique para fixar; use
    <span class="mono">⛶ tela cheia</span> para estudar com espaço. A ficha completa de cada tabela vive em <b>ENTIDADES</b>.
  </div>`;
}

/* ---------- FLUXOGRAMAS: explicação leiga no hover dos estados ---------- */

export function wireFluxogramas(root, dados) {
  const estados = (dados && dados.estados) || {};
  root.querySelectorAll('.diagrama-box').forEach(box => {
    const svg = box.querySelector('.st-svg');
    if (!svg) return;
    const pop = document.createElement('div');
    pop.className = 'st-pop';
    pop.hidden = true;
    box.appendChild(pop);
    svg.querySelectorAll('.st-no').forEach(g => {
      const nome = g.dataset.e;
      const txt = estados[nome];
      if (!txt) return;
      g.classList.add('st-explicado');
      g.setAttribute('tabindex', '0');
      const mostrar = () => {
        pop.innerHTML = `<b>${esc(nome)}</b>${esc(txt)}`;
        pop.hidden = false;
        const r = g.getBoundingClientRect(), b = box.getBoundingClientRect();
        let x = r.left - b.left + r.width / 2 - pop.offsetWidth / 2;
        x = Math.max(8, Math.min(x, b.width - pop.offsetWidth - 8));
        let y = r.bottom - b.top + 8;
        if (y + pop.offsetHeight > b.height - 4) y = r.top - b.top - pop.offsetHeight - 8;
        pop.style.left = `${Math.round(x)}px`;
        pop.style.top = `${Math.round(y)}px`;
      };
      const esconder = () => { pop.hidden = true; };
      g.addEventListener('mouseenter', mostrar);
      g.addEventListener('mouseleave', esconder);
      g.addEventListener('focus', mostrar);
      g.addEventListener('blur', esconder);
    });
  });
}

/* ---------- interface única ---------- */

const RENDER_AREA = {
  ROTAS: renderRotas,
  ENTIDADES: renderEntidades,
  MIGRATIONS: renderMigrations,
  INTEGRACOES: renderIntegracoes,
  ESTRUTURA: renderEstrutura,
  SCHEMA: renderSchema,
};

/* capa da área, ou null pra manter o markdown renderizado (FLUXOGRAMAS e
   qualquer doc sem dados estruturados) */
export function renderArea(doc, ctx) {
  const fn = doc && doc.dados && Object.hasOwn(RENDER_AREA, doc.name) && RENDER_AREA[doc.name];
  if (!fn) return null;
  try {
    return fn(doc.dados, ctx);
  } catch {
    return null;   // capa nunca derruba a aba: sem desenho, o markdown fica
  }
}

export function wireArea(root, doc, ctx) {
  if (!doc) return;
  if (doc.name === 'FLUXOGRAMAS') wireFluxogramas(root, doc.dados);
  if (doc.name === 'ROTAS' && doc.dados) {
    const q = root.querySelector('#rt-q');
    const lista = root.querySelector('#rt-list');
    if (q && lista) q.addEventListener('input', () => {
      ctx.aoBuscarRota && ctx.aoBuscarRota(q.value);
      lista.innerHTML = rotasListHtml(doc.dados, q.value);
    });
  }
  if (doc.name === 'INTEGRACOES') {
    const svg = root.querySelector('.ctx-svg');
    if (!svg) return;
    const ligar = (nome, on) => {
      svg.classList.toggle('ctx-hover', on);
      svg.querySelectorAll('.ctx-svc, .ctx-rotulo').forEach(g => g.classList.toggle('on', on && g.dataset.svc === nome));
      root.querySelectorAll('.ctx-card').forEach(c => c.classList.toggle('on', on && c.dataset.svc === nome));
    };
    root.querySelectorAll('.ctx-svc, .ctx-card').forEach(el => {
      el.addEventListener('mouseenter', () => ligar(el.dataset.svc, true));
      el.addEventListener('mouseleave', () => ligar(el.dataset.svc, false));
      el.addEventListener('focus', () => ligar(el.dataset.svc, true));
      el.addEventListener('blur', () => ligar(el.dataset.svc, false));
    });
  }
}
