import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Agente, Ci, Coleta, EsperaCi, Fase, Issue, Migration, Prd, SubAgente, Subida } from '../types'

// Torre das ondas: só leitura. A coleta (hooks/coletar.sh) junta o Hospital OS,
// o `claude agents`, as migrations que a subida pediu e o /api/health.
// O relógio só olha o que é local (sessões, agentes, subidas, migrations); o GitHub e o OS
// são buscados quando um evento do workflow acontece: agente que começa ou termina, sessão
// que nasce ou para, subida que fecha, migration nova, ou um gh/fechar_onda nesta sessão.

const PANE = 'ondas'
const STUDIO = 'https://studio.hospitalsaomatheus.cloud/project/default/sql/new'
const PERIODO_MS = 10_000
/** Comando desta sessão que muda o GitHub ou a produção: ao terminar, recoleta. */
const EVENTO_NO_SHELL = /fechar_onda\.py\s+--prs|gh\s+pr\s+(create|merge|ready|close)|gh\s+issue\s+(create|close|edit)|gh\s+run\s+watch|gh\s+pr\s+checks\b[^|;&]*--watch/
const APLICADA_VISIVEL_MS = 60 * 60 * 1000

const coleta = atom({ plugin: 'hr-ondas', key: 'coleta' } as const, null)
const erro = atom({ plugin: 'hr-ondas', key: 'erro' } as const, null)
const todos = atom({ plugin: 'hr-ondas', key: 'todos' } as const, false)
const esperaCi = atom({ plugin: 'hr-ondas', key: 'esperaCi' } as const, null)

const COR: Record<Fase, string> = {
  triagem: 'inactive',
  fila: 'inactive',
  bloqueada: 'subtle',
  em_andamento: 'suggestion',
  pr_aberto: 'permission',
  mergeada: 'merged',
  em_producao: 'success',
  humana: 'warning',
  encerrada_sem_pr: 'subtle',
}

const MARCA: Record<Fase, string> = {
  triagem: '?',
  fila: '·',
  bloqueada: '×',
  em_andamento: '▸',
  pr_aberto: '◆',
  mergeada: '●',
  em_producao: '✓',
  humana: '!',
  encerrada_sem_pr: '✓',
}

const NOME: Record<Fase, string> = {
  triagem: 'triagem',
  fila: 'fila',
  bloqueada: 'bloqueada',
  em_andamento: 'em andamento',
  pr_aberto: 'PR aberto',
  mergeada: 'mergeada',
  em_producao: 'em produção',
  humana: 'humana',
  encerrada_sem_pr: 'encerrada sem PR',
}

const ATIVAS: Fase[] = ['em_andamento', 'pr_aberto', 'mergeada', 'humana']

export const curto = (texto: string, max: number) =>
  texto.length > max ? `${texto.slice(0, max - 1)}…` : texto

export const minutos = (ms: number) => {
  const m = Math.max(0, Math.round(ms / 60_000))
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
}

/**
 * Migrations que o humano declarou aplicadas numa fala ("apliquei a migration 118",
 * "apliquei as migrations 117 e 118"): só o passado "apliquei" seguido de "migration"
 * e de números de três dígitos; nada de futuro, pergunta ou negativa.
 */
export const declaradasAplicadas = (texto: string): number[] => {
  const m = /(?<!n[ãa]o\s)(?<!n[ãa]o\s\w+\s)\bapliquei\s+(?:j[áa]\s+)?(?:a|as|essa|essas|aquela|aquelas)?\s*migrations?\s+((?:\d{3}(?:\s*[,e]\s*)?)+)/i.exec(texto)
  if (!m) return []
  return [...new Set((m[1]!.match(/\d{3}/g) ?? []).map(Number))].sort((a, b) => a - b)
}

/** Migration que a subida pediu e o /api/health ainda não devolveu, uma por número. */
export const pendentes = (c: Coleta): Migration[] => {
  const porNumero = new Map<number, Migration>()
  for (const m of c.migrations) {
    const esperando = c.aplicada === null ? c.em - m.mtime < 24 * 3600_000 : m.numero > c.aplicada
    const atual = porNumero.get(m.numero)
    if (esperando && (!atual || atual.mtime < m.mtime)) porNumero.set(m.numero, m)
  }
  return [...porNumero.values()].sort((a, b) => a.numero - b.numero)
}

/** Migration que o health já devolve e a subida pediu há menos de uma hora. */
export const aplicadasRecentes = (c: Coleta): Migration[] =>
  c.aplicada === null
    ? []
    : c.migrations
        .filter(m => m.numero <= c.aplicada! && c.em - m.mtime < APLICADA_VISIVEL_MS)
        .sort((a, b) => a.numero - b.numero)

/** Grupo das issues sem PRD pai em andamento: um PRD de número 0, desenhado como os outros. */
export const SEM_PRD = 0
export const comSemPrd = (os: Coleta['os']): Coleta['os'] =>
  os?.soltas?.length
    ? { ...os, prds: [...os.prds, { n: SEM_PRD, titulo: 'issues sem PRD pai em andamento', ondas: [], issues: os.soltas }] }
    : os

