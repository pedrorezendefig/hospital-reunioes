import { expect, test } from 'claude-code/testing'

import { acaoDe, acaoDoPrd, arvore, marcaDaFase, prontas } from '../hooks/register'
import type { Fatia, Item, Visao } from '../types'

const item = (n: number, fase: string, x: Partial<Item> = {}): Item => ({
  n, titulo: `issue ${n}`, fase, selos: [], quem: [], fechada: false, ...x,
})
const fatia = (n: number, fase: string, travadaPor: number[] = [], x: Partial<Item> = {}): Fatia => ({
  ...item(n, fase, x), travadaPor,
})

// recorte da visão real de 07/11/2026 (PRD #1415 e a aba Tecnologia)
const VISAO: Visao = {
  login: 'pedrorezendefig',
  repo: 'pedrorezendefig/hospital-reunioes',
  agora: '2026-11-07T15:00:00+00:00',
  semaforo: { cor: 'verde', detalhe: 'Actions operational' },
  abertas: 11,
  caminho: {
    triagem: [item(1427, 'triagem', { selos: ['Diretor'] })],
    fila: [item(1471, 'fila de agente', { selos: ['Diretor'] }), item(1416, 'fila de agente')],
    humana: [item(1453, 'humana', { selos: ['Humana'] })],
    andamento: [],
    pr: [],
    entregue: [item(1458, 'entregue 06/11', { fechada: true })],
  },
  prds: [{
    n: 1415,
    titulo: 'PRD: Contas médicas, acompanhar o processamento',
    fatias: [fatia(1416, 'fila de agente'), fatia(1417, 'fila de agente', [1416]), fatia(1418, 'fila de agente', [1416])],
  }],
  tecnologia: {
    bug: [item(1471, 'fila de agente', { selos: ['Diretor'] }), item(1430, 'entregue 06/11', { selos: ['Diretor'], quem: ['pedrorezendefig'], fechada: true })],
    melhoria: [item(1053, 'humana', { selos: ['Humana', 'Diretor'], quem: ['pedroribbe'] })],
  },
  janelaDias: 14,
  plano: ['1. Tarefa humana #1453:', '   - tarefa sua: Gerar de novo a ata'],
}

const PANE = {
  plugin: 'hr-issues',
  component: 'Pane',
  requestId: 'issues',
  props: {
    title: 'Issues',
    isFocused: false,
    bodyColumns: 78,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 60 },
    view: {},
  },
} as const

test('a fatia travada fica embaixo da que trava; a livre fica na raiz', () => {
  const linhas = arvore(VISAO.prds[0]!)
  expect(linhas.map(l => [l.fatia.n, l.nivel, l.travada])).toEqual([
    [1416, 0, false],
    [1417, 1, true],
    [1418, 1, true],
  ])
})

test('bloqueio fora do PRD sobe para a raiz, e um ciclo não some com ninguém', () => {
  const fora = arvore({ n: 1, titulo: 'x', fatias: [fatia(2, 'fila de agente', [99])] })
  expect(fora.map(l => [l.fatia.n, l.nivel])).toEqual([[2, 0]])
  const ciclo = arvore({ n: 1, titulo: 'x', fatias: [fatia(2, 'fila de agente', [3]), fatia(3, 'fila de agente', [2])] })
  expect(ciclo.map(l => l.fatia.n).sort()).toEqual([2, 3])
})

test('a marca segue a fase que o script escreveu', () => {
  expect(marcaDaFase('humana').marca).toBe('!')
  expect(marcaDaFase('PR #90').marca).toBe('◆')
  expect(marcaDaFase('entregue 06/11').marca).toBe('✓')
  expect(marcaDaFase('fila de agente', true).marca).toBe('×')
  expect(prontas({ n: 1, titulo: 'x', fatias: [fatia(2, 'entregue 06/11', [], { fechada: true }), fatia(3, 'triagem')] })).toBe(1)
})

