import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Agente, Coleta, EsperaCi, Fase, Issue, Migration, Prd, SubAgente } from '../types'

// Torre das ondas: só leitura. A coleta (hooks/coletar.sh) junta o Hospital OS,
// o `claude agents`, as migrations que a subida pediu e o /api/health.

const PANE = 'ondas'
const STUDIO = 'https://studio.hospitalsaomatheus.cloud/project/default/sql/new'
const PERIODO_MS = 20_000
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
  encerrada_sem_pr: '-',
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

export const sessoesDoPrd = (c: Coleta, prd: number): Agente[] =>
  c.agentes.filter(a => c.prdSessoes[a.nome] === prd)

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

export const duracao = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60))
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm.padStart(2, '0')}:${ss}` : `${mm}:${ss}`
}

export const agentesDoPrd = (c: Coleta, prd: Prd): SubAgente[] =>
  (c.subAgentes ?? []).filter(a => c.prdSessoes[a.sessao] === prd.n).sort((x, y) => x.inicio - y.inicio)

/** A fatia de um sub-agente pela descrição: "PR 1166" vai à issue do PR, "#1139" à issue. */
export const alvo = (a: SubAgente, prd: Prd): number | null => {
  const pr = /PR\s*#?(\d+)/i.exec(a.descricao)
  if (pr) return prd.issues.find(i => i.pr === Number(pr[1]))?.n ?? null
  const n = Number(/#(\d+)/.exec(a.descricao)?.[1])
  return prd.issues.some(i => i.n === n) ? n : null
}

type EstadoEtapa = 'feita' | 'agora' | 'falhou' | 'falta'
const COR_ETAPA: Record<EstadoEtapa, string> = { feita: 'success', agora: 'suggestion', falhou: 'error', falta: 'inactive' }
const MARCA_ETAPA: Record<EstadoEtapa, string> = { feita: ' ✓', agora: ' ●', falhou: ' ✗', falta: '' }

/** Esteira da fatia: implementar → CI → revisar → (corrigir) → subida → no ar. */
export const etapas = (i: Issue, ags: SubAgente[], agora: number) => {
  const de = (tipo: string) => ags.filter(a => a.tipo === tipo)
  const estado = (tipo: string, feita: boolean): EstadoEtapa => {
    const lista = de(tipo)
    if (lista.some(a => estadoDoAgente(a, agora) === 'trabalhando')) return 'agora'
    return feita || (lista.length > 0 && lista.every(a => a.terminou)) ? 'feita' : 'falta'
  }
  const depoisDoPr = ['pr_aberto', 'mergeada', 'em_producao'].includes(i.fase)
  const subiu = ['mergeada', 'em_producao'].includes(i.fase)
  const lista: { nome: string; estado: EstadoEtapa }[] = [
    { nome: 'implementar', estado: estado('hr-implementador', depoisDoPr) },
    {
      nome: 'CI',
      estado: subiu || i.ci === 'verde' ? 'feita' : i.ci === 'vermelho' ? 'falhou' : i.pr ? 'agora' : 'falta',
    },
    { nome: 'revisar', estado: estado('hr-revisor', subiu || !!i.veredito) },
  ]
  if (de('hr-corretor').length) lista.push({ nome: 'corrigir', estado: estado('hr-corretor', subiu) })
  lista.push({ nome: 'subida', estado: i.fase === 'em_producao' ? 'feita' : i.fase === 'mergeada' ? 'agora' : 'falta' })
  lista.push({ nome: 'no ar', estado: i.fase === 'em_producao' ? 'feita' : 'falta' })
  return lista
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

/** Onda que não anda cabe em uma ou duas linhas: as fatias e o que ela espera de fora. */
export const resumoDaOnda = (issues: Issue[], onda: number[]) => {
  const linhas = [{ texto: issues.map(i => `${MARCA[i.fase]} #${i.n}`).join('  '), cor: 'inactive' }]
  const fora = [...new Set(issues.flatMap(i => i.por))].filter(n => !onda.includes(n)).sort((a, b) => a - b)
  if (fora.length) linhas.push({ texto: `espera ${fora.map(n => `#${n}`).join(' ')}`, cor: 'subtle' })
  return linhas
}

let rodando = false
const sessoesVistas = new Set<string>()
const migrationsAvisadas = new Set<number>()

async function coletar($: EngineInterface) {
  if (rodando) return
  rodando = true
  try {
    const r = await $.process.run(['/bin/bash', `${$.plugin.root}/hooks/coletar.sh`], {
      timeoutMs: 90_000,
    })
    if (r.exitCode !== 0) throw new Error(r.stderr.slice(0, 200) || `saída ${r.exitCode}`)
    const c: Coleta = { ...JSON.parse(r.stdout), em: await $.clock.now() }
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
    if (arg === 'todos' || arg === 'ativos') await update($, todos, () => arg === 'todos')
    await $.ui.open({ id: PANE, title: 'Ondas', columns: 78 })
    await coletar($)
    return { text: `Painel das ondas atualizado${arg === 'todos' ? ', com todos os PRDs' : ''}.` }
  })

  // CI em espera na própria sessão: o --watch segura a chamada até o fim
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const cmd = e.command
    const assistindo = /gh\s+run\s+watch|gh\s+pr\s+checks\b[^|;&]*--watch/.test(cmd)
    if (!assistindo) return next(e)
    const pr = Number(/gh\s+pr\s+checks\s+(\d+)/.exec(cmd)?.[1]) || null
    const repo = (await read($, coleta))?.os?.repo ?? 'pedrorezendefig/hospital-reunioes'
    const url = pr ? `https://github.com/${repo}/pull/${pr}/checks` : `https://github.com/${repo}/actions`
    await update($, esperaCi, () => ({ pr, url }) satisfies EsperaCi)
    try {
      return await next(e)
    } finally {
      await update($, esperaCi, () => null)
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

    const linhaAgente = (a: SubAgente) => {
      const estado = estadoDoAgente(a, c.em)
      const pct = Math.round((a.ctx / JANELA) * 100)
      const cheio = Math.min(10, Math.round(pct / 10))
      return (
        <Text key={`a${a.id}`} wrap="truncate-end">
          {'    '}
          <Text color={COR_AGENTE[estado]}>{MARCA_AGENTE[estado]} </Text>
          <Text bold>{a.tipo}</Text>
          <Text dimColor>
            {' '}
            {[nomeModelo(a.modelo), a.esforco].filter(Boolean).join(' · ')}{' '}
          </Text>
          <Text color={COR_AGENTE[estado]}>{'▰'.repeat(cheio)}</Text>
          <Text dimColor>
            {'▱'.repeat(10 - cheio)} ctx {pct}% · {Math.round(a.ctx / 1000)}k · {duracao((estado === 'trabalhando' ? c.em : a.fim) - a.inicio)}
          </Text>
        </Text>
      )
    }

    const passos = (i: Issue, ags: SubAgente[]) => (
      <Text key={`s${i.n}`} wrap="truncate-end">
        {'    '}
        {etapas(i, ags, c.em).map((s, k) => (
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

    return (
      <Box flexDirection="column">
        <Text dimColor>
          atualizado há {Math.round(((await $.clock.now()) - c.em) / 1000)} s ·{' '}
          {mostrarTodos ? 'todos os PRDs (/ondas ativos)' : 'PRDs ativos (/ondas todos)'}
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
          const emOnda = new Set(prd.ondas.flat())
          const porN = new Map(prd.issues.map(i => [i.n, i]))
          const fora = prd.issues.filter(i => !emOnda.has(i.n))
          const entregues = fora.filter(i => i.fase === 'em_producao' || i.estado === 'CLOSED')
          const soltas = fora.filter(i => !entregues.includes(i))
          const feitas = prd.issues.filter(i => i.fase === 'em_producao').length
          const semAlvo = ags.filter(a => alvo(a, prd) === null)

          return (
            <Box key={`prd${prd.n}`} flexDirection="column" marginTop={1}>
              <Text wrap="truncate-end">
                <Text bold>
                  <Link href={`https://github.com/${repo}/issues/${prd.n}`} label={`PRD #${prd.n}`} />
                </Text>{' '}
                <Text dimColor>
                  {feitas}/{prd.issues.length} no ar
                </Text>
              </Text>
              <Text dimColor wrap="truncate-end">
                {curto(prd.titulo.replace(/^PRD: /, ''), largura)}
              </Text>
              {sessoes.map(s => {
                const daSessao = ags.filter(a => a.sessao === s.nome)
                const vivos = daSessao.filter(a => estadoDoAgente(a, c.em) === 'trabalhando').length
                return (
                  <Text key={s.nome} wrap="truncate-end">
                    <Text color={s.status === 'busy' ? 'suggestion' : 'inactive'}>
                      {s.status === 'busy' ? '●' : '○'} {s.nome}
                    </Text>
                    <Text dimColor>
                      {' '}
                      · {vivos} trabalhando · {daSessao.length - vivos} terminado(s)
                    </Text>
                  </Text>
                )
              })}

              {prd.ondas.map((onda, k) => {
                const issues = onda.map(n => porN.get(n)).filter((i): i is Issue => !!i)
                const situacao = situacaoDaOnda(issues, ags, prd, c.em)
                return (
                  <Box key={`o${k}`} flexDirection="column">
                    {k > 0 && <Text color={COR_ONDA[situacao]}>{'      ▼'}</Text>}
                    <Box flexDirection="column" borderStyle="round" borderColor={COR_ONDA[situacao]} paddingX={1}>
                      <Text bold color={COR_ONDA[situacao]}>
                        Onda {k + 1} <Text dimColor>· {NOME_ONDA[situacao]}</Text>
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
                                  passos(i, dela)
                                )}
                                {dela.map(linhaAgente)}
                              </Box>
                            )
                          })
                        : resumoDaOnda(issues, onda).map((r, j) => (
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
                  {semAlvo.map(linhaAgente)}
                </Box>
              )}
            </Box>
          )
        })}
      </Box>
    )
  })
}
