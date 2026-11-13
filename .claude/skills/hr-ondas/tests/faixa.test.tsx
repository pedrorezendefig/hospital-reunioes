import { expect, mock, test } from 'claude-code/testing'

import {
  aoAnexar, aoChamarSkill, aoEscrever, aoReceber, aoResultado, aoUsar, faixaVazia, linhasDaFaixa,
} from '../hooks/register'
import type { LinhaDaFaixa } from '../hooks/register'
import type { Faixa } from '../types'

// A faixa da sessão: a fase desta sessão na esteira, inferida do que ela chama e escreve.

const AGORA = 1_800_000_000_000
const MIN = 60_000
const textoDaLinha = (l: LinhaDaFaixa) => l.partes.map(p => p.texto).join('')
const textos = (f: Faixa, agora = AGORA) => linhasDaFaixa(f, agora).map(textoDaLinha)
const notificacao = (toolUseId: string, status: string, resultado = '') =>
  `<task-notification>\n<task-id>a835924afb49b17c0</task-id>\n<tool-use-id>${toolUseId}</tool-use-id>\n<status>${status}</status>\n<summary>x</summary>\n<result>${resultado}</result>\n</task-notification>`

test('fora da esteira a faixa fica calada, mesmo com shell rodando', () => {
  const f = aoUsar(faixaVazia(), 'b1', 'Bash', { command: 'ls', description: 'Lista arquivos' }, AGORA)
  expect(linhasDaFaixa(f, AGORA)).toEqual([])
  expect(linhasDaFaixa(null, AGORA)).toEqual([])
  expect(aoChamarSkill(faixaVazia(), 'humanizer').skill).toBeNull()
})

test('grill mostra a rodada, as perguntas, a espera e a porta', () => {
  let f = aoUsar(faixaVazia(), 's1', 'Skill', { skill: 'grill-with-docs' }, AGORA)
  f = aoEscrever(f, '**Rodada 1**\n\n**P1. Destino**\n...\n**P7. Extras**\n\nRecomendo: (a).')
  expect(textos(f)[0]).toBe('▸ fase: grill · rodada 1 · P1 a P7')
  f = { ...f, ociosaDesde: AGORA - 3 * MIN }
  expect(textos(f)[0]).toBe('▸ fase: grill · rodada 1 · P1 a P7 · esperando você há 3 min')
  f = aoEscrever(f, '**Rodada 2**\n\n**P8. Formato**')
  expect(textos(f)[0]).toContain('rodada 2 · P8 ·')
  f = aoEscrever(f, '**Porta: C (PR direto)**, porque é ferramenta')
  expect(textos(f)[0]).toContain('porta C')
  // o express continua o mesmo grill; outra skill zera a rodada
  expect(aoChamarSkill(f, 'express').rodada).toBe(2)
  const prd = aoChamarSkill(f, 'to-prd')
  expect([prd.rodada, prd.porta, textos(prd)[0]]).toEqual([null, null, '▸ fase: PRD · esperando você há 3 min'])
  // fora do grill, "Rodada" no texto não conta
  expect(aoEscrever(prd, '**Rodada 9**').rodada).toBeNull()
})

test('comando digitado (/grill-with-docs) também marca a fase', () => {
  const f = aoReceber(faixaVazia(), '<command-message>grill-with-docs</command-message>\n<command-name>/grill-with-docs</command-name>')
  expect(f.skill).toBe('grill-with-docs')
})