export const sessoesDoPrd = (c: Coleta, prd: number): Agente[] =>
  c.agentes.filter(a => prdDaSessao(c, a.nome) === prd)

/** PRDs que entram no painel: com sessão de onda viva ou com fatia andando. */
export const prdsVisiveis = (c: Coleta, mostrarTodos: boolean): Prd[] => {
  const prds = c.os?.prds ?? []
  const comSessao = (p: Prd) => sessoesDoPrd(c, p.n).length > 0
  const andando = (p: Prd) => p.issues.some(i => ATIVAS.includes(i.fase))
  return prds
    .filter(p => mostrarTodos || comSessao(p) || andando(p))
    .sort((a, b) => Number(comSessao(b)) - Number(comSessao(a)) || b.n - a.n)
}

export const detalhe = (i: Issue): string => {
  const partes: string[] = [NOME[i.fase]]
  if (i.fase === 'pr_aberto') {
    if (i.ci) partes.push(`CI ${i.ci.replace('_', ' ')}`)
    if (i.veredito) partes.push(i.veredito.toLowerCase())
    if (i.conflito) partes.push('conflito')
  }
  if (i.versao) partes.push(i.versao)
  if (i.por.length) partes.push(`espera ${i.por.map(n => `#${n}`).join(' ')}`)
  return partes.join(' · ')
}

const corDaIssue = (i: Issue) =>
  i.fase === 'pr_aberto' && (i.ci === 'vermelho' || i.conflito) ? 'error' : COR[i.fase]

// Sub-agentes: quem trabalha em cada fatia e em que etapa ela está
const JANELA = 1_000_000
const PARADO_MS = 10 * 60_000

type EstadoAgente = 'trabalhando' | 'terminou' | 'parado'
const COR_AGENTE: Record<EstadoAgente, string> = { trabalhando: 'suggestion', terminou: 'success', parado: 'warning' }
const MARCA_AGENTE: Record<EstadoAgente, string> = { trabalhando: '●', terminou: '✓', parado: '◌' }

/** Sem end_turn e com escrita nos últimos 10 min: trabalhando; sem escrita há mais: parado. */
export const estadoDoAgente = (a: SubAgente, agora: number): EstadoAgente =>
  a.terminou ? 'terminou' : agora - a.fim < PARADO_MS ? 'trabalhando' : 'parado'

export const nomeModelo = (m: string | null) => {
  const r = /claude-([a-z]+)-(\d+)-(\d+)/.exec(m ?? '')
  return r ? `${r[1]![0]!.toUpperCase()}${r[1]!.slice(1)} ${r[2]}.${r[3]}` : (m ?? '')
}

/** Tetos em minutos (amarelo, vermelho): p75 e p90 do histórico desta máquina em 13/10/2026. */
export const TETOS: Record<string, [number, number]> = {
  'hr-implementador': [30, 35],
  'hr-revisor': [5, 10],
  'hr-corretor': [10, 15],
  CI: [8, 12],
  subida: [10, 25],
}

export const corDaDuracao = (etapa: string, ms: number): 'warning' | 'error' | undefined => {
  const teto = TETOS[etapa]
  if (!teto) return undefined
  const min = ms / 60_000
  return min >= teto[1] ? 'error' : min >= teto[0] ? 'warning' : undefined
}

export const duracao = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60))
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm.padStart(2, '0')}:${ss}` : `${mm}:${ss}`
}

/** PRD dono da issue ou do PR que o sub-agente cita. */
const prdDoAlvo = (c: Coleta, a: SubAgente): number | undefined =>
  (c.os?.prds ?? []).find(p => alvo(a, p) !== null)?.n

/** PRD da sessão: o do alvo do sub-agente mais recente dela; sem alvo, o da passagem (coletar.sh); passagem sem PRD, o da fila fixa. */
export const prdDaSessao = (c: Coleta, nome: string): number | undefined => {
  const dela = (c.subAgentes ?? []).filter(a => a.sessao === nome).sort((x, y) => y.inicio - x.inicio)
  for (const a of dela) {
    const n = prdDoAlvo(c, a)
    if (n !== undefined) return n
  }
  const fila = c.passagens?.[linhagem(nome)]?.ondas[/-onda(\d+)$/.exec(nome)?.[1] ?? ''] ?? []
  return c.prdSessoes[nome] ?? (c.os?.prds ?? []).find(p => p.issues.some(i => fila.includes(i.n)))?.n
}

/** Sub-agentes do PRD: pelo alvo; sem alvo em nenhum PRD, pelo PRD da sessão. */
export const agentesDoPrd = (c: Coleta, prd: Prd): SubAgente[] =>
  (c.subAgentes ?? [])
    .filter(a => (prdDoAlvo(c, a) ?? prdDaSessao(c, a.sessao)) === prd.n)
    .sort((x, y) => x.inicio - y.inicio)

/** A fatia de um sub-agente pela descrição: "PR 1166" vai à issue do PR, "#1139" à issue. */
export const alvo = (a: SubAgente, prd: Prd): number | null => {
  const pr = /PR\s*#?(\d+)/i.exec(a.descricao)
  if (pr) return prd.issues.find(i => i.pr === Number(pr[1]))?.n ?? null
  const n = Number(/#(\d+)/.exec(a.descricao)?.[1])
  if (prd.issues.some(i => i.n === n)) return n
  // "Rebase conflito #1178": o orquestrador cita o PR sem a palavra PR
  return prd.issues.find(i => i.pr === n)?.n ?? null
}

/** A fatia do sub-agente para a tela: "#1142 (PR #1178)"; sem fatia, a descrição que ele recebeu. */
export const rotuloDoAlvo = (a: SubAgente, prd: Prd): string => {
  const n = alvo(a, prd)
  if (n === null) return a.descricao
  const pr = prd.issues.find(i => i.n === n)?.pr
  return pr ? `#${n} (PR #${pr})` : `#${n}`
}

