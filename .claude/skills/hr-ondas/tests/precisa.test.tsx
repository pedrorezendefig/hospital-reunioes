import { expect, mock, test } from 'claude-code/testing'

import { cardsDaOnda, cardsSemTitulo, precisaDeVoce } from '../hooks/register'
import type { Coleta } from '../types'

// "Precisa de você": cada Onda que espera traz o motivo por extenso e os cards que ele cita.
// Recorte real de 13/11/2026 (~/.pedroos/ondas/hospital).

const AGORA = 1_800_000_000_000
const REPO = 'pedrorezendefig/hospital-reunioes'
const issue = (n: number, titulo: string, fase = 'em_andamento', estado = 'OPEN') => ({
  n, titulo, estado, url: '', fase, pr: null, ci: null, veredito: null, conflito: false, versao: null, por: [],
})
const COLETA = {
  os: {
    repo: REPO,
    prds: [{ n: 1571, titulo: 'Reuniões e Ouvidoria consultadas pelo Claude', ondas: [], issues: [
      issue(1614, 'Aceite do diretor: Conector no celular e no computador bate com as telas', 'humana'),
    ] }],
  },
  agentes: [], prdSessoes: {}, migrations: [], aplicada: 141, em: AGORA,
  ondasEstado: [
    { id: 'hsm-conector-onda3', estado: 'pronto-para-voce', prd: 1632, baixas: [],
      texto: 'PRD #1632 em produção, mensagem para o diretor pronta no comentário do PRD; a passada nas Demandas antigas ficou com você na #1673' },
    { id: 'hsm-conector-onda4', estado: 'pronto-para-voce', prd: 1571, baixas: [],
      texto: 'fila vazia, 1 issue com você: #1614 (aceite do diretor)' },
    { id: 'hsm-x-onda1', estado: 'erro', prd: null, baixas: [1700], texto: 'rollback da subida' },
  ],
} as unknown as Coleta
const CITADOS = {
  1632: { titulo: 'PRD: card do diretor com explicação para o desenvolvedor e email ao Responsável', aberto: false, em: AGORA },
  1673: { titulo: 'Tecnologia: rodar em produção a passada do bloco Para o desenvolvedor', aberto: true, em: AGORA },
}

test('a Onda cita os cards do motivo e as baixas, sem repetir o PRD', () => {
  const [o3, o4, ox] = COLETA.ondasEstado!
  expect(cardsDaOnda(o3!)).toEqual([1673])
  expect(cardsDaOnda(o4!)).toEqual([1614])
  expect(cardsDaOnda(ox!)).toEqual([1700])
  // o OS já traz o PRD 1571 e a #1614; o resto o mod busca no GitHub
  expect(cardsSemTitulo(COLETA).sort()).toEqual([1632, 1673, 1700])
})

test('cada Onda traz o motivo inteiro e cada card com título; a Fatia citada não se repete', () => {
  const lista = precisaDeVoce(COLETA, CITADOS)
  expect(lista.map(x => `${x.rotulo} ${x.texto}`)).toEqual([
    'Onda hsm-x-onda1 quebrou',
    'Onda hsm-conector-onda3 espera você',
    'Onda hsm-conector-onda4 espera você',
  ])
  const o3 = lista[1]!
  expect(o3.detalhe).toBe(COLETA.ondasEstado![0]!.texto)
  expect(o3.cards).toEqual([
    { n: 1632, texto: `PRD #1632 · ${CITADOS[1632].titulo}`, feito: true },
    { n: 1673, texto: `#1673 · ${CITADOS[1673].titulo}`, feito: false },
  ])
  expect(lista[2]!.cards!.map(k => k.texto)).toEqual([
    'PRD #1571 · Reuniões e Ouvidoria consultadas pelo Claude',
    '#1614 é sua · Aceite do diretor: Conector no celular e no computador bate com as telas',
  ])
  // sem título buscado ainda: o card aparece só com o número
  expect(precisaDeVoce(COLETA)[1]!.cards!.map(k => k.texto)).toEqual(['PRD #1632', '#1673'])
  // a #1614 humana já está na Onda: não vira linha solta
  expect(lista.some(x => x.rotulo === '#1614')).toBe(false)
})

test('painel: motivo inteiro, cards sem link, fechado marcado, e o botão resolver em cada Onda', async ($, on) => {
  const gh: number[] = []
  mock.clock(on, { now: AGORA })
  on('process.run', (_$: any, e: any) => {
    const argv = [...e.argv] as string[]
    if (argv[0] === 'gh') {
      const n = Number(/issues\/(\d+)/.exec(argv[2]!)![1])
      gh.push(n)
      const c = (CITADOS as Record<number, { titulo: string; aberto: boolean }>)[n]
      return { value: { exitCode: c ? 0 : 1, stdout: c ? `${c.aberto ? 'open' : 'closed'}\t${c.titulo}\n` : '', stderr: '' } } as any
    }
    return { value: { exitCode: 0, stdout: JSON.stringify(COLETA), stderr: '' } } as any
  })
  on('command.register', () => ({ value: undefined }) as any)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', (_$: any, e: any, next: any) => (e.component === 'Pane' ? null : next(e)))
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' } as any)
  // o título dos cards que o OS não traz vem do GitHub, uma vez
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' } as any)
  expect(gh.sort()).toEqual([1632, 1673, 1700])

  const pane = await $.ui.mount({ plugin: 'hr-ondas', surface: 'terminal', component: 'Pane', requestId: 'ondas', props: {} as any })
  expect(await pane.find({ text: /a passada nas Demandas antigas ficou com você na #1673$/ })).toBeTruthy()
  expect(await pane.find({ text: /→ #1673 · Tecnologia: rodar em produção/ })).toBeTruthy()
  // nenhum link no painel
  expect(await pane.findAll({ type: 'Link' })).toHaveLength(0)
  // PRD fechado: marcado
  expect(await pane.find({ text: /→ ✓ fechado · PRD #1632/ })).toBeTruthy()
  expect(await pane.find({ text: /#1614 é sua · Aceite do diretor/ })).toBeTruthy()
  // um botão resolver por Onda
  const botoes = (await pane.findAll({ type: 'Button' })).map(b => (b.props as { label?: string }).label)
  expect(botoes).toEqual(['resolver', 'resolver', 'resolver'])
  await pane.unmount()
})