test('Fatia da onda passa por TDD, revisão, must-fix e correção, com tentativa e cronômetro', () => {
  let f = aoUsar(faixaVazia(), 'sk', 'Skill', { skill: 'onda-enxuta' }, AGORA)
  f = aoUsar(f, 'imp', 'Agent', { description: 'Implementar issue #1620', subagent_type: 'onda-implementador', prompt: '[papel: implementador]' }, AGORA - 12 * MIN)
  f = aoResultado(f, 'imp', 'Async agent launched successfully. agentId: a1')
  expect(textos(f)[1]).toBe('  • #1620 · TDD · 12:00')

  f = aoReceber(f, notificacao('imp', 'completed', 'PR #1666 aberto'))
  f = aoUsar(f, 'e1', 'Bash', { command: 'python3 .claude/skills/onda-enxuta/scripts/estado_onda.py issue --sessao hsm-qr --onda 2 --numero 1620 --pr 1666 --status revisao' }, AGORA)
  f = aoResultado(f, 'e1', '')
  f = aoUsar(f, 'rev', 'Agent', { description: 'Revisar PR #1666', subagent_type: 'onda-revisor', prompt: '[papel: revisor]\nPR #1666, issue #1620.' }, AGORA - 11 * MIN)
  const rev = linhasDaFaixa(f, AGORA)[1]!
  expect(textoDaLinha(rev)).toBe('  • #1620 · revisão · PR #1666 · 11:00')
  // revisor passou de 10 min: amarelo
  expect(rev.partes.at(-1)!.cor).toBe('warning')

  f = aoReceber(f, notificacao('rev', 'completed', 'pr: #1666 (issue #1620)\nveredito: MUST-FIX (2). (1) ...'))
  expect(f.fatias[0]!.veredito).toBe('MUST-FIX')
  f = aoUsar(f, 'cor1', 'Agent', { description: 'Corrigir must-fix do PR #1666', subagent_type: 'onda-corretor', prompt: '[papel: corretor]\nPR #1666, issue #1620. Motivo: revisao.' }, AGORA - MIN)
  expect(textos(f)[1]).toBe('  • #1620 · correção · PR #1666 · MUST-FIX · tentativa 1/3 · 1:00')
  f = aoReceber(f, notificacao('cor1', 'completed'))

  // conflito com PR irmão não conta tentativa; CI vermelho conta
  f = aoUsar(f, 'cor2', 'Agent', { description: 'Rebase conflito #1666', subagent_type: 'onda-corretor', prompt: 'PR #1666, issue #1620. Motivo: conflito.' }, AGORA)
  f = aoReceber(f, notificacao('cor2', 'completed'))
  expect(f.fatias[0]!.tentativas).toBe(1)
  f = aoUsar(f, 'cor3', 'Agent', { description: 'Corrigir CI do PR #1666', subagent_type: 'onda-corretor', prompt: 'PR #1666, issue #1620. Motivo: ci.' }, AGORA)
  const t2 = linhasDaFaixa(f, AGORA)[1]!.partes.find(p => p.texto.includes('tentativa'))!
  expect([t2.texto, t2.cor]).toEqual([' · tentativa 2/3', 'warning'])
  f = aoReceber(f, notificacao('cor3', 'completed'))
  f = aoUsar(f, 'cor4', 'Agent', { description: 'Corrigir CI do PR #1666', subagent_type: 'hr-corretor', prompt: 'PR #1666, issue #1620. Motivo: ci.' }, AGORA)
  expect(linhasDaFaixa(f, AGORA)[1]!.partes.find(p => p.texto.includes('tentativa'))!.cor).toBe('error')

  // baixa em vermelho; mergeada some
  f = aoReceber(f, notificacao('cor4', 'completed'))
  f = aoUsar(f, 'e2', 'Bash', { command: 'estado_onda.py issue --sessao a --onda 2 --numero 1620 --status baixa' }, AGORA)
  f = aoResultado(f, 'e2', '')
  expect(linhasDaFaixa(f, AGORA)[1]!.partes[0]).toEqual({ texto: '  ✗ #1620', bold: true, cor: 'error' })
  f = aoUsar(f, 'e3', 'Bash', { command: 'estado_onda.py issue --sessao a --onda 2 --numero 1620 --status mergeado' }, AGORA)
  f = aoResultado(f, 'e3', '')
  expect(textos(f)).toEqual(['▸ fase: onda'])
})

