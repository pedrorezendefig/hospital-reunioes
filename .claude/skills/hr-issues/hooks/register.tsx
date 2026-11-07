import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Caixa, Fatia, Item, Prd, Visao } from '../types'

// Aba "Issues", ao lado da "Ondas" do hr-ondas: a tela visual do /minhas-issues num painel.
// Só leitura. Quem calcula é o minhas_issues.py --json (via hooks/coletar.sh, com cache
// compartilhado de 5 min); o painel só desenha. Recoleta a cada minuto (o cache segura o
// GitHub) e logo depois de um gh que muda issue ou PR nesta sessão.

const PANE = 'issues'
const TITULO = 'Issues'
const PERIODO_MS = 60_000
const EVENTO_NO_SHELL = /fechar_onda\.py\s+--prs|gh\s+pr\s+(create|merge|ready|close)|gh\s+issue\s+(create|close|edit|reopen)/
const MAX_NUMEROS = 8

const visao = atom({ plugin: 'hr-issues', key: 'visao' } as const, null)
const erro = atom({ plugin: 'hr-issues', key: 'erro' } as const, null)
const em = atom({ plugin: 'hr-issues', key: 'em' } as const, null)

export const CAIXAS: { id: Caixa; nome: string; marca: string; cor: string }[] = [
  { id: 'triagem', nome: 'Triagem', marca: '?', cor: 'inactive' },
  { id: 'fila', nome: 'Fila de agente', marca: '·', cor: 'suggestion' },
  { id: 'humana', nome: 'Humana', marca: '!', cor: 'warning' },
  { id: 'andamento', nome: 'Em andamento', marca: '▸', cor: 'suggestion' },
  { id: 'pr', nome: 'PR aberto', marca: '◆', cor: 'permission' },
  { id: 'entregue', nome: 'Entregue', marca: '✓', cor: 'success' },
]

const COR_SEMAFORO = { verde: 'success', amarelo: 'warning', vermelho: 'error' } as const
const COR_SELO: Record<string, string> = { Humana: 'warning', Diretor: 'permission' }

/** Marca e cor de uma fase escrita pelo script. Fatia com bloqueio aberto vira "travada". */
export const marcaDaFase = (fase: string, travada = false): { marca: string; cor: string } => {
  if (travada) return { marca: '×', cor: 'subtle' }
  if (fase.startsWith('entregue')) return { marca: '✓', cor: 'success' }
  if (fase.startsWith('PR')) return { marca: '◆', cor: 'permission' }
  if (fase === 'não vai ser feita') return { marca: '✗', cor: 'subtle' }
  const caixa = { triagem: 'triagem', 'fila de agente': 'fila', humana: 'humana', 'em andamento': 'andamento' }[fase]
  const c = CAIXAS.find(x => x.id === caixa)
  return c ? { marca: c.marca, cor: c.cor } : { marca: '·', cor: 'inactive' }
}

export const curto = (texto: string, max: number) =>
  max < 2 ? '' : texto.length > max ? `${texto.slice(0, max - 1)}…` : texto

export const minutos = (ms: number) => {
  const m = Math.max(0, Math.round(ms / 60_000))
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
}

/**
 * A árvore de um PRD em linhas: a fatia livre na raiz e, embaixo dela, as que ela trava.
 * Uma fatia travada por outra fora do PRD (ou já fechada) sobe para a raiz.
 */
