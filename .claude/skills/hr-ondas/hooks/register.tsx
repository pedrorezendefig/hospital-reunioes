import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderSurface } from 'claude-code'

import type { Agente, CardCitado, Ci, Coleta, Encerrar, EstadoOnda, Faixa, FatiaDaFaixa, Fase, Issue, Migration, Prd, SubAgente, Subida, Tarefa } from '../types'

// Torre das ondas: só leitura. A coleta (hooks/coletar.sh) junta o coletor do PedroOS,
// o `claude agents`, as migrations que a subida pediu e o /api/health.
// O relógio só olha o que é local (sessões, agentes, subidas, migrations); o GitHub e o OS
// são buscados quando um evento do workflow acontece: agente que começa ou termina, sessão
// que nasce ou para, subida que fecha, migration nova, ou um gh/fechar_onda nesta sessão.
// É um painel de monitoramento, sem link: cada Fatia mostra o tempo de cada etapa, e cada item do
// "Precisa de você" tem o botão resolver, que abre no Claude Agents uma sessão só daquele item.
// Vale para todo Projeto com o Pacote do fluxo (o coletar.sh lê o .claude/fluxo.json dele).

const PANE = 'ondas'
const COLUNAS = 100
const PERIODO_MS = 10_000
/** Comando desta sessão que muda o GitHub ou a produção: ao terminar, recoleta. */
const EVENTO_NO_SHELL = /fechar_onda\.py\s+--prs|gh\s+pr\s+(create|merge|ready|close)|gh\s+issue\s+(create|close|edit)|gh\s+run\s+watch|gh\s+pr\s+checks\b[^|;&]*--watch/
const APLICADA_VISIVEL_MS = 60 * 60 * 1000

/** dono/nome do repositório: o do OS, senão o do remote origin. */
const repoDa = (c: Coleta | null) => c?.os?.repo ?? c?.repo ?? ''
/** Como o humano aplica a migration e o editor SQL do Projeto (`migrations` do .claude/fluxo.json). */
const aplicarDa = (c: Coleta | null) => c?.migracoes?.aplicar ?? 'aplique no banco'
const editorDa = (c: Coleta | null) => c?.migracoes?.editor ?? null
const rotuloDoEditor = (url: string) => (/studio/i.test(url) ? 'Studio' : 'editor SQL')

const coleta = atom({ plugin: 'hr-ondas', key: 'coleta' } as const, null)
const erro = atom({ plugin: 'hr-ondas', key: 'erro' } as const, null)
const todos = atom({ plugin: 'hr-ondas', key: 'todos' } as const, false)
const faixa = atom({ plugin: 'hr-ondas', key: 'faixa' } as const, null)
const relogio = atom({ plugin: 'hr-ondas', key: 'relogio' } as const, 0)
const cards = atom({ plugin: 'hr-ondas', key: 'cards' } as const, {})
const verDetalhe = atom({ plugin: 'hr-ondas', key: 'verDetalhe' } as const, false)

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