/** No que a sessão está: os sub-agentes trabalhando; sem nenhum, o último que acabou. */
export const focoDaSessao = (nome: string, ags: SubAgente[], agora: number): SubAgente[] => {
  const dela = ags.filter(a => a.sessao === nome)
  const vivos = dela.filter(a => estadoDoAgente(a, agora) === 'trabalhando')
  if (vivos.length) return vivos
  const ultimo = dela.sort((x, y) => y.fim - x.fim)[0]
  return ultimo ? [ultimo] : []
}

/** "onda-gestao-onda4" vira "gestao-onda4" ao lado do sub-agente. */
export const nomeCurtoDaSessao = (nome: string) => nome.replace(/^onda-/, '')

type EstadoEtapa = 'feita' | 'agora' | 'falhou' | 'falta'
const COR_ETAPA: Record<EstadoEtapa, string> = { feita: 'success', agora: 'suggestion', falhou: 'error', falta: 'inactive' }
const MARCA_ETAPA: Record<EstadoEtapa, string> = { feita: ' ✓', agora: ' ●', falhou: ' ✗', falta: '' }

export type Etapa = { nome: string; estado: EstadoEtapa; ms?: number; cor?: 'warning' | 'error' }

/** A subida que levou o PR da fatia: a mais recente que o cita. */
export const subidaDoPr = (c: Coleta, pr: number | null): Subida | undefined =>
  pr === null ? undefined : (c.subidas ?? []).filter(s => s.prs.includes(pr)).sort((a, b) => b.inicio - a.inicio)[0]

/** Fatias prontas do PRD: no ar ou fechadas (o passo humano fecha sem PR). */
export const prontasDoPrd = (prd: Prd) => prd.issues.filter(i => i.fase === 'em_producao' || i.estado === 'CLOSED').length

/** Esteira da fatia: implementar → CI → revisar → (corrigir) → subida → no ar, com o tempo de cada etapa. */
export const etapas = (
  i: Issue,
  ags: SubAgente[],
  agora: number,
  extra: { ci?: Ci; subida?: Subida; migrationPendente?: boolean } = {},
) => {
  // passo humano fechado (ou issue encerrada sem código): não houve esteira para mostrar
  if (i.fase === 'encerrada_sem_pr') return [{ nome: 'fechada sem PR', estado: 'feita' as EstadoEtapa }]
  const de = (tipo: string) => ags.filter(a => a.tipo === tipo)
  const estado = (tipo: string, feita: boolean): EstadoEtapa => {
    const lista = de(tipo)
    if (lista.some(a => estadoDoAgente(a, agora) === 'trabalhando')) return 'agora'
    return feita || (lista.length > 0 && lista.every(a => a.terminou)) ? 'feita' : 'falta'
  }
  // soma do tempo dos sub-agentes do tipo; o que trabalha conta até agora
  const gasto = (tipo: string) => {
    const lista = de(tipo)
    if (!lista.length) return undefined
    return lista.reduce((n, a) => n + ((estadoDoAgente(a, agora) === 'trabalhando' ? agora : a.fim) - a.inicio), 0)
  }
  const com = (nome: string, estado: EstadoEtapa, ms: number | undefined, teto = nome, pintar = true): Etapa =>
    ms === undefined || estado === 'falta' ? { nome, estado } : { nome, estado, ms, cor: pintar ? corDaDuracao(teto, ms) : undefined }
  const depoisDoPr = ['pr_aberto', 'mergeada', 'em_producao'].includes(i.fase)
  const subiu = ['mergeada', 'em_producao'].includes(i.fase)
  const ciMs = extra.ci ? (extra.ci.fim ?? agora) - extra.ci.inicio : undefined
  const lista: Etapa[] = [
    com('implementar', estado('hr-implementador', depoisDoPr), gasto('hr-implementador'), 'hr-implementador'),
    com('CI', subiu || i.ci === 'verde' ? 'feita' : i.ci === 'vermelho' ? 'falhou' : i.pr ? 'agora' : 'falta', ciMs),
    com('revisar', estado('hr-revisor', subiu || !!i.veredito), gasto('hr-revisor'), 'hr-revisor'),
  ]
  if (de('hr-corretor').length) lista.push(com('corrigir', estado('hr-corretor', subiu), gasto('hr-corretor'), 'hr-corretor'))
  const s = extra.subida
  const subidaMs = s ? (s.fim ?? agora) - s.inicio : undefined
  lista.push(
    com(
      'subida',
      i.fase === 'em_producao' ? 'feita' : i.fase === 'mergeada' || (s && s.fim === null) ? 'agora' : 'falta',
      subidaMs,
      'subida',
      !extra.migrationPendente, // esperando o Studio, o tempo é do humano: sem cor
    ),
  )
  lista.push({ nome: 'no ar', estado: i.fase === 'em_producao' ? 'feita' : 'falta' })
  return lista
}