export const arvore = (prd: Prd): { fatia: Fatia; nivel: number; travada: boolean }[] => {
  const porN = new Map(prd.fatias.map(f => [f.n, f]))
  const pai = (f: Fatia) => f.travadaPor.find(b => porN.has(b) && b !== f.n)
  const filhos = new Map<number, Fatia[]>()
  for (const f of prd.fatias) {
    const p = pai(f)
    if (p !== undefined) filhos.set(p, [...(filhos.get(p) ?? []), f])
  }
  const saida: { fatia: Fatia; nivel: number; travada: boolean }[] = []
  const vistas = new Set<number>()
  const andar = (f: Fatia, nivel: number) => {
    if (vistas.has(f.n)) return
    vistas.add(f.n)
    saida.push({ fatia: f, nivel, travada: f.travadaPor.length > 0 })
    for (const filho of filhos.get(f.n) ?? []) andar(filho, nivel + 1)
  }
  for (const f of prd.fatias) if (pai(f) === undefined) andar(f, 0)
  for (const f of prd.fatias) andar(f, 0) // ciclo de bloqueio: ninguém some
  return saida
}

export const prontas = (prd: Prd) => prd.fatias.filter(f => f.fechada || f.fase.startsWith('entregue')).length

let rodando = false
let frescoPendente = false