/** A Etapa da Fatia em texto; sem `comEspera`, sem as bloqueadoras (a linha da Onda já as diz). */
export const detalhe = (i: Issue, comEspera = true): string => {
  const partes: string[] = [NOME[i.fase]]
  if (i.fase === 'pr_aberto') {
    if (i.ci) partes.push(`CI ${i.ci.replace('_', ' ')}`)
    if (i.veredito) partes.push(i.veredito.toLowerCase())
    if (i.conflito) partes.push('conflito')
  }
  if (i.versao) partes.push(i.versao)
  if (comEspera && i.por.length) partes.push(`espera ${i.por.map(n => `#${n}`).join(' ')}`)
  return partes.join(' · ')
}

/** Um card que a pendência manda olhar; `feito` quando já fechou. */
export type CardPendente = { n: number; texto: string; feito: boolean }

/**
 * A sessão que o botão resolver abre no Claude Agents: o nome e o pedido. Com `viva`, a sessão que já cuida do
 * item (a da própria Onda) está rodando: o botão só traz o Claude Agents, sem lançar outra.
 */
export type PedidoDeSessao = { nome: string; prompt: string; viva: string | null }

/** Uma linha do bloco "Precisa de você", com a sessão que o botão resolver abre. */
export type Pendencia = {
  chave: string
  cor: 'error' | 'warning'
  marca: string
  rotulo: string
  texto: string
  /** o motivo por extenso, como a Onda gravou */
  detalhe?: string | null
  cards?: CardPendente[]
  sessao: PedidoDeSessao | null
}

const NOME_DE_SESSAO = /^\w[\w.-]*$/
const ESTADO_ONDA_PY = 'python3 .claude/skills/onda-enxuta/scripts/estado_onda.py'
const ORIGEM = 'Esta sessão foi aberta pelo botão resolver do painel das Ondas (mod hr-ondas).'

/**
 * O pedido do Fechar a Onda do PedroOS (app/server/sessao-de-onda.js, promptDoFechamento): lê o Estado da Onda,
 * faz a parte do agente, guia a do humano e grava o `resolvido`. Sem linhagem e número válidos, null.
 */
export const pedidoDaOnda = (o: EstadoOnda, vivas: string[]): PedidoDeSessao | null => {
  const m = /^(.+)-onda(\d+)$/.exec(o.id)
  const sessao = o.sessao ?? m?.[1] ?? ''
  const numero = o.onda ?? Number(m?.[2])
  if (![o.id, sessao].every(s => NOME_DE_SESSAO.test(s)) || !Number.isInteger(numero) || numero <= 0) return null
  const alvo = `--sessao ${sessao} --onda ${numero}`
  return {
    nome: `fechar-${o.id}`,
    viva: vivas.includes(o.id) ? o.id : null,
    prompt: `Feche a Onda ${o.id}: ela ${o.estado === 'erro' ? 'quebrou' : 'está em "espera você"'}.
1. Leia o Estado da Onda: ${ESTADO_ONDA_PY} ler ${alvo}. O que falta são os eventos pronto-para-voce e erro depois do último resolvido, e as issues em baixa.
2. Mostre ao Pedro, uma linha por pendência, o que cada uma pede. Leia o que precisar no GitHub (gh issue view --comments, gh pr view) e confira se já foi feito antes de pedir alguma coisa.
3. Faça a parte do agente. O que é só do Pedro (mandar uma mensagem, aplicar uma migration, decidir algo de produto) vira passo a passo, um passo por vez; mensagem para ele mandar vai pronta num bloco de código. Espere o "feito" e confira.
4. Com tudo resolvido, rode: ${ESTADO_ONDA_PY} resolvido ${alvo} --texto "<o que foi feito, numa frase>". Issue em baixa só sai quando o PR dela entra pela subida (fechar_onda.py), que já marca a Onda.
${ORIGEM} Merge, deploy ou migration só com o "pode" do Pedro aqui.`,
  }
}

/** O pedido do "acompanhar" do PedroOS: a issue humana que o Pedro faz agora, um passo por vez, e fecha no fim. */
export const pedidoDaHumana = (n: number): PedidoDeSessao => ({
  nome: `acompanhar-${n}`,
  viva: null,
  prompt: `A issue #${n} é humana e o Pedro vai fazer agora. Leia o card com gh issue view ${n} --comments e acompanhe o Passo a passo dele, um passo por vez: mostre o passo e o link, ofereça fazer pelo playwright-cli ou pelo gh o que der, espere o "feito" e confira antes de passar ao próximo. Login, senha, pagamento e segredo ficam com o Pedro.
${ORIGEM} No fim, comente na issue o que foi feito e feche.`,
})

/** O PR com CI vermelho: a sessão lê a falha, conserta na branch do PR e leva até o verde. */
export const pedidoDoCi = (n: number, pr: number): PedidoDeSessao => ({
  nome: `ci-pr-${pr}`,
  viva: null,
  prompt: `O PR #${pr} da issue #${n} está com o CI vermelho. Leia a falha (gh pr checks ${pr}, gh run view <id> --log-failed), conserte na branch do PR num worktree, rode as conferências locais e leve até o CI verde. Mostre ao Pedro a causa numa linha antes de mexer.
${ORIGEM} Merge, deploy ou migration só com o "pode" do Pedro aqui.`,
})

/** Os cards que uma Onda cita no motivo (#N, fora o PRD dela) mais as issues dela em baixa. */
export const cardsDaOnda = (o: EstadoOnda): number[] => {
  const citados = [...(o.texto ?? '').matchAll(/#(\d+)/g)].map(m => Number(m[1])).filter(n => n !== o.prd)
  return [...new Set([...(o.baixas ?? []), ...citados])]
}

/** Os números que as Ondas citam e que o OS não traz: o mod busca o título deles no GitHub. */
export const cardsSemTitulo = (c: Coleta): number[] => {
  const doOs = new Set([...(c.os?.prds ?? []).flatMap(p => [p.n, ...p.issues.map(i => i.n)]), ...(c.os?.soltas ?? []).map(i => i.n)])
  const todos = (c.ondasEstado ?? []).flatMap(o => [...(o.prd ? [o.prd] : []), ...cardsDaOnda(o)])
  return [...new Set(todos)].filter(n => !doOs.has(n))
}

/**
 * O que espera você, fora as migrations (que têm botão próprio): Onda que quebrou ou espera você,
 * Fatia humana aberta e PR com CI vermelho, cada um com a sessão do botão resolver. A Onda traz o motivo
 * por extenso e os cards que ele cita (o PRD e as issues); a Fatia citada por uma Onda não se repete.
 */
export const precisaDeVoce = (c: Coleta, citados: Record<string, CardCitado> = {}): Pendencia[] => {
  const issues = new Map([...(c.os?.prds ?? []).flatMap(p => p.issues), ...(c.os?.soltas ?? [])].map(i => [i.n, i]))
  const prds = new Map((c.os?.prds ?? []).map(p => [p.n, p]))
  const vivas = c.agentes.map(a => a.nome)
  const card = (n: number): CardPendente => {
    const i = issues.get(n)
    const titulo = i?.titulo ?? prds.get(n)?.titulo ?? (citados[n]?.titulo || null)
    const aberto = i ? i.estado === 'OPEN' : (citados[n]?.aberto ?? true)
    return { n, texto: `#${n}${i?.fase === 'humana' ? ' é sua' : ''}${titulo ? ` · ${titulo}` : ''}`, feito: !aberto }
  }
  const ondas = [...(c.ondasEstado ?? [])]
    .sort((a, b) => Number(b.estado === 'erro') - Number(a.estado === 'erro'))
    .map(o => ({
      chave: `o${o.id}`,
      cor: o.estado === 'erro' ? ('error' as const) : ('warning' as const),
      marca: o.estado === 'erro' ? '✗' : '!',
      rotulo: `Onda ${o.id}`,
      texto: o.estado === 'erro' ? 'quebrou' : 'espera você',
      detalhe: o.texto,
      cards: [...(o.prd ? [{ ...card(o.prd), texto: card(o.prd).texto.replace(/^#/, 'PRD #') }] : []), ...cardsDaOnda(o).map(card)],
      sessao: pedidoDaOnda(o, vivas),
    }))
  const naOnda = new Set(ondas.flatMap(o => o.cards.map(k => k.n)))
  const fatias = new Map<number, Pendencia>()
  for (const i of (c.os?.prds ?? []).flatMap(p => p.issues)) {
    if (i.estado !== 'OPEN' || fatias.has(i.n) || naOnda.has(i.n)) continue
    const humana = i.fase === 'humana'
    if (!humana && !(i.fase === 'pr_aberto' && i.ci === 'vermelho')) continue
    fatias.set(i.n, {
      chave: `i${i.n}`,
      cor: humana ? 'warning' : 'error',
      marca: humana ? '!' : '✗',
      rotulo: `#${i.n}`,
      texto: `${humana ? 'é sua' : 'CI vermelho'} · ${i.titulo}`,
      sessao: humana ? pedidoDaHumana(i.n) : i.pr ? pedidoDoCi(i.n, i.pr) : null,
    })
  }
  return [...ondas, ...fatias.values()]
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
  'onda-implementador': [30, 35],
  'onda-revisor': [5, 10],
  'onda-corretor': [10, 15],
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
  /** `subidaS`: os segundos da subida no registro da main, quando a sessão que subiu já acabou */
  extra: { ci?: Ci; subida?: Subida; subidaS?: number; migrationPendente?: boolean } = {},
) => {
  // passo humano fechado (ou issue encerrada sem código): não houve esteira para mostrar
  if (i.fase === 'encerrada_sem_pr') return [{ nome: 'fechada sem PR', estado: 'feita' as EstadoEtapa }]
  // o papel conta, não o prefixo: o nome antigo dos agentes (hr) e o novo (onda) são a mesma etapa
  const de = (tipo: string) => ags.filter(a => papelDoAgente(a.tipo) === papelDoAgente(tipo))
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
    com('implementar', estado('onda-implementador', depoisDoPr), gasto('onda-implementador'), 'onda-implementador'),
    com('CI', subiu || i.ci === 'verde' ? 'feita' : i.ci === 'vermelho' ? 'falhou' : i.pr ? 'agora' : 'falta', ciMs),
    com('revisar', estado('onda-revisor', subiu || !!i.veredito), gasto('onda-revisor'), 'onda-revisor'),
  ]
  if (de('onda-corretor').length) lista.push(com('corrigir', estado('onda-corretor', subiu), gasto('onda-corretor'), 'onda-corretor'))
  const s = extra.subida
  const subidaMs = s ? (s.fim ?? agora) - s.inicio : extra.subidaS !== undefined ? extra.subidaS * 1000 : undefined
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

/** As etapas que já têm tempo, na ordem da esteira: o que vai na linha da Fatia. */
export const temposDaFatia = (lista: Etapa[]) => lista.filter((s): s is Etapa & { ms: number } => s.ms !== undefined)

/** Menos de um minuto em segundos; o resto como `minutos`. */
export const tempoCurto = (ms: number) => (ms < 60_000 ? `${Math.max(0, Math.round(ms / 1000))} s` : minutos(ms))

/** Os sub-agentes que trabalharam na Fatia: os das sessões vivas e os do histórico (sessão já encerrada), sem repetir. */
export const agentesDaFatia = (c: Coleta, prd: Prd, vivos: SubAgente[], n: number): SubAgente[] => {
  const ids = new Set(vivos.map(a => a.id))
  return [...vivos, ...(c.historico ?? []).filter(a => !ids.has(a.id))].filter(a => alvo(a, prd) === n)
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

/** O que a Onda espera de fora dela (quem está na mão do humano, dito), ou null. */
export const esperaDeFora = (issues: Issue[], onda: number[], porN?: Map<number, Issue>): string | null => {
  const fora = [...new Set(issues.flatMap(i => i.por))].filter(n => !onda.includes(n)).sort((a, b) => a - b)
  const nome = (n: number) => (porN?.get(n)?.fase === 'humana' ? `#${n} (humana)` : `#${n}`)
  return fora.length ? `espera ${fora.map(nome).join(' ')}` : null
}

/** Fatia no ar: em produção ou fechada (o passo humano fecha sem PR). */
export const noAr = (i: Issue) => i.fase === 'em_producao' || i.estado === 'CLOSED'

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

// ---------------------------------------------------------------------------
// Faixa da sessão: a fase desta sessão na esteira, acima do prompt. Só inferência:
// o que a sessão chama (Skill, Agent, Bash, Monitor) e escreve (Rodada, P, Porta),
// mais as linhas que a /onda-enxuta já grava pelo estado_onda.py. Nenhuma skill muda.

/** As skills da esteira e o nome da fase de cada uma na faixa. */
export const FASE_DA_SKILL: Record<string, string> = {
  'grill-with-docs': 'grill',
  'grill-me': 'grill',
  express: 'express',
  'to-prd': 'PRD',
  'to-issues': 'fatias',
  triage: 'triagem',
  'pegar-issue': 'pegar issue',
  tdd: 'TDD',
  ship: 'ship',
  'onda-enxuta': 'onda',
  'montar-ondas-enxutas': 'montar ondas',
  'retro-onda': 'retro',
  'resolver-conflitos': 'conflitos',
  diagnose: 'diagnóstico',
  deploy: 'deploy',
}
const GRILL = new Set(['grill-with-docs', 'grill-me', 'express'])
export const MAX_TENTATIVAS = 3
/** Minutos a partir dos quais o cronômetro fica amarelo. */
export const LIMITE_DA_FASE: Record<string, number> = {
  TDD: 30,
  'revisão': 10,
  'correção': 10,
  CI: 15,
  subida: 25,
  shell: 5,
}

export const faixaVazia = (): Faixa => ({
  skill: null, rodada: null, perguntas: null, porta: null,
  tarefas: [], fatias: [], paradas: [], prs: [], ociosaDesde: null, encerrar: null,
})

const papelDoAgente = (tipo: string | null) =>
  /^(?:onda|hr)-(implementador|revisor|corretor)$/.exec(tipo ?? '')?.[1] ?? null
const numeroPr = (t: string) => Number(/\bPR\s*#?(\d+)/i.exec(t)?.[1]) || null
const numeroIssue = (t: string) => Number(/\bissue\s*#?(\d+)/i.exec(t)?.[1]) || null
const prDoCi = (cmd: string) => Number(/gh\s+pr\s+checks\s+(\d+)/.exec(cmd)?.[1]) || null
const prsDaSubida = (cmd: string) =>
  /fechar_onda\.py\b/.test(cmd) && !/--dry-run/.test(cmd)
    ? (/--prs\s+([\d\s]+)/.exec(cmd)?.[1]?.match(/\d+/g) ?? []).map(Number)
    : []
const opcao = (cmd: string, nome: string) => {
  const m = new RegExp(`--${nome}\\s+(?:"([^"]*)"|'([^']*)'|(\\S+))`).exec(cmd)
  return m ? (m[1] ?? m[2] ?? m[3] ?? null) : null
}

const comFatia = (f: Faixa, issue: number, muda: (x: FatiaDaFaixa) => FatiaDaFaixa): Faixa => {
  const existe = f.fatias.some(x => x.issue === issue)
  const base: FatiaDaFaixa = { issue, pr: null, status: null, tentativas: 0, veredito: null }
  return { ...f, fatias: existe ? f.fatias.map(x => (x.issue === issue ? muda(x) : x)) : [...f.fatias, muda(base)] }
}
const comPrs = (f: Faixa, prs: number[]): Faixa => ({ ...f, prs: [...new Set([...f.prs, ...prs])] })

/** A sessão chamou uma skill (pela ferramenta Skill ou pelo comando digitado). */
export const aoChamarSkill = (f: Faixa, nome: string): Faixa => {
  const skill = nome.replace(/^\//, '').split(':').pop()!
  if (!(skill in FASE_DA_SKILL)) return f
  if (skill === f.skill) return f
  // grill novo começa sem rodada; o express continua o grill em lote
  const continuaGrill = skill === 'express' && GRILL.has(f.skill ?? '')
  return continuaGrill ? { ...f, skill } : { ...f, skill, rodada: null, perguntas: null, porta: null }
}

/** Um tool_use da sessão principal. */
export const aoUsar = (f: Faixa, id: string, ferramenta: string, input: Record<string, unknown>, em: number): Faixa => {
  const txt = (k: string) => (typeof input[k] === 'string' ? (input[k] as string) : '')
  if (ferramenta === 'Skill') return aoChamarSkill(f, txt('skill'))
  if (ferramenta === 'TaskStop' || ferramenta === 'KillShell') {
    const alvo = txt('task_id') || txt('shell_id')
    return alvo ? { ...f, tarefas: f.tarefas.filter(t => !t.recibo?.includes(alvo)) } : f
  }
  const nova = (x: Partial<Tarefa>): Tarefa => ({
    id, tipo: 'shell', descricao: '', comando: null, agente: null, issue: null, pr: null, inicio: em, recibo: null, ...x,
  })

  if (ferramenta === 'Agent') {
    const tipo = txt('subagent_type') || 'general-purpose'
    const papel = papelDoAgente(tipo)
    const texto = `${txt('description')}\n${txt('prompt').slice(0, 600)}`
    const pr = numeroPr(texto)
    let issue = numeroIssue(texto) ?? (papel === 'implementador' ? Number(/#(\d+)/.exec(txt('description'))?.[1]) || null : null)
    if (!issue && pr) issue = f.fatias.find(x => x.pr === pr)?.issue ?? null
    let g: Faixa = { ...f, tarefas: [...f.tarefas, nova({ tipo: 'agente', descricao: txt('description'), agente: tipo, issue, pr })] }
    if (papel && issue) {
      const motivo = /Motivo:\s*(\w+)/i.exec(txt('prompt'))?.[1]?.toLowerCase()
      g = comFatia(g, issue, x => ({
        ...x,
        pr: pr ?? x.pr,
        veredito: papel === 'revisor' ? null : x.veredito,
        tentativas: papel === 'corretor' && motivo !== 'conflito' ? x.tentativas + 1 : x.tentativas,
      }))
    }
    return g
  }

  if (ferramenta === 'Monitor') {
    const cmd = txt('command')
    return { ...f, tarefas: [...f.tarefas, nova({ tipo: 'monitor', descricao: txt('description'), comando: cmd, pr: prDoCi(cmd) })] }
  }

  if (ferramenta !== 'Bash') return f
  const cmd = txt('command')
  let g = f
  if (/estado_onda\.py\s+issue\b/.test(cmd)) {
    const n = Number(opcao(cmd, 'numero'))
    const pr = Number(opcao(cmd, 'pr')) || null
    const status = opcao(cmd, 'status')
    if (n) g = comFatia(g, n, x => ({ ...x, pr: pr ?? x.pr, status: status ?? x.status }))
  }
  if (/estado_onda\.py\s+evento\b/.test(cmd) && /--tipo\s+(erro|pronto-para-voce)\b/.test(cmd)) {
    const texto = opcao(cmd, 'texto')
    if (texto && !g.paradas.includes(texto)) g = { ...g, paradas: [...g.paradas, texto] }
  }
  if (/estado_onda\.py\s+resolvido\b/.test(cmd)) g = { ...g, paradas: [] }
  const subida = prsDaSubida(cmd)
  if (subida.length) g = comPrs(g, subida)
  const bg = input.run_in_background === true
  const descricao = subida.length
    ? `subida dos PRs ${subida.map(n => `#${n}`).join(' ')}`
    : txt('description') || curto(cmd.split('\n')[0]!, 60)
  return { ...g, tarefas: [...g.tarefas, nova({ tipo: bg ? 'shell-bg' : 'shell', descricao, comando: cmd, pr: prDoCi(cmd) })] }
}

const ACK_DE_FUNDO = /launched|running in the background|async agent|agentId:/i

/** O veredito do revisor e o fim de um agente da onda. */
const aoTerminarAgente = (f: Faixa, t: Tarefa, resultado: string): Faixa => {
  const papel = papelDoAgente(t.agente)
  if (papel !== 'revisor' || !t.issue) return f
  const v = /veredito:?\**\s*(LIMPO|MUST-FIX)/i.exec(resultado)?.[1]?.toUpperCase() as FatiaDaFaixa['veredito'] | undefined
  return v ? comFatia(f, t.issue, x => ({ ...x, veredito: v })) : f
}

/** O tool_result de um tool_use da sessão principal. */
export const aoResultado = (f: Faixa, id: string, texto: string): Faixa => {
  const t = f.tarefas.find(x => x.id === id)
  if (!t) return f
  const sem = { ...f, tarefas: f.tarefas.filter(x => x.id !== id) }
  if (t.tipo === 'shell') {
    const abertos = /gh\s+pr\s+create\b/.test(t.comando ?? '')
      ? (texto.match(/\/pull\/(\d+)/g) ?? []).map(s => Number(s.slice(6)))
      : []
    return comPrs(sem, abertos)
  }
  if (t.tipo === 'agente' && !ACK_DE_FUNDO.test(texto)) return aoTerminarAgente(sem, t, texto)
  return { ...f, tarefas: f.tarefas.map(x => (x.id === id ? { ...x, recibo: texto.slice(0, 2000) } : x)) }
}

/** O texto de uma linha que chegou para a sessão: task-notification ou comando digitado. */
export const aoReceber = (f: Faixa, texto: string): Faixa => {
  let g = f
  const comando = /<command-name>\/?([\w:-]+)<\/command-name>/.exec(texto)?.[1]
  if (comando) g = aoChamarSkill(g, comando)
  for (const [, bloco] of texto.matchAll(/<task-notification>([\s\S]*?)<\/task-notification>/g)) {
    const id = /<tool-use-id>([^<]+)<\/tool-use-id>/.exec(bloco!)?.[1]
    const status = /<status>([^<]+)<\/status>/.exec(bloco!)?.[1]
    if (!id || !status || status === 'running') continue
    const t = g.tarefas.find(x => x.id === id)
    if (!t) continue
    g = { ...g, tarefas: g.tarefas.filter(x => x.id !== id) }
    if (t.tipo === 'agente') g = aoTerminarAgente(g, t, /<result>([\s\S]*?)<\/result>/.exec(bloco!)?.[1] ?? '')
  }
  return g
}

/** O texto que o modelo escreveu: Rodada, as perguntas P e a Porta do grill. */
export const aoEscrever = (f: Faixa, texto: string): Faixa => {
  if (!GRILL.has(f.skill ?? '')) return f
  let g = f
  const rodadas = [...texto.matchAll(/\*\*Rodada\s+(\d+)\*\*/g)].map(m => Number(m[1]))
  if (rodadas.length) g = { ...g, rodada: rodadas[rodadas.length - 1]! }
  const ps = [...texto.matchAll(/\*\*P(\d+)\./g)].map(m => Number(m[1]))
  if (ps.length) g = { ...g, perguntas: [Math.min(...ps), Math.max(...ps)] }
  const porta = /\*\*Porta:?\*?\*?:?\s*([ABC])\b/.exec(texto)?.[1]
  if (porta) g = { ...g, porta }
  return g
}

export const faixaAtiva = (f: Faixa | null): f is Faixa =>
  !!f && (!!f.skill || f.fatias.length > 0 || f.paradas.length > 0 || f.prs.length > 0)

export type LinhaDaFaixa = { chave: string; partes: { texto: string; cor?: string; dim?: boolean; bold?: boolean }[] }

/** A fase de uma Fatia e a tarefa que a cronometra. */
export const faseDaFatia = (f: Faixa, x: FatiaDaFaixa): { fase: string; desde: Tarefa | null } => {
  const daFatia = (t: Tarefa) => t.issue === x.issue || (x.pr !== null && t.pr === x.pr)
  const agente = f.tarefas.find(t => t.tipo === 'agente' && papelDoAgente(t.agente) && daFatia(t))
  if (agente) {
    const papel = papelDoAgente(agente.agente)
    return { fase: papel === 'implementador' ? 'TDD' : papel === 'revisor' ? 'revisão' : 'correção', desde: agente }
  }
  if (x.pr !== null) {
    const ci = f.tarefas.find(t => t.tipo !== 'agente' && t.pr === x.pr)
    if (ci) return { fase: 'CI', desde: ci }
    const subida = f.tarefas.find(t => prsDaSubida(t.comando ?? '').includes(x.pr!))
    if (subida) return { fase: 'subida', desde: subida }
  }
  const porStatus: Record<string, string> = {
    fila: 'na fila', implementando: 'TDD', revisao: 'revisão', correcao: 'correção',
    verde: 'verde, esperando a subida', baixa: 'baixa', mergeado: 'mergeada',
  }
  if (x.status && porStatus[x.status]) return { fase: porStatus[x.status]!, desde: null }
  if (x.veredito === 'MUST-FIX') return { fase: 'must-fix', desde: null }
  return { fase: x.pr ? 'PR aberto' : 'na fila', desde: null }
}

const corDoCronometro = (fase: string, ms: number) =>
  LIMITE_DA_FASE[fase] !== undefined && ms >= LIMITE_DA_FASE[fase]! * 60_000 ? 'warning' : undefined

/** As linhas da faixa, de cima para baixo. Vazia quando a sessão não está na esteira. */
export const linhasDaFaixa = (f: Faixa | null, agora: number): LinhaDaFaixa[] => {
  if (!faixaAtiva(f)) return []
  const linhas: LinhaDaFaixa[] = []

  const fase = f.skill ? FASE_DA_SKILL[f.skill]! : 'onda'
  const cab: LinhaDaFaixa['partes'] = [{ texto: '▸ fase: ', dim: true }, { texto: fase, bold: true, cor: 'suggestion' }]
  if (f.rodada !== null) cab.push({ texto: ` · rodada ${f.rodada}` })
  if (f.perguntas) cab.push({ texto: ` · ${f.perguntas[0] === f.perguntas[1] ? `P${f.perguntas[0]}` : `P${f.perguntas[0]} a P${f.perguntas[1]}`}` })
  if (f.porta) cab.push({ texto: ` · porta ${f.porta}`, cor: 'success' })
  if (f.ociosaDesde !== null && f.tarefas.length === 0) {
    cab.push({ texto: ` · esperando você há ${minutos(agora - f.ociosaDesde)}`, cor: 'warning' })
  }
  linhas.push({ chave: 'fase', partes: cab })

  const usadas = new Set<string>()
  for (const x of f.fatias) {
    if (x.status === 'mergeado') continue
    const { fase: fx, desde } = faseDaFatia(f, x)
    if (desde) usadas.add(desde.id)
    const baixa = x.status === 'baixa'
    const p: LinhaDaFaixa['partes'] = [
      { texto: `  ${baixa ? '✗' : '•'} #${x.issue}`, bold: true, cor: baixa ? 'error' : undefined },
      { texto: ` · ${fx}`, cor: baixa ? 'error' : fx.startsWith('verde') ? 'success' : undefined },
    ]
    if (x.pr) p.push({ texto: ` · PR #${x.pr}`, dim: true })
    if (x.veredito && fx !== 'revisão') p.push({ texto: ` · ${x.veredito}`, cor: x.veredito === 'LIMPO' ? 'success' : 'warning' })
    if (x.tentativas > 0) {
      p.push({
        texto: ` · tentativa ${x.tentativas}/${MAX_TENTATIVAS}`,
        cor: x.tentativas >= MAX_TENTATIVAS ? 'error' : x.tentativas === MAX_TENTATIVAS - 1 ? 'warning' : undefined,
      })
    }
    if (desde) p.push({ texto: ` · ${duracao(agora - desde.inicio)}`, cor: corDoCronometro(fx, agora - desde.inicio), dim: !corDoCronometro(fx, agora - desde.inicio) })
    linhas.push({ chave: `fatia${x.issue}`, partes: p })
  }

  for (const t of f.tarefas) {
    if (usadas.has(t.id)) continue
    const ms = agora - t.inicio
    const subida = prsDaSubida(t.comando ?? '').length > 0
    const [rotulo, chaveLimite] =
      t.pr && t.tipo !== 'agente'
        ? [`CI do PR #${t.pr}`, 'CI']
        : subida
          ? [t.descricao, 'subida']
          : t.tipo === 'shell'
            ? [`shell: ${t.descricao}`, 'shell']
            : t.tipo === 'shell-bg'
              ? [`em segundo plano: ${t.descricao}`, '']
              : t.tipo === 'monitor'
                ? [`monitor: ${t.descricao}`, '']
                : [`agente ${t.agente}: ${t.descricao}`, '']
    const cor = corDoCronometro(chaveLimite, ms)
    linhas.push({
      chave: `t${t.id}`,
      partes: [{ texto: `  ◷ ${rotulo}` }, { texto: ` · ${duracao(ms)}`, cor, dim: !cor }],
    })
  }

  f.paradas.forEach((texto, i) =>
    linhas.push({ chave: `parada${i}`, partes: [{ texto: `  ! espera você: ${texto}`, cor: 'warning', bold: true }] }),
  )

  const e = f.encerrar
  if (e && f.ociosaDesde !== null && f.tarefas.length === 0) {
    const falta = [
      ...e.abertos.map(n => `PR #${n} aberto`),
      ...(e.semCommit ? [`${e.semCommit} arquivo(s) sem commit`] : []),
      ...(e.worktree ? [`worktree ${e.worktree}`] : []),
    ]
    if (falta.length) linhas.push({ chave: 'encerrar', partes: [{ texto: '  encerrar: falta ', dim: true }, { texto: falta.join(' · '), cor: 'warning' }] })
    else if (e.mergeados.length) {
      linhas.push({
        chave: 'encerrar',
        partes: [{ texto: '  encerrar: ', dim: true }, { texto: `pode (${e.mergeados.map(n => `PR #${n}`).join(', ')} mergeado)`, cor: 'success' }],
      })
    }
  }
  return linhas
}

/** O texto de um bloco de conteúdo, seja string ou lista de blocos. */
const textoDe = (c: unknown): string =>
  typeof c === 'string'
    ? c
    : Array.isArray(c)
      ? c.map(b => (b && typeof b === 'object' && 'text' in b && typeof b.text === 'string' ? b.text : '')).join('\n')
      : ''

/** Aplica uma linha da conversa principal à faixa. */
export const aoAnexar = (f: Faixa, mensagem: { type: string; content?: unknown }, em: number): Faixa => {
  const c = mensagem.content
  if (typeof c === 'string') return mensagem.type === 'assistant' ? aoEscrever(f, c) : aoReceber(f, c)
  if (!Array.isArray(c)) return f
  let g = f
  for (const b of c as { type?: string; [k: string]: unknown }[]) {
    if (b?.type === 'tool_use') g = aoUsar(g, String(b.id), String(b.name), (b.input ?? {}) as Record<string, unknown>, em)
    else if (b?.type === 'tool_result') g = aoResultado(g, String(b.tool_use_id), textoDe(b.content))
    else if (b?.type === 'text' && typeof b.text === 'string') g = mensagem.type === 'assistant' ? aoEscrever(g, b.text) : aoReceber(g, b.text)
  }
  return g
}

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

/**
 * Copia o .sql inteiro, byte a byte como está no arquivo, para colar no SQL Editor do Studio.
 * Nunca abre editor (o VS Code pesava na memória). No terminal do Mac confere o clipboard
 * contra o arquivo antes de dizer que copiou.
 */
async function copiarSql($: EngineInterface, m: Migration, surface: RenderSurface) {
  const reserva = `rode: ! pbcopy < '${m.caminho}'`
  try {
    const texto = await $.fs.read(m.caminho)
    const r = await $.ui.copy({ text: texto, surface })
    if (!r.isCopied) {
      $.ui.toast(`Não copiei a migration ${m.numero} (${r.reason}); ${reserva}`)
      return
    }
    if (surface === 'terminal') {
      const colado = await $.process.run(['/usr/bin/pbpaste'], { timeoutMs: 5_000 })
      if (colado.exitCode === 0 && colado.stdout !== texto) {
        $.ui.toast(`O clipboard não bate com a migration ${m.numero}; ${reserva}`)
        return
      }
    }
    $.ui.toast(`Migration ${m.numero} copiada inteira (${m.linhas} linhas): ${aplicarDa(await read($, coleta))}`)
  } catch (falha) {
    $.ui.toast(`Não copiei a migration ${m.numero}: ${String(falha).slice(0, 120)}; ${reserva}`)
  }
}

const abrindo = new Set<string>()

/**
 * O botão resolver: lança a sessão daquele item em segundo plano (hooks/resolver.sh, pelo lancar_sessao.sh da
 * onda) e traz para a frente o Claude Agents da pasta do Projeto, onde ela aparece. Sessão com o nome já viva
 * (ou a `viva` do pedido): não lança outra.
 */
async function resolver($: EngineInterface, p: PedidoDeSessao) {
  if (abrindo.has(p.nome)) return
  abrindo.add(p.nome)
  $.ui.toast(`Abrindo ${p.viva ?? p.nome} no Claude Agents…`)
  try {
    const r = await $.process.run(
      ['/bin/bash', `${$.plugin.root}/hooks/resolver.sh`, p.nome, ...(p.viva ? ['--viva', p.viva] : [])],
      { stdin: p.prompt, timeoutMs: 120_000 },
    )
    if (r.exitCode !== 0) throw new Error(r.stderr.trim().slice(0, 200) || `saída ${r.exitCode}`)
    $.ui.toast(r.stdout.trim().split('\n').pop() || `Sessão ${p.nome} no Claude Agents`)
  } catch (falha) {
    $.ui.toast(`Não abri a sessão ${p.nome}: ${String(falha).slice(0, 160)}`)
  } finally {
    abrindo.delete(p.nome)
  }
}

const CARD_VALE_MS = 10 * 60_000

/** Título e estado dos cards que as Ondas citam e o OS não traz (REST, até 10 por coleta, vale 10 min). */
async function buscarCards($: EngineInterface, c: Coleta) {
  const agora = await $.clock.now()
  const ja = await read($, cards)
  const faltam = cardsSemTitulo(c).filter(n => !ja[n] || agora - ja[n]!.em > CARD_VALE_MS).slice(0, 10)
  if (!faltam.length || !repoDa(c)) return
  const novos: Record<string, CardCitado> = {}
  for (const n of faltam) {
    const r = await $.process.run(['gh', 'api', `repos/${repoDa(c)}/issues/${n}`, '--jq', '[.state, .title] | @tsv'], { timeoutMs: 15_000 })
    const [estado, ...titulo] = r.exitCode === 0 ? r.stdout.trim().split('\t') : []
    // falhou: guarda o que tinha, para não bater no GitHub a cada 10 s
    novos[n] = estado ? { titulo: titulo.join(' '), aberto: estado === 'open', em: agora } : { ...(ja[n] ?? { titulo: '', aberto: true }), em: agora }
  }
  await update($, cards, v => ({ ...v, ...novos }))
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
    await update($, erro, () => (c.os ? null : 'Coletor do PedroOS sem resposta'))
    await buscarCards($, c).catch(() => {})

    const novasSessoes = c.agentes.filter(a => !sessoesVistas.has(a.nome))
    novasSessoes.forEach(a => sessoesVistas.add(a.nome))
    const novasMigrations = pendentes(c).filter(m => !migrationsAvisadas.has(m.numero))
    novasMigrations.forEach(m => migrationsAvisadas.add(m.numero))

    for (const m of novasMigrations) {
      $.ui.toast(`Migration ${m.numero} esperando você: ${aplicarDa(c)} (${m.sessao})`)
    }
    // a primeira coleta só abre se já houver onda rodando; depois, a cada novidade
    if (novasSessoes.length > 0 || novasMigrations.length > 0) {
      void $.ui.open({ id: PANE, title: 'Ondas', columns: COLUNAS })
    }

    const p = pendentes(c)
    const vivas = c.agentes.filter(a => a.status === 'busy').length
    $.ui.status(
      p.length
        ? `ondas: migration ${p.map(m => m.numero).join(', ')} esperando você: ${aplicarDa(c)}`
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

const RELOGIO_MS = 5_000

async function mudarFaixa($: EngineInterface, muda: (f: Faixa) => Faixa): Promise<Faixa> {
  return update($, faixa, f => muda(f ?? faixaVazia())) as Promise<Faixa>
}

/** A checagem da linha "Sessão: pode encerrar": PRs desta sessão, worktree e o que sobrou sem commit. */
async function checarEncerrar($: EngineInterface, f: Faixa) {
  try {
    const cwd = await $.session.cwd()
    const worktree = /\.claude\/worktrees\/([^/]+)/.exec(cwd)?.[1] ?? null
    let semCommit = 0
    if (worktree) {
      const st = await $.process.run(['git', 'status', '--short'], { timeoutMs: 10_000 })
      semCommit = st.exitCode === 0 ? st.stdout.split('\n').filter(Boolean).length : 0
    }
    const abertos: number[] = []
    const mergeados: number[] = []
    // REST, não GraphQL: as ondas em paralelo zeram a cota do GraphQL
    const repo = repoDa(await read($, coleta))
    for (const n of repo ? f.prs : []) {
      const r = await $.process.run(['gh', 'api', `repos/${repo}/pulls/${n}`, '--jq', '"\\(.state) \\(.merged)"'], { timeoutMs: 15_000 })
      if (r.exitCode !== 0) continue
      const [estado, merged] = r.stdout.trim().split(' ')
      if (merged === 'true') mergeados.push(n)
      else if (estado === 'open') abertos.push(n)
    }
    const encerrar: Encerrar = { abertos, mergeados, semCommit, worktree }
    await mudarFaixa($, x => ({ ...x, encerrar }))
  } catch {
    // sem gh ou sem git: a faixa fica sem a linha de encerrar
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'ondas',
      description: 'Torre das ondas: o que precisa de você, PRD, Onda e Etapa de cada Fatia (`/ondas todos` mostra todos os PRDs; `/ondas detalhe` liga e desliga o detalhe dos agentes)',
    })
    // a torre é o painel que nasce com a sessão interativa do Hospital
    if (e.isInteractive) void $.ui.open({ id: PANE, title: 'Ondas', columns: COLUNAS })
    void coletar($)
    $.clock.every(PERIODO_MS, () => coletar($))
    // os cronômetros da faixa andam enquanto há tarefa rodando ou a sessão espera você
    $.clock.every(RELOGIO_MS, async () => {
      const f = await read($, faixa)
      if (!faixaAtiva(f) || (!f.tarefas.length && f.ociosaDesde === null)) return
      const agora = await $.clock.now()
      await update($, relogio, () => agora)
    })
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
    const detalheAgora = arg === 'detalhe' ? await update($, verDetalhe, v => !v) : null
    await $.ui.open({ id: PANE, title: 'Ondas', columns: COLUNAS })
    await coletar($, true)
    if (detalheAgora !== null) return { text: `Detalhe dos agentes ${detalheAgora ? 'ligado' : 'desligado'} no painel das ondas.` }
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

  // Todo comando que muda o GitHub ou a produção recoleta ao terminar (o --watch do CI também).
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!EVENTO_NO_SHELL.test(e.command)) return next(e)
    try {
      return await next(e)
    } finally {
      void coletar($, true)
    }
  })

  // A faixa lê cada linha da conversa principal depois de guardada; a dos sub-agentes não.
  on('session.append', async ($, e, next) => {
    const r = await next(e)
    if (!e.agentId && e.door !== 'queue') {
      const em = await $.clock.now()
      await mudarFaixa($, f => aoAnexar(f, e.message, em))
    }
    return r
  })

  on('turn.start', async ($, e, next) => {
    if (!e.agentId) await mudarFaixa($, f => (f.ociosaDesde === null ? f : { ...f, ociosaDesde: null }))
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    if (!e.agentId) {
      const em = await $.clock.now()
      const f = await mudarFaixa($, x => ({ ...x, ociosaDesde: em }))
      if (faixaAtiva(f)) void checarEncerrar($, f)
    }
    return r
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const rest = await next(e)
    if (e.props.hasSurvey) return rest
    const c = await read($, coleta)
    const p = c ? pendentes(c) : []
    const linhas = linhasDaFaixa(await read($, faixa), (await read($, relogio)) || (await $.clock.now()))
    if (!p.length && !linhas.length) return rest
    const { Box, Text, Link, Button } = $.ui.resolve(e)
    const editor = editorDa(c)

    return (
      <Box flexDirection="column">
        {rest}
        {p.map(m => (
          <Box key={`m${m.numero}`} flexDirection="row">
            <Text color="warning">
              ⏳ migration {m.numero} esperando você: {aplicarDa(c)} ({m.linhas} linhas, {m.sessao}, há{' '}
              {minutos(c!.em - m.mtime)}){' '}
            </Text>
            <Button key={`copiar-faixa-${m.numero}`} label="copiar SQL" onPress={press => void copiarSql($, m, press.surface)} />
            {editor ? <Text color="warning"> · </Text> : null}
            {editor ? <Link href={editor} label={rotuloDoEditor(editor)} /> : null}
          </Box>
        ))}
        {linhas.map(l => (
          <Text key={l.chave} wrap="truncate-end">
            {l.partes.map(x => (
              <Text color={x.cor} dimColor={x.dim} bold={x.bold}>
                {x.texto}
              </Text>
            ))}
          </Text>
        ))}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link, Button } = $.ui.resolve(e)
    const c = await read($, coleta)
    const falha = await read($, erro)
    const mostrarTodos = await read($, todos)
    const comDetalhe = await read($, verDetalhe)
    const largura = Math.max(30, (e.props.bodyColumns ?? (e.viewport?.columns ?? 100) - 4) - 4)

    if (!c) {
      return (
        <Box flexDirection="column">
          <Text dimColor>{falha ?? 'Coletando (o coletor do PedroOS pode levar uns 20 s)…'}</Text>
        </Box>
      )
    }

    const p = pendentes(c)
    const recentes = aplicadasRecentes(c)
    const pendencias = precisaDeVoce(c, await read($, cards))
    const prds = prdsVisiveis(c, mostrarTodos)
    const editor = editorDa(c)
    const tituloDa = (i: Issue) => i.titulo.replace(/^Contas médicas: /, '')

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

    /** A esteira da Fatia com o tempo de cada etapa: sub-agentes vivos e do histórico, CI e subida. */
    const etapasDa = (i: Issue, prd: Prd, vivos: SubAgente[], sessao?: string) =>
      etapas(i, agentesDaFatia(c, prd, vivos, i.n), c.em, {
        ci: i.pr ? c.ci?.[String(i.pr)] : undefined,
        subida: subidaDoPr(c, i.pr),
        subidaS: i.pr ? c.subidasFeitas?.[String(i.pr)] : undefined,
        migrationPendente: p.some(m => m.sessao === sessao),
      })

    /** A esteira em uma linha, só as marcas: o tempo de cada etapa vai na linha da Fatia. */
    const passos = (i: Issue, lista: Etapa[]) => (
      <Text key={`s${i.n}`} wrap="truncate-end">
        {'    '}
        {lista.map((s, k) => (
          <Text key={`e${k}`}>
            {k > 0 ? <Text dimColor> → </Text> : null}
            <Text color={COR_ETAPA[s.estado]}>
              {s.nome}
              {MARCA_ETAPA[s.estado]}
            </Text>
          </Text>
        ))}
      </Text>
    )

    /** A linha da Fatia: o número, o tempo de cada etapa que já tem tempo e o título. */
    const linhaComTempos = (i: Issue, lista: Etapa[], recuo: string) => (
      <Text key={`t${i.n}`} wrap="truncate-end">
        {recuo}
        <Text color={corDaIssue(i)}>{MARCA[i.fase]} </Text>
        <Text bold>#{i.n}</Text>
        {temposDaFatia(lista).map(s => (
          <Text key={`${i.n}-${s.nome}`}>
            <Text dimColor> · </Text>
            {s.nome}{' '}
            <Text color={s.cor ?? 'suggestion'}>{tempoCurto(s.ms)}</Text>
          </Text>
        ))}
        <Text dimColor> · {curto(tituloDa(i), largura)}</Text>
      </Text>
    )

    /** Uma linha por Fatia fora da Onda que roda: a Etapa, o número e o título. */
    const linhaFatia = (i: Issue, comEspera: boolean, recuo: string) => (
      <Text key={`f${i.n}`} wrap="truncate-end">
        {recuo}
        <Text color={corDaIssue(i)}>{MARCA[i.fase]} </Text>
        <Text bold>#{i.n}</Text>
        <Text color={corDaIssue(i)}> {detalhe(i, comEspera)}</Text>
        <Text dimColor> · {tituloDa(i)}</Text>
      </Text>
    )

    return (
      <Box flexDirection="column">
        <Text dimColor wrap="truncate-end">
          atualizado há {minutos((await $.clock.now()) - (c.remotoEm ?? c.em))} ·{' '}
          {mostrarTodos ? 'todos os PRDs (/ondas ativos)' : 'PRDs ativos (/ondas todos)'}
          {c.osEm != null && c.osEm < (c.remotoEm ?? c.em) ? (
            <Text color="warning"> · PedroOS sem resposta, PRDs de há {minutos(c.em - c.osEm)}</Text>
          ) : null}
        </Text>
        {falha && <Text color="error">{falha}</Text>}

        <Box flexDirection="column" marginTop={1}>
          <Text bold>
            Precisa de você
            {p.length > 0 ? <Text dimColor> · migration no ar: {c.aplicada ?? '?'}</Text> : null}
          </Text>
          {p.map((m, k) => (
            <Box key={`p${m.numero}`} flexDirection="row">
              <Text color="warning">
                {'  '}⏳ migration {m.numero} {k === 0 ? aplicarDa(c) : `depois da ${p[k - 1]?.numero}`}{' '}
              </Text>
              <Button key={`copiar-${m.numero}`} label="copiar SQL" onPress={press => void copiarSql($, m, press.surface)} />
              <Text color="warning" wrap="truncate-end">
                {' '}
                {editor ? (
                  <Text>
                    · <Link href={editor} label={rotuloDoEditor(editor)} />{' '}
                  </Text>
                ) : null}
                · {m.linhas} linhas · {m.sessao} · há {minutos(c.em - m.mtime)}
              </Text>
            </Box>
          ))}
          {/* O botão vem antes do texto: a linha longa corta o fim, nunca o botão. */}
          {pendencias.map(x => (
            <Box key={x.chave} flexDirection="column">
              <Box flexDirection="row">
                <Text color={x.cor}>
                  {'  '}
                  {x.marca}{' '}
                </Text>
                {x.sessao ? (
                  <Button key={`resolver-${x.chave}`} label="resolver" onPress={() => void resolver($, x.sessao!)} />
                ) : null}
                <Text wrap="truncate-end">
                  {' '}
                  <Text bold>{x.rotulo}</Text>
                  <Text color={x.cor}> {x.texto}</Text>
                </Text>
              </Box>
              {x.detalhe ? (
                <Box paddingLeft={4}>
                  <Text wrap="wrap">{x.detalhe}</Text>
                </Box>
              ) : null}
              {(x.cards ?? []).map(k => (
                <Box key={`${x.chave}-${k.n}`} paddingLeft={4}>
                  <Text wrap="truncate-end" dimColor={k.feito}>
                    → {k.feito ? '✓ fechado · ' : ''}
                    {k.texto}
                  </Text>
                </Box>
              ))}
            </Box>
          ))}
          {pendencias.some(x => x.sessao) && (
            <Text key="resolver" dimColor wrap="truncate-end">
              {'  '}resolver abre no Claude Agents uma sessão só daquele item: ela faz a parte do agente, guia a sua e fecha no fim
            </Text>
          )}
          {p.length === 0 && pendencias.length === 0 && <Text color="success">{'  '}✓ Nada espera você</Text>}
          {recentes.length > 0 && (
            <Text key="aplicadas" color="success" dimColor wrap="truncate-end">
              {'  '}✓ aplicada na última hora: migration {[...new Set(recentes.map(m => m.numero))].join(', ')}
            </Text>
          )}
        </Box>

        {prds.length === 0 && (
          <Box marginTop={1}>
            <Text dimColor>Nenhum PRD com onda rodando ou fatia andando. /ondas todos mostra tudo.</Text>
          </Box>
        )}

        {prds.map(prd => {
          const sessoes = sessoesDoPrd(c, prd.n)
          const ags = agentesDoPrd(c, prd)
          const ondas = ondasDoPrd(c, prd)
          const porN = new Map(prd.issues.map(i => [i.n, i]))
          // o tempo da Onda conta também os sub-agentes de sessão que já acabou
          const vivosIds = new Set(ags.map(a => a.id))
          const comHistorico = [...ags, ...(c.historico ?? []).filter(a => !vivosIds.has(a.id))]
          const desenhadas = ondas.map(o => {
            const issues = o.issues.map(n => porN.get(n)).filter((i): i is Issue => !!i)
            return { o, issues, situacao: situacaoDaOnda(issues, ags, prd, c.em), tempo: duracaoDaOnda(issues, comHistorico, prd, c.em) }
          })
          // a Onda que roda mostra todas as Fatias dela; fora dela, a Fatia no ar vai para a linha "no ar"
          const naCaixa = new Set(desenhadas.filter(d => d.situacao === 'andando').flatMap(d => d.o.issues))
          const emOnda = new Set(ondas.flatMap(o => o.issues))
          const entregues = prd.issues.filter(i => noAr(i) && !naCaixa.has(i.n))
          const soltas = prd.issues.filter(i => !emOnda.has(i.n) && !noAr(i))
          const semAlvo = ags.filter(a => alvo(a, prd) === null)

          return (
            <Box key={`prd${prd.n}`} flexDirection="column" marginTop={1}>
              <Text wrap="truncate-end">
                <Text bold>{prd.n === SEM_PRD ? 'Sem PRD' : `PRD #${prd.n}`}</Text>{' '}
                <Text dimColor>
                  {prontasDoPrd(prd)}/{prd.issues.length} prontas
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
                    {comDetalhe && s.fala && (
                      <Text dimColor wrap="truncate-end">
                        {'    '}💬 {curto(s.fala.texto.split('\n')[0] ?? '', largura - 22)} · há {minutos(c.em - s.fala.em)}
                      </Text>
                    )}
                    {comDetalhe &&
                      focoDaSessao(s.nome, ags, c.em).map(a =>
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

              {desenhadas.map(({ o, issues, situacao, tempo }) => {
                const passagem =
                  situacao === 'feita' || o.sessao ? '' : o.passagem === 'nao' ? ' · passagem: ainda não' : o.passagem === 'escrita' ? ' · passagem escrita' : ''
                const cabecalho = (
                  <Text key="cab" bold color={COR_ONDA[situacao]} wrap="truncate-end">
                    Onda {o.numero}{' '}
                    {o.sessao ? <Text color="suggestion">· {o.sessao.nome} </Text> : null}
                    <Text dimColor>
                      · {NOME_ONDA[situacao]}
                      {tempo !== null ? ` · ${minutos(tempo)}` : ''}
                      {passagem}
                    </Text>
                  </Text>
                )
                // só a Onda que roda ganha a caixa; as outras são um título e as Fatias que faltam
                if (situacao !== 'andando') {
                  const espera = esperaDeFora(issues, o.issues, porN)
                  return (
                    <Box key={`o${o.numero}`} flexDirection="column">
                      {cabecalho}
                      {issues.filter(i => !noAr(i)).map(i => linhaFatia(i, false, '  '))}
                      {espera && (
                        <Text key="espera" color="subtle" wrap="truncate-end">
                          {'  '}
                          {espera}
                        </Text>
                      )}
                    </Box>
                  )
                }
                return (
                  <Box key={`o${o.numero}`} flexDirection="column" borderStyle="round" borderColor={COR_ONDA[situacao]} paddingX={1}>
                    {cabecalho}
                    {issues.map(i => {
                      const dela = ags.filter(a => alvo(a, prd) === i.n)
                      const lista = etapasDa(i, prd, ags, sessoes.find(s => dela.some(a => a.sessao === s.nome))?.nome)
                      return (
                        <Box key={`i${i.n}`} flexDirection="column">
                          {linhaComTempos(i, lista, '')}
                          {i.fase === 'bloqueada' || i.fase === 'fila' || i.fase === 'humana' ? (
                            <Text dimColor wrap="truncate-end">
                              {'    '}
                              {detalhe(i)}
                            </Text>
                          ) : (
                            passos(i, lista)
                          )}
                          {comDetalhe && dela.map(a => linhaAgente(a))}
                        </Box>
                      )
                    })}
                  </Box>
                )
              })}

              {soltas.map(i => linhaFatia(i, true, ''))}
              {entregues.length > 0 && (
                <Box flexDirection="column">
                  <Text color="success">✓ {entregues.length} no ar</Text>
                  {entregues.map(i => linhaComTempos(i, etapasDa(i, prd, ags), '  '))}
                </Box>
              )}
              {comDetalhe && semAlvo.length > 0 && (
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