test('o painel desenha o caminho, a árvore, os selos e a Tecnologia', async ($, on) => {
  on('state.get', (_, e) => ({
    value: e.key === 'visao' ? { value: VISAO, version: 1 } : { value: undefined, version: 0 },
  }))
  on('clock.now', () => ({ value: Date.parse(VISAO.agora) }))

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const texto = async (re: RegExp) => (await ui.find({ type: 'Text', text: re }))?.text ?? ''
  const linha = async (key: string) => (await ui.find({ type: 'Box', key }))?.text ?? ''

  expect(await linha('chumana')).toMatch(/Humana\s+1\s*#1453 Humana/)
  expect(await linha('ctriagem')).toContain('#1427 Diretor')
  // fila inteira, sem corte, e sem URL nenhuma no painel
  expect(await linha('cfila')).toMatch(/#1471.*#1416/)
  expect(await ui.findAll({ type: 'Link' })).toHaveLength(0)
  expect(await linha('i61417')).toContain('└ ')
  expect(await linha('i61417')).toContain('travada')
  expect(await linha('i31053')).toContain('pedroribbe')
  expect(await linha('i31053')).toContain('Humana')
  expect(await linha('i31053')).not.toContain('Diretor')
  expect(await texto(/Tarefa humana/)).toContain('#1453')
  await ui.unmount()
})

test('o clique decide: fila de PRD com várias fatias monta a onda do PRD, sozinha a da issue', () => {
  const [triagem, fila1471, fila1416] = [VISAO.caminho.triagem[0]!, VISAO.caminho.fila[0]!, VISAO.caminho.fila[1]!]
  expect(acaoDe(fila1416, VISAO)).toEqual({ tipo: 'prd', n: 1415 })
  expect(acaoDe(fila1471, VISAO)).toEqual({ tipo: 'issue', n: 1471 })
  expect(acaoDe(VISAO.caminho.humana[0]!, VISAO)).toEqual({ tipo: 'humana', n: 1453 })
  expect(acaoDe(triagem, VISAO)).toEqual({ tipo: 'triagem', n: 1427 })
  expect(acaoDe(VISAO.caminho.entregue[0]!, VISAO)).toEqual({ abrir: 1458 })
  expect(acaoDe(item(9, 'PR #90'), VISAO)).toEqual({ abrir: 9 })
  expect(acaoDoPrd(VISAO.prds[0]!, VISAO)).toEqual({ tipo: 'prd', n: 1415 })
  // PRD com uma fatia só aberta: a onda é a da issue, não a do PRD
  const umaSo = { n: 7, titulo: 'x', fatias: [fatia(8, 'entregue 06/11', [], { fechada: true }), fatia(9, 'fila de agente')] }
  const v = { ...VISAO, prds: [umaSo] }
  expect(acaoDoPrd(umaSo, v)).toEqual({ tipo: 'issue', n: 9 })
  expect(acaoDe(umaSo.fatias[1]!, v)).toEqual({ tipo: 'issue', n: 9 })
  expect(acaoDoPrd({ n: 7, titulo: 'x', fatias: [umaSo.fatias[0]!] }, v)).toEqual({ abrir: 7 })
})

test('clicar num número da fila abre a sessão da onda uma vez só; entregue abre no GitHub', async ($, on) => {
  on('state.get', (_, e, next) => (e.key === 'visao' ? { value: { value: VISAO, version: 1 } } : next(e)))
  on('clock.now', () => ({ value: Date.parse(VISAO.agora) }))
  const chamadas: string[][] = []
  on('process.run', (_, e) => {
    chamadas.push([...e.argv])
    return { value: { exitCode: 0, stdout: 'backgrounded · a1b2 · onda-prd-1415\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.notify', () => ({ value: { isSent: true, channel: 'terminal_bell' } }))

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'cfila#1416' })
  expect(chamadas).toHaveLength(1)
  expect(chamadas[0]!.slice(1).map(a => a.replace(/.*\/hooks\//, ''))).toEqual(['lancar.sh', 'prd', '1415'])
  expect((await ui.find({ type: 'Text', text: /onda-prd-1415/ }))?.text).toContain('a1b2')

  // a outra fatia do mesmo PRD é a mesma onda: não abre segunda sessão
  await ui.press({ key: 'i2#1416' })
  expect(chamadas).toHaveLength(1)

  await ui.press({ key: 'centregue#1458' })
  expect(chamadas[1]).toEqual(['open', 'https://github.com/pedrorezendefig/hospital-reunioes/issues/1458'])
  await ui.unmount()
})

test('sem visão ainda, o painel diz que está coletando', async ($, on) => {
  on('state.get', () => ({ value: { value: undefined, version: 0 } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toMatch(/Coletando/)
  await ui.unmount()
})