async function coletar($: EngineInterface, fresco = false) {
  if (rodando) {
    frescoPendente ||= fresco
    return
  }
  rodando = true
  try {
    const r = await $.process.run(['/bin/bash', `${$.plugin.root}/hooks/coletar.sh`, ...(fresco ? ['--fresco'] : [])], {
      timeoutMs: 180_000,
    })
    if (r.exitCode === 3) return // outra sessão coletando e sem cache ainda: o próximo minuto pega
    if (r.exitCode !== 0) throw new Error(r.stderr.trim().split('\n').pop()?.slice(0, 200) || `saída ${r.exitCode}`)
    const v = JSON.parse(r.stdout) as Visao
    await update($, visao, () => v)
    await update($, em, () => Date.parse(v.agora))
    await update($, erro, () => null)
    const humanas = v.caminho.humana.length
    $.ui.status(humanas ? `issues: ${humanas} humana(s) esperando você` : undefined)
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
      name: 'issues',
      description: 'Aba Issues: caminho das minhas issues, árvore dos PRDs, selos Humana e Diretor e o que chegou da Tecnologia',
    })
    if (e.isInteractive) void $.ui.open({ id: PANE, title: TITULO, columns: 78 })
    void coletar($)
    $.clock.every(PERIODO_MS, () => coletar($))
    return next(e)
  })

  on('command.run', { command: 'issues' }, async $ => {
    await $.ui.open({ id: PANE, title: TITULO, columns: 78 })
    await coletar($, true)
    return { text: 'Aba Issues atualizada.' }
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!EVENTO_NO_SHELL.test(e.command)) return next(e)
    try {
      return await next(e)
    } finally {
      void coletar($, true)
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link } = $.ui.resolve(e)
    const v = await read($, visao)
    const falha = await read($, erro)
    const quando = await read($, em)
    const largura = Math.max(30, (e.props.bodyColumns ?? (e.viewport?.columns ?? 100) - 4) - 2)

    if (!v) {
      return (
        <Box flexDirection="column">
          <Text dimColor>{falha ?? 'Coletando as issues (uns 10 s)…'}</Text>
        </Box>
      )
    }

    const repo = v.repo ?? 'pedrorezendefig/hospital-reunioes'
    const link = (n: number) => <Link href={`https://github.com/${repo}/issues/${n}`} label={`#${n}`} />
    const selos = (i: Item) =>
      i.selos.map(s => (
        <Text key={`s${i.n}${s}`} color={COR_SELO[s]} bold>
          {' '}
          {s}
        </Text>
      ))

    const linhaItem = (i: Item, recuo: string, travada = false, mostrarQuem = false) => {
      const { marca, cor } = marcaDaFase(i.fase, travada)
      const quem = mostrarQuem ? ` · ${i.quem.join(', ') || 'sem responsável'}` : ''
      const meta = `${travada ? 'travada' : i.fase}${quem}`
      const resto = largura - recuo.length - String(i.n).length - meta.length - 8 - i.selos.join(' ').length
      return (
        <Text key={`i${recuo.length}${i.n}`} wrap="truncate-end">
          {recuo}
          <Text color={cor}>{marca} </Text>
          {link(i.n)}
          {selos(i)}
          <Text color={cor}> {meta}</Text>
          <Text dimColor> {curto(i.titulo, resto)}</Text>
        </Text>
      )
    }

    const tec = v.tecnologia
    const agora = await $.clock.now()

    return (
      <Box flexDirection="column">
        <Text wrap="truncate-end">
          <Text bold>{v.login}</Text>
          <Text dimColor> · {v.abertas} abertas · </Text>
          <Text color={COR_SEMAFORO[v.semaforo.cor]}>Actions {v.semaforo.cor}</Text>
          <Text dimColor> · há {minutos(agora - (quando ?? agora))}</Text>
        </Text>
        {falha && <Text color="error">{falha}</Text>}

        <Box flexDirection="column" marginTop={1}>
          <Text bold>Caminho</Text>
          {CAIXAS.map(c => {
            const its = v.caminho[c.id]
            const nome = c.id === 'entregue' ? `${c.nome} ${v.janelaDias}d` : c.nome
            return (
              <Text key={`c${c.id}`} wrap="truncate-end">
                <Text color={its.length ? c.cor : 'inactive'} bold={its.length > 0}>
                  {' '}
                  {c.marca} {nome.padEnd(16)} {String(its.length).padStart(3)}
                </Text>
                {its.slice(0, MAX_NUMEROS).map(i => (
                  <Text key={`n${c.id}${i.n}`}>
                    {'  '}
                    {link(i.n)}
                    {selos(i)}
                  </Text>
                ))}
                {its.length > MAX_NUMEROS && <Text dimColor> +{its.length - MAX_NUMEROS}</Text>}
              </Text>
            )
          })}
          <Text dimColor> ? triagem → · fila → ▸ andamento → ◆ PR → ✓ entregue · ! humana sai da triagem</Text>
        </Box>

        {v.prds.map(prd => (
          <Box key={`prd${prd.n}`} flexDirection="column" marginTop={1}>
            <Text wrap="truncate-end">
              <Text bold>
                <Link href={`https://github.com/${repo}/issues/${prd.n}`} label={`PRD #${prd.n}`} />
              </Text>
              <Text dimColor>
                {' '}
                {prontas(prd)}/{prd.fatias.length} prontas · {curto(prd.titulo.replace(/^PRD: /, ''), largura - 24)}
              </Text>
            </Text>
            {arvore(prd).map(({ fatia, nivel, travada }) =>
              linhaItem(fatia, `${'  '.repeat(nivel + 1)}${nivel ? '└ ' : ''}`, travada),
            )}
          </Box>
        ))}

        <Box flexDirection="column" marginTop={1}>
          <Text bold>
            Chegou da Tecnologia <Text dimColor>· pedidos do diretor, abertos e fechados em {v.janelaDias} dias</Text>
          </Text>
          {tec.bug.length + tec.melhoria.length === 0 && <Text dimColor> nada nessa janela</Text>}
          {(['bug', 'melhoria'] as const).map(tipo =>
            tec[tipo].length ? (
              <Box key={tipo} flexDirection="column">
                <Text color="permission">
                  {' '}
                  {tipo === 'bug' ? 'Bug' : 'Melhoria'} ({tec[tipo].length})
                </Text>
                {tec[tipo].map(i => linhaItem({ ...i, selos: i.selos.filter(s => s !== 'Diretor') }, '   ', false, true))}
              </Box>
            ) : null,
          )}
        </Box>

        {v.plano.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Plano</Text>
            {v.plano.map((l, k) => (
              <Text key={`p${k}`} dimColor={!/^\d\./.test(l)} wrap="truncate-end">
                {' '}
                {l.replace(/`/g, '')}
              </Text>
            ))}
          </Box>
        )}
        <Text dimColor>/issues atualiza agora · /minhas-issues traz o passo a passo das humanas</Text>
      </Box>
    )
  })
}