test('três Fatias em paralelo, uma linha cada', () => {
  let f = aoChamarSkill(faixaVazia(), 'onda-enxuta')
  for (const n of [1621, 1622, 1623]) {
    f = aoUsar(f, `i${n}`, 'Agent', { description: `Implementar issue #${n}`, subagent_type: 'onda-implementador', prompt: '' }, AGORA)
  }
  expect(textos(f).slice(1)).toEqual(['  • #1621 · TDD · 0:00', '  • #1622 · TDD · 0:00', '  • #1623 · TDD · 0:00'])
})

test('esperas de shell, Monitor de CI e segundo plano, com TaskStop', () => {
  let f = aoChamarSkill(faixaVazia(), 'ship')
  f = aoUsar(f, 'sh', 'Bash', { command: 'uv run pytest', description: 'Roda os testes' }, AGORA - 6 * MIN)
  f = aoUsar(f, 'mo', 'Monitor', { description: 'checks do PR #1600', command: 'gh pr checks 1600 --json name,bucket', timeout_ms: 1_800_000 }, AGORA - 16 * MIN)
  f = aoResultado(f, 'mo', 'Monitor started. taskId: bqg9garn5')
  f = aoUsar(f, 'bg', 'Bash', { command: 'sleep 99', description: 'Espera o deploy', run_in_background: true }, AGORA)
  f = aoResultado(f, 'bg', 'Command running in background with ID: bymrkseye')
  expect(textos(f).slice(1)).toEqual([
    '  ◷ shell: Roda os testes · 6:00',
    '  ◷ CI do PR #1600 · 16:00',
    '  ◷ em segundo plano: Espera o deploy · 0:00',
  ])
  // shell acima de 5 min e CI acima de 15 min ficam amarelos; o segundo plano não tem limite
  expect(linhasDaFaixa(f, AGORA).slice(1).map(l => l.partes.at(-1)!.cor)).toEqual(['warning', 'warning', undefined])
  f = aoResultado(f, 'sh', '12 passed')
  f = aoUsar(f, 'stop', 'TaskStop', { task_id: 'bqg9garn5' }, AGORA)
  f = aoReceber(f, notificacao('bg', 'completed'))
  expect(textos(f)).toEqual(['▸ fase: ship'])
})

test('o PR aberto pelo gh pr create e a subida entram na conta da sessão', () => {
  let f = aoChamarSkill(faixaVazia(), 'ship')
  f = aoUsar(f, 'pr', 'Bash', { command: 'gh pr create --title x --body-file pr.md' }, AGORA)
  f = aoResultado(f, 'pr', 'https://github.com/pedrorezendefig/hospital-reunioes/pull/1680\n')
  expect(f.prs).toEqual([1680])
  f = aoUsar(f, 'dry', 'Bash', { command: 'python3 fechar_onda.py --prs 1680 --dry-run' }, AGORA)
  f = aoResultado(f, 'dry', '')
  f = aoUsar(f, 'up', 'Bash', { command: 'python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs 1680 1681', run_in_background: true }, AGORA - 3 * MIN)
  expect(f.prs).toEqual([1680, 1681])
  expect(textos(f).at(-1)).toBe('  ◷ subida dos PRs #1680 #1681 · 3:00')
  // Fatia com PR na subida: a fase dela é a subida
  f = aoUsar(f, 'e', 'Bash', { command: 'estado_onda.py issue --sessao a --onda 1 --numero 1679 --pr 1681 --status verde' }, AGORA)
  f = aoResultado(f, 'e', '')
  expect(textos(f)).toContain('  • #1679 · subida · PR #1681 · 3:00')
})

