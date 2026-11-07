import { expect, test } from 'claude-code/testing'

import { arvore, marcaDaFase, prontas } from '../hooks/register'
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

  expect(await texto(/Humana\s+1/)).toContain('#1453 Humana')
  expect(await texto(/Triagem/)).toContain('#1427 Diretor')
  expect(await texto(/#1417/)).toContain('└ ')
  expect(await texto(/#1417/)).toContain('travada')
  expect(await texto(/#1053/)).toContain('pedroribbe')
  expect(await texto(/#1053/)).toContain('Humana')
  expect(await texto(/#1053/)).not.toContain('Diretor')
  expect(await texto(/Tarefa humana/)).toContain('#1453')
  await ui.unmount()
})

test('sem visão ainda, o painel diz que está coletando', async ($, on) => {
  on('state.get', () => ({ value: { value: undefined, version: 0 } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toMatch(/Coletando/)
  await ui.unmount()
})