/** O que a sessão está fazendo agora: a subida em curso, senão o Bash em primeiro plano. */
export const atividadeDaSessao = (s: Agente, c: Coleta): { texto: string; inicio: number } | null => {
  const subida = (c.subidas ?? []).find(x => x.sessao === s.nome && x.fim === null)
  if (subida) return { texto: `subida ${subida.prs.map(p => `#${p}`).join(' ')}`, inicio: subida.inicio }
  if (!s.shell) return null
  return { texto: rotuloDoShell(s.shell.descricao, s.shell.comando), inicio: s.shell.inicio }
}

/** Padrão conhecido vira rótulo fixo; o resto é a description que o orquestrador escreveu. */
export const rotuloDoShell = (descricao: string, comando: string) => {
  const subida = /python[\d.]*\s+(?:-\S+\s+)*\S*fechar_onda\.py\s+--prs\s+([\d\s]+)/.exec(comando)
  if (subida && !/--dry-run/.test(comando)) return `subida ${subida[1]!.trim().split(/\s+/).map(p => `#${p}`).join(' ')}`
  const ci = /gh\s+(?:pr\s+checks\s+(\d+)[^|;&]*--watch|run\s+watch)/.exec(comando)
  if (ci) return ci[1] ? `esperando o CI do PR #${ci[1]}` : 'esperando o CI'
  return descricao || curto(comando.replace(/^cd [^;]*;\s*/, ''), 60)
}

/** Do primeiro sub-agente da onda ao último fim, ou até agora. */
export const duracaoDaOnda = (issues: Issue[], ags: SubAgente[], prd: Prd, agora: number): number | null => {
  const da = ags.filter(a => issues.some(i => i.n === alvo(a, prd)))
  if (!da.length) return null
  const inicio = Math.min(...da.map(a => a.inicio))
  const fim = da.some(a => estadoDoAgente(a, agora) === 'trabalhando') ? agora : Math.max(...da.map(a => a.fim))
  return fim - inicio
}

type SituacaoOnda = 'feita' | 'andando' | 'fila' | 'parada'
const COR_ONDA: Record<SituacaoOnda, string> = { feita: 'success', andando: 'suggestion', fila: 'permission', parada: 'inactive' }
const NOME_ONDA: Record<SituacaoOnda, string> = { feita: 'no ar', andando: 'andando', fila: 'na fila', parada: 'parada' }

export const situacaoDaOnda = (issues: Issue[], ags: SubAgente[], prd: Prd, agora: number): SituacaoOnda => {
  if (issues.every(i => i.fase === 'em_producao' || i.estado === 'CLOSED')) return 'feita'
  const comAgente = ags.some(a => issues.some(i => i.n === alvo(a, prd)) && estadoDoAgente(a, agora) === 'trabalhando')
  if (comAgente || issues.some(i => ATIVAS.includes(i.fase))) return 'andando'
  return issues.some(i => i.fase === 'fila') ? 'fila' : 'parada'
}

/** Onda que não anda cabe em uma ou duas linhas: as fatias e o que ela espera de fora (quem está na mão do humano, dito). */
export const resumoDaOnda = (issues: Issue[], onda: number[], porN?: Map<number, Issue>) => {
  const linhas = [{ texto: issues.map(i => `${MARCA[i.fase]} #${i.n}`).join('  '), cor: 'inactive' }]
  const fora = [...new Set(issues.flatMap(i => i.por))].filter(n => !onda.includes(n)).sort((a, b) => a - b)
  const nome = (n: number) => (porN?.get(n)?.fase === 'humana' ? `#${n} (humana)` : `#${n}`)
  if (fora.length) linhas.push({ texto: `espera ${fora.map(nome).join(' ')}`, cor: 'subtle' })
  return linhas
}

/** Linhagem da sessão: "onda-gestao-onda4" é a onda 4 da linhagem "onda-gestao". */
export const linhagem = (nome: string) => nome.replace(/-onda\d+$/, '')

export type OndaDesenhada = {
  numero: number
  issues: number[]
  /** A sessão viva desta onda (`<linhagem>-onda<numero>`), se houver. */
  sessao?: Agente
  /** Pela passagem: viva (sessão rodando), escrita (passagem existe, sessão não roda) ou nao; null quando a onda vem do OS. */
  passagem: 'viva' | 'escrita' | 'nao' | null
}

/** Ondas do PRD na numeração do terminal: a fila-alvo da passagem da linhagem das suas sessões. Sem passagem, as colunas do OS. */
export const ondasDoPrd = (c: Coleta, prd: Prd): OndaDesenhada[] => {
  const nos = new Set(prd.issues.map(i => i.n))
  for (const s of sessoesDoPrd(c, prd.n)) {
    const l = linhagem(s.nome)
    const p = c.passagens?.[l]
    if (!p) continue
    const ondas = Object.entries(p.ondas)
      .map(([k, v]) => ({ numero: Number(k), issues: v.filter(n => nos.has(n)) }))
      .filter(o => o.issues.length)
      .sort((a, b) => a.numero - b.numero)
    if (!ondas.length) continue
    return ondas.map(o => {
      const sessao = c.agentes.find(a => a.nome === `${l}-onda${o.numero}`)
      return { ...o, sessao, passagem: sessao ? 'viva' : p.escritas.includes(o.numero) ? 'escrita' : 'nao' }
    })
  }
  return prd.ondas.map((issues, k) => ({ numero: k + 1, issues, passagem: null }))
}

/** O que muda num evento do workflow, lido só da parte local da coleta. */
export const assinatura = (c: Pick<Coleta, 'agentes' | 'subAgentes' | 'subidas' | 'migrations'>) =>
  JSON.stringify([
    c.agentes.map(a => `${a.nome}:${a.status}`),
    (c.subAgentes ?? []).map(a => `${a.id}:${a.terminou}`),
    (c.subidas ?? []).map(s => `${s.prs.join(',')}:${s.fim !== null}`),
    c.migrations.map(m => `${m.sessao}/${m.arquivo}`),
  ])

let rodando = false
let frescoPendente = false
let ultimaAssinatura: string | null = null
const sessoesVistas = new Set<string>()
const migrationsAvisadas = new Set<number>()

/** Grava a declaração no registro (~/.claude/hr-ondas/aplicadas) e recoleta. */
async function registrarAplicadas($: EngineInterface, numeros: number[]) {
  const r = await $.process.run(
    ['/bin/bash', `${$.plugin.root}/hooks/coletar.sh`, `--registrar=${numeros.join(',')}`],
    { timeoutMs: 10_000 },
  )
  if (r.exitCode !== 0) throw new Error(r.stderr.slice(0, 200) || `saída ${r.exitCode}`)
  $.ui.toast(`Migration ${numeros.join(', ')} registrada como aplicada`)
  await coletar($, true)
}

async function coletar($: EngineInterface, fresco = false) {
  if (rodando) {
    frescoPendente ||= fresco
    return
  }
  rodando = true
  try {
    const args = [...(fresco ? ['--fresco'] : []), ...((await read($, todos)) ? ['--todos'] : [])]
    const r = await $.process.run(['/bin/bash', `${$.plugin.root}/hooks/coletar.sh`, ...args], {
      timeoutMs: 120_000,
    })
    if (r.exitCode !== 0) throw new Error(r.stderr.slice(0, 200) || `saída ${r.exitCode}`)
    const agora = await $.clock.now()
    const bruto = JSON.parse(r.stdout) as Omit<Coleta, 'em'>
    const anterior = await read($, coleta)
    // OS sem resposta: fica o último retrato bom; o resto (sessões, agentes, migrations) é fresco
    const c: Coleta = {
      ...bruto,
      os: comSemPrd(bruto.os) ?? anterior?.os ?? null,
      osEm: bruto.os ? (bruto.osEm ?? agora) : (anterior?.osEm ?? null),
      em: agora,
    }
    const a = assinatura(c)
    if (ultimaAssinatura !== null && a !== ultimaAssinatura) frescoPendente = true
    ultimaAssinatura = a
    await update($, coleta, () => c)
    await update($, erro, () => (c.os ? null : 'Hospital OS fora do ar em 127.0.0.1:8799'))

    const novasSessoes = c.agentes.filter(a => !sessoesVistas.has(a.nome))
    novasSessoes.forEach(a => sessoesVistas.add(a.nome))
    const novasMigrations = pendentes(c).filter(m => !migrationsAvisadas.has(m.numero))
    novasMigrations.forEach(m => migrationsAvisadas.add(m.numero))

    for (const m of novasMigrations) {
      $.ui.toast(`Migration ${m.numero} esperando o Studio (${m.sessao})`)
    }
    // a primeira coleta só abre se já houver onda rodando; depois, a cada novidade
    if (novasSessoes.length > 0 || novasMigrations.length > 0) {
      void $.ui.open({ id: PANE, title: 'Ondas', columns: 78 })
    }

    const p = pendentes(c)
    const vivas = c.agentes.filter(a => a.status === 'busy').length
    $.ui.status(
      p.length
        ? `ondas: migration ${p.map(m => m.numero).join(', ')} esperando o Studio`
        : vivas
          ? `ondas: ${vivas} sessão(ões) rodando`
          : undefined,
    )
  } catch (falha) {
    await update($, erro, () => `coleta falhou: ${String(falha).slice(0, 160)}`)
  } finally {
    rodando = false
  }
  if (frescoPendente) {
    frescoPendente = false
    await coletar($, true)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'ondas',
      description: 'Torre das ondas: PRD, onda, fase de cada issue e migrations (`/ondas todos` mostra todos os PRDs)',
    })
    // a torre é o painel que nasce com a sessão interativa do Hospital
    if (e.isInteractive) void $.ui.open({ id: PANE, title: 'Ondas', columns: 78 })
    void coletar($)
    $.clock.every(PERIODO_MS, () => coletar($))
    return next(e)
  })

  on('command.run', { command: 'ondas' }, async ($, e) => {
    const arg = e.args.trim()
    // /ondas aplicada 118[,119]: o humano aplicou no Studio e declara
    const aplicada = /^aplicadas?\s+([\d,\s]+)$/.exec(arg)
    if (aplicada) {
      const numeros = (aplicada[1]!.match(/\d+/g) ?? []).map(Number)
      await registrarAplicadas($, numeros)
      return { text: `Migration ${numeros.join(', ')} registrada como aplicada.` }
    }
    if (arg === 'todos' || arg === 'ativos') await update($, todos, () => arg === 'todos')
    await $.ui.open({ id: PANE, title: 'Ondas', columns: 78 })
    await coletar($, true)
    return { text: `Painel das ondas atualizado${arg === 'todos' ? ', com todos os PRDs' : ''}.` }
  })

  // "apliquei a migration 118" em qualquer sessão: registra e o painel para de cobrar
  on('prompt.submit', async ($, e, next) => {
    const numeros = declaradasAplicadas(e.text)
    if (!numeros.length) return next(e)
    let nota: string
    try {
      await registrarAplicadas($, numeros)
      nota = `hr-ondas: migration ${numeros.join(', ')} registrada como aplicada em ~/.claude/hr-ondas/aplicadas; o painel das ondas já não a cobra.`
    } catch (falha) {
      nota = `hr-ondas: não consegui registrar a migration ${numeros.join(', ')} como aplicada: ${String(falha).slice(0, 160)}`
    }
    return next({ ...e, context: [...(e.context ?? []), nota] })
  })

  // CI em espera na própria sessão: o --watch segura a chamada até o fim.
  // Todo comando que muda o GitHub ou a produção recoleta ao terminar.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const cmd = e.command
    const assistindo = /gh\s+run\s+watch|gh\s+pr\s+checks\b[^|;&]*--watch/.test(cmd)
    if (!assistindo) {
      if (!EVENTO_NO_SHELL.test(cmd)) return next(e)
      try {
        return await next(e)
      } finally {
        void coletar($, true)
      }
    }
    const pr = Number(/gh\s+pr\s+checks\s+(\d+)/.exec(cmd)?.[1]) || null
    const repo = (await read($, coleta))?.os?.repo ?? 'pedrorezendefig/hospital-reunioes'
    const url = pr ? `https://github.com/${repo}/pull/${pr}/checks` : `https://github.com/${repo}/actions`
    await update($, esperaCi, () => ({ pr, url }) satisfies EsperaCi)
    try {
      return await next(e)
    } finally {
      await update($, esperaCi, () => null)
      void coletar($, true)
    }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const c = await read($, coleta)
    const ci = await read($, esperaCi)
    const p = c ? pendentes(c) : []
    if (!p.length && !ci) return next(e)
    const { Box, Text, Link } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {p.map(m => (
          <Text key={`m${m.numero}`} color="warning">
            ⏳ migration {m.numero} esperando o Studio ({m.linhas} linhas, {m.sessao}, há{' '}
            {minutos(c!.em - m.mtime)}) · <Link href={`vscode://file${m.caminho}:1`} label="abrir no VS Code" /> ·{' '}
            <Link href={STUDIO} label="Studio SQL" />
          </Text>
        ))}
        {ci && (
          <Text key="ci" color="suggestion">
            ◷ esperando o CI{ci.pr ? ` do PR #${ci.pr}` : ''} · <Link href={ci.url} label="ver checks" />
          </Text>
        )}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link } = $.ui.resolve(e)
    const c = await read($, coleta)
    const falha = await read($, erro)
    const mostrarTodos = await read($, todos)
    const largura = Math.max(30, (e.props.bodyColumns ?? (e.viewport?.columns ?? 100) - 4) - 4)

    if (!c) {
      return (
        <Box flexDirection="column">
          <Text dimColor>{falha ?? 'Coletando (o Hospital OS pode levar uns 20 s)…'}</Text>
        </Box>
      )
    }

    const p = pendentes(c)
    const recentes = aplicadasRecentes(c)
    const prds = prdsVisiveis(c, mostrarTodos)
    const repo = c.os?.repo ?? 'pedrorezendefig/hospital-reunioes'
    const linkIssue = (n: number) => <Link href={`https://github.com/${repo}/issues/${n}`} label={`#${n}`} />

    const linhaAgente = (a: SubAgente, alvoDele?: string) => {
      const estado = estadoDoAgente(a, c.em)
      const pct = Math.round((a.ctx / JANELA) * 100)
      const cheio = Math.min(10, Math.round(pct / 10))
      return (
        <Text key={`a${a.id}`} wrap="truncate-end">
          {'    '}
          <Text color={COR_AGENTE[estado]}>{MARCA_AGENTE[estado]} </Text>
          <Text bold>{a.tipo}</Text>
          {alvoDele ? <Text> {alvoDele}</Text> : null}
          <Text dimColor>
            {' '}
            {[alvoDele ? null : nomeCurtoDaSessao(a.sessao), nomeModelo(a.modelo), a.esforco].filter(Boolean).join(' · ')}{' '}
          </Text>
          <Text color={COR_AGENTE[estado]}>{'▰'.repeat(cheio)}</Text>
          <Text dimColor>
            {'▱'.repeat(10 - cheio)} ctx {pct}% · {Math.round(a.ctx / 1000)}k · {duracao((estado === 'trabalhando' ? c.em : a.fim) - a.inicio)}
          </Text>
        </Text>
      )
    }

    const passos = (i: Issue, ags: SubAgente[], sessao: string | undefined) => {
      const extra = {
        ci: i.pr ? c.ci?.[String(i.pr)] : undefined,
        subida: subidaDoPr(c, i.pr),
        migrationPendente: p.some(m => m.sessao === sessao),
      }
      return (
        <Text key={`s${i.n}`} wrap="truncate-end">
          {'    '}
          {etapas(i, ags, c.em, extra).map((s, k) => (
            <Text key={`e${k}`}>
              {k > 0 ? <Text dimColor> → </Text> : null}
              <Text color={COR_ETAPA[s.estado]}>
                {s.nome}
                {MARCA_ETAPA[s.estado]}
              </Text>
              {s.ms !== undefined ? (
                <Text color={s.cor} dimColor={!s.cor}>
                  {' '}
                  {minutos(s.ms)}
                </Text>
              ) : null}
            </Text>
          ))}
        </Text>
      )
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>
          GitHub há {minutos((await $.clock.now()) - (c.remotoEm ?? c.em))} ·{' '}
          {mostrarTodos ? 'todos os PRDs (/ondas ativos)' : 'PRDs ativos (/ondas todos)'}
          {c.osEm != null && c.osEm < (c.remotoEm ?? c.em) ? (
            <Text color="warning"> · Hospital OS sem resposta, PRDs de há {minutos(c.em - c.osEm)}</Text>
          ) : null}
        </Text>
        {falha && <Text color="error">{falha}</Text>}

        {(p.length > 0 || recentes.length > 0) && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Migrations · no ar: {c.aplicada ?? '?'}</Text>
            {p.map((m, k) => (
              <Text key={`p${m.numero}`} color="warning" wrap="truncate-end">
                {'  '}⏳ {m.numero} {k === 0 ? 'cole no Studio' : `depois da ${p[k - 1]?.numero}`} ·{' '}
                <Link href={`vscode://file${m.caminho}:1`} label="VS Code" /> · <Link href={STUDIO} label="Studio" /> ·{' '}
                {m.linhas} linhas · {m.sessao} · há {minutos(c.em - m.mtime)}
              </Text>
            ))}
            {recentes.map(m => (
              <Text key={`a${m.numero}${m.sessao}`} color="success">
                {'  '}✓ {m.numero} aplicada ({m.sessao})
              </Text>
            ))}
          </Box>
        )}

        {prds.length === 0 && (
          <Text dimColor>Nenhum PRD com onda rodando ou fatia andando. /ondas todos mostra tudo.</Text>
        )}

        {prds.map(prd => {
          const sessoes = sessoesDoPrd(c, prd.n)
          const ags = agentesDoPrd(c, prd)
          const ondas = ondasDoPrd(c, prd)
          const emOnda = new Set(ondas.flatMap(o => o.issues))
          const porN = new Map(prd.issues.map(i => [i.n, i]))
          const fora = prd.issues.filter(i => !emOnda.has(i.n))
          const entregues = fora.filter(i => i.fase === 'em_producao' || i.estado === 'CLOSED')
          const soltas = fora.filter(i => !entregues.includes(i))
          const feitas = prontasDoPrd(prd)
          const semAlvo = ags.filter(a => alvo(a, prd) === null)

          return (
            <Box key={`prd${prd.n}`} flexDirection="column" marginTop={1}>
              <Text wrap="truncate-end">
                <Text bold>
                  {prd.n === SEM_PRD ? 'Sem PRD' : <Link href={`https://github.com/${repo}/issues/${prd.n}`} label={`PRD #${prd.n}`} />}
                </Text>{' '}
                <Text dimColor>
                  {feitas}/{prd.issues.length} prontas
                </Text>
              </Text>
              <Text dimColor wrap="truncate-end">
                {curto(prd.titulo.replace(/^PRD: /, ''), largura)}
              </Text>
              {sessoes.map(s => {
                const daSessao = ags.filter(a => a.sessao === s.nome)
                const vivos = daSessao.filter(a => estadoDoAgente(a, c.em) === 'trabalhando').length
                const atividade = atividadeDaSessao(s, c)
                const corAtividade = atividade?.texto.startsWith('subida') ? corDaDuracao('subida', c.em - atividade.inicio) : undefined
                return (
                  <Box key={s.nome} flexDirection="column">
                    <Text wrap="truncate-end">
                      <Text color={s.status === 'busy' ? 'suggestion' : 'inactive'}>
                        {s.status === 'busy' ? '●' : '○'} {s.nome}
                      </Text>
                      <Text dimColor>
                        {' '}
                        · {duracao(c.em - s.inicio)} · {vivos} trabalhando · {daSessao.length - vivos} terminado(s)
                      </Text>
                    </Text>
                    {atividade && (
                      <Text wrap="truncate-end">
                        {'    '}
                        <Text color="suggestion">⚙ </Text>
                        <Text>{curto(atividade.texto, largura - 14)}</Text>
                        <Text color={corAtividade} dimColor={!corAtividade}>
                          {' '}
                          · {duracao(c.em - atividade.inicio)}
                        </Text>
                      </Text>
                    )}
                    {s.fala && (
                      <Text dimColor wrap="truncate-end">
                        {'    '}💬 {curto(s.fala.texto.split('\n')[0] ?? '', largura - 22)} · há {minutos(c.em - s.fala.em)}
                      </Text>
                    )}
                    {focoDaSessao(s.nome, ags, c.em).map(a =>
                      estadoDoAgente(a, c.em) === 'trabalhando' ? (
                        linhaAgente(a, rotuloDoAlvo(a, prd))
                      ) : (
                        <Text key={`u${a.id}`} dimColor wrap="truncate-end">
                          {'    '}○ último: {a.tipo} {rotuloDoAlvo(a, prd)} · {estadoDoAgente(a, c.em) === 'terminou' ? 'terminou' : 'parado'} há{' '}
                          {minutos(c.em - a.fim)}
                        </Text>
                      ),
                    )}
                  </Box>
                )
              })}

              {ondas.map((o, k) => {
                const issues = o.issues.map(n => porN.get(n)).filter((i): i is Issue => !!i)
                const situacao = situacaoDaOnda(issues, ags, prd, c.em)
                const tempoDaOnda = duracaoDaOnda(issues, ags, prd, c.em)
                const passagem =
                  situacao === 'feita' || o.sessao ? '' : o.passagem === 'nao' ? ' · passagem: ainda não' : o.passagem === 'escrita' ? ' · passagem escrita' : ''
                return (
                  <Box key={`o${o.numero}`} flexDirection="column">
                    {k > 0 && <Text color={COR_ONDA[situacao]}>{'      ▼'}</Text>}
                    <Box flexDirection="column" borderStyle="round" borderColor={COR_ONDA[situacao]} paddingX={1}>
                      <Text bold color={COR_ONDA[situacao]} wrap="truncate-end">
                        Onda {o.numero}{' '}
                        {o.sessao ? <Text color="suggestion">· {o.sessao.nome} </Text> : null}
                        <Text dimColor>
                          · {NOME_ONDA[situacao]}
                          {tempoDaOnda !== null ? ` · ${minutos(tempoDaOnda)}` : ''}
                          {passagem}
                        </Text>
                      </Text>
                      {situacao === 'andando'
                        ? issues.map(i => {
                            const dela = ags.filter(a => alvo(a, prd) === i.n)
                            return (
                              <Box key={`i${i.n}`} flexDirection="column">
                                <Text wrap="truncate-end">
                                  <Text color={corDaIssue(i)}>{MARCA[i.fase]} </Text>
                                  {linkIssue(i.n)}
                                  {i.pr ? (
                                    <Text>
                                      {' '}
                                      <Link href={`https://github.com/${repo}/pull/${i.pr}`} label={`PR #${i.pr}`} />
                                    </Text>
                                  ) : null}
                                  <Text dimColor> {curto(i.titulo.replace(/^Contas médicas: /, ''), largura)}</Text>
                                </Text>
                                {i.fase === 'bloqueada' || i.fase === 'fila' ? (
                                  <Text dimColor wrap="truncate-end">
                                    {'    '}
                                    {detalhe(i)}
                                  </Text>
                                ) : (
                                  passos(i, dela, sessoes.find(s => dela.some(a => a.sessao === s.nome))?.nome)
                                )}
                                {dela.map(a => linhaAgente(a))}
                              </Box>
                            )
                          })
                        : resumoDaOnda(issues, o.issues, porN).map((r, j) => (
                            <Text key={`r${j}`} color={r.cor} wrap="wrap">
                              {r.texto}
                            </Text>
                          ))}
                    </Box>
                  </Box>
                )
              })}

              {soltas.map(i => (
                <Text key={`l${i.n}`} wrap="truncate-end">
                  <Text color={corDaIssue(i)}>{MARCA[i.fase]} </Text>
                  {linkIssue(i.n)} <Text color={corDaIssue(i)}>{detalhe(i)}</Text>
                </Text>
              ))}
              {entregues.length > 0 && (
                <Text color="success" wrap="truncate-end">
                  ✓ no ar: {entregues.map(i => `#${i.n}`).join(' ')}
                </Text>
              )}
              {semAlvo.length > 0 && (
                <Box flexDirection="column" marginTop={1}>
                  <Text dimColor>outros agentes</Text>
                  {semAlvo.map(a => linhaAgente(a))}
                </Box>
              )}
            </Box>
          )
        })}
      </Box>
    )
  })
}