test('"espera você" da onda aparece até o resolvido', () => {
  let f = aoChamarSkill(faixaVazia(), 'onda-enxuta')
  f = aoUsar(f, 'ev', 'Bash', { command: 'estado_onda.py evento --sessao a --onda 1 --tipo pronto-para-voce --texto "migration 124 esperando o Studio"' }, AGORA)
  f = aoUsar(f, 'ev2', 'Bash', { command: 'estado_onda.py evento --sessao a --onda 1 --tipo pr-pronto --texto "PR verde"' }, AGORA)
  f = aoResultado(aoResultado(f, 'ev', ''), 'ev2', '')
  expect(textos(f)).toEqual(['▸ fase: onda', '  ! espera você: migration 124 esperando o Studio'])
  f = aoUsar(f, 'rs', 'Bash', { command: 'estado_onda.py resolvido --sessao a --onda 1 --texto "migration 124 aplicada"' }, AGORA)
  expect(f.paradas).toEqual([])
})

test('linha de encerrar com o que falta, ou "pode" com o PR mergeado', () => {
  const base = { ...aoChamarSkill(faixaVazia(), 'ship'), prs: [1680], ociosaDesde: AGORA }
  const falta = { ...base, encerrar: { abertos: [1680], mergeados: [], semCommit: 2, worktree: 'faixa-x' } }
  expect(textos(falta).at(-1)).toBe('  encerrar: falta PR #1680 aberto · 2 arquivo(s) sem commit · worktree faixa-x')
  const pode = { ...base, encerrar: { abertos: [], mergeados: [1680], semCommit: 0, worktree: null } }
  expect(textos(pode).at(-1)).toBe('  encerrar: pode (PR #1680 mergeado)')
  // com o turno rodando, a linha não aparece
  expect(textos({ ...pode, ociosaDesde: null }).some(t => t.includes('encerrar'))).toBe(false)
})

test('aoAnexar lê as linhas como a conversa as guarda', () => {
  let f = aoAnexar(faixaVazia(), { type: 'assistant', content: [{ type: 'tool_use', id: 'tu1', name: 'Skill', input: { skill: 'onda-enxuta' } }] }, AGORA)
  f = aoAnexar(f, {
    type: 'assistant',
    content: [
      { type: 'text', text: 'Disparando o implementador.' },
      { type: 'tool_use', id: 'tu2', name: 'Agent', input: { description: 'Implementar issue #1620', subagent_type: 'onda-implementador', prompt: '' } },
    ],
  }, AGORA)
  f = aoAnexar(f, { type: 'user', content: [{ type: 'tool_result', tool_use_id: 'tu2', content: [{ type: 'text', text: 'Async agent launched successfully. agentId: x' }] }] }, AGORA)
  expect(f.tarefas.map(t => t.id)).toEqual(['tu2'])
  f = aoAnexar(f, { type: 'user', content: notificacao('tu2', 'completed') }, AGORA)
  expect(f.tarefas).toEqual([])
  expect(f.fatias.map(x => x.issue)).toEqual([1620])
})

test('faixa desenhada acima do prompt a partir do session.append', async ($, on) => {
  mock.clock(on, { now: AGORA })
  // embaixo dos plugins, o Claude Code não desenha nada nesta faixa
  on('ui.render', ($: any, e: any) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })
  await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: '<command-name>/grill-with-docs</command-name>' }] } } as any)
  await $.session.append({ message: { type: 'assistant', content: [{ type: 'text', text: '**Rodada 1**\n\n**P1. A**\n\n**P2. B**' }] } } as any)
  // linha de sub-agente não mexe na faixa
  await $.session.append({ message: { type: 'assistant', content: [{ type: 'tool_use', id: 'x', name: 'Skill', input: { skill: 'ship' } }] }, agentId: 'a1' } as any)
  const ui = await $.ui.mount({
    plugin: 'hr-ondas', component: 'AbovePrompt', surface: 'terminal',
    props: { hasSurvey: false, bodyColumns: 100 },
  } as any)
  const linha = await ui.find({ type: 'Text', text: /fase:/ })
  expect(linha?.text).toBe('▸ fase: grill · rodada 1 · P1 a P2')
  await ui.unmount()
})
