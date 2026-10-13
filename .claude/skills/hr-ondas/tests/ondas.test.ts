import { expect, mock, test } from 'claude-code/testing'

import { alvo, detalhe, etapas, pendentes, prdsVisiveis, situacaoDaOnda } from '../hooks/register'
import type { Coleta, SubAgente } from '../types'

const AGORA = 1_800_000_000_000
// recorte real do /api/data (PRDs 1128 e 1129), com a #1132 forçada em PR aberto e CI vermelho
const BRUTO = {"os":{"repo":"pedrorezendefig/hospital-reunioes","prds":[{"n":1129,"titulo":"PRD: Contas médicas, Gestão (memória por tela, ensinar regra, Validação, Conferência da coordenação, Contratos, Habilitação, ditado; ADR 0070)","ondas":[[1139],[1140,1143,1144],[1141,1142,1146],[1145],[1147]],"issues":[{"n":1147,"titulo":"docs: manual do PRD #1129","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1147","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1139,1140,1141,1142,1143,1144,1145,1146]},{"n":1146,"titulo":"Contas médicas: tabela de preço em PDF ou planilha com mapeamento proposto pela IA","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1146","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1140]},{"n":1145,"titulo":"Contas médicas: ditado nos campos de texto longo","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1145","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1141,1142,1143]},{"n":1144,"titulo":"Contas médicas: Contratos e aviso de reajuste no sino","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1144","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1139]},{"n":1143,"titulo":"Contas médicas: Conferência da coordenação (cenários, Passo C, lembretes, tela)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1143","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1131,1137,1139]},{"n":1142,"titulo":"Contas médicas: fila de Validação (regras pendentes, bloqueados, observações, Retorno, enviar ao cadastro)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1142","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1139,1140]},{"n":1141,"titulo":"Contas médicas: ensinar uma regra nova com proposta da IA e reanalisar contas afetadas","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1141","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1140]},{"n":1140,"titulo":"Contas médicas: Memória da operadora por tela (editar, decidir, histórico, exportar) e biblioteca de tabelas","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1140","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1139]},{"n":1139,"titulo":"Contas médicas: migration 118 e tela de Habilitação (perfil x permissão, registro)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1139","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]}]},{"n":1128,"titulo":"PRD: Contas médicas, IA e Painel (Passo A e Passo B pelo adaptador com JSON schema e ZDR, se necessário, marcações, reenvio com nota de saída, Painel; ADR 0070)","ondas":[[1130,1132,1133,1136],[1131,1137],[1134,1135],[1138]],"issues":[{"n":1138,"titulo":"docs: manual do PRD #1128","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1138","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1131,1132,1133,1134,1135,1136,1137]},{"n":1137,"titulo":"Contas médicas: Painel (nota por semana, causa-raiz, itens que faltam, produção, nível de evidência, custo)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1137","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130]},{"n":1136,"titulo":"Contas médicas: reenvio da conta corrigida e nota de saída","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1136","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1135,"titulo":"Contas médicas: Passo B, comparação com a memória e conferência das linhas da IA","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1135","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1131]},{"n":1134,"titulo":"Contas médicas: se necessário sempre incluído (PRESCRITO_SN) e classe de UTI do dia","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1134","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1131]},{"n":1133,"titulo":"Contas médicas: prescrição lida por coordenada de coluna","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1133","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1132,"titulo":"Contas médicas: marcações de caixa e botão e formulário em branco aprendido","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1132","fase":"pr_aberto","pr":1150,"ci":"vermelho","veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1131,"titulo":"Contas médicas: Passo A, eventos do prontuário com página e trecho","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1131","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130]},{"n":1130,"titulo":"Contas médicas: migration 117 e adaptador de IA (JSON schema, ZDR, cache, custo por chamada, modelo por passo)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1130","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]}]}]},"agentes":[{"nome":"onda-ia-onda1","status":"busy","estado":"working","inicio":0}],"prdSessoes":{"onda-ia-onda1":1128},"migrations":[{"numero":117,"arquivo":"117_contas_medicas_ia.sql","caminho":"/tmp/fechar_onda/onda-ia-onda1/117_contas_medicas_ia.sql","sessao":"onda-ia-onda1","mtime":0,"linhas":210},{"numero":116,"arquivo":"116_contas_medicas_fundacao.sql","caminho":"/tmp/fechar_onda/onda-a-onda1/116_contas_medicas_fundacao.sql","sessao":"onda-a-onda1","mtime":0,"linhas":587}],"aplicada":116}
const COLETA = {
  ...BRUTO,
  migrations: BRUTO.migrations.map(m => ({ ...m, mtime: AGORA - 12 * 60_000 })),
}
const comEm = (c: typeof COLETA): Coleta => ({ ...c, em: AGORA }) as Coleta

const sub = (x: Partial<SubAgente>): SubAgente => ({
  sessao: 'onda-ia-onda1', id: 'a', tipo: 'hr-implementador', descricao: '', esforco: null,
  modelo: 'claude-opus-5-5', inicio: AGORA - 600_000, fim: AGORA - 30_000, ctx: 80_000, terminou: false, ...x,
})
const AGENTES = [
  sub({ id: 'imp', descricao: 'Implementa #1132', esforco: 'xhigh', ctx: 263_000, terminou: true }),
  sub({ id: 'rev', tipo: 'hr-revisor', descricao: 'Revisar PR 1150', ctx: 76_000 }),
]

test('migration pendente é só a que o health ainda não devolveu', () => {
  expect(pendentes(comEm(COLETA)).map(m => m.numero)).toEqual([117])
  expect(pendentes(comEm({ ...COLETA, aplicada: 117 }))).toEqual([])
})

test('painel mostra o PRD com sessão viva primeiro e esconde o PRD parado', () => {
  const prds = prdsVisiveis(comEm(COLETA), false).map(p => p.n)
  expect(prds).toEqual([1128])
  expect(prdsVisiveis(comEm(COLETA), true).map(p => p.n)).toEqual([1128, 1129])
})

test('detalhe da issue traz CI e bloqueadoras', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const i1132 = prd.issues.find(i => i.n === 1132)!
  const i1137 = prd.issues.find(i => i.n === 1137)!
  expect(detalhe(i1132)).toBe('PR aberto · CI vermelho')
  expect(detalhe(i1137)).toBe('bloqueada · espera #1130')
})

test('sub-agente cai na fatia pelo número da issue ou do PR', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  expect(AGENTES.map(a => alvo(a, prd))).toEqual([1132, 1132])
  expect(alvo(sub({ descricao: 'Implementa #9999' }), prd)).toBeNull()
})

test('esteira da fatia: implementou, CI vermelho, revisor trabalhando', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const i = prd.issues.find(x => x.n === 1132)!
  const e = etapas(i, AGENTES, AGORA).map(s => `${s.nome}:${s.estado}`)
  expect(e).toEqual(['implementar:feita', 'CI:falhou', 'revisar:agora', 'subida:falta', 'no ar:falta'])
  // revisor sem escrever há mais de 10 min não conta como trabalhando
  const velho = etapas(i, [{ ...AGENTES[1]!, fim: AGORA - 11 * 60_000 }], AGORA)
  expect(velho.find(s => s.nome === 'revisar')!.estado).toBe('falta')
})

test('onda com fatia em PR anda; onda só bloqueada fica parada', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const porN = (ns: number[]) => ns.map(n => prd.issues.find(i => i.n === n)!)
  expect(situacaoDaOnda(porN(prd.ondas[0]!), [], prd, AGORA)).toBe('andando')
  expect(situacaoDaOnda(porN(prd.ondas[2]!), [], prd, AGORA)).toBe('parada')
})

const montar = async ($: any, on: any) => {
  mock.clock(on, { now: AGORA })
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify({ ...COLETA, subAgentes: AGENTES }), stderr: '' } }))
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', () => null)
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' })
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`painel desenha onda, fase e migration (${surface})`, async ($, on) => {
    await montar($, on)
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    expect(await pane.find({ text: /117 cole no Studio/ })).toBeTruthy()
    expect(await pane.find({ text: /Onda 2/ })).toBeTruthy()
    expect(await pane.find({ text: /espera #1130/ })).toBeTruthy()
    expect(await pane.find({ text: /onda-ia-onda1/ })).toBeTruthy()
    expect(await pane.find({ text: /PRD #1129/ })).toBeUndefined()
    expect(await pane.find({ text: /1 trabalhando · 1 terminado/ })).toBeTruthy()
    expect(await pane.find({ text: /hr-revisor/ })).toBeTruthy()
    expect(await pane.find({ text: /Opus 5\.5 · xhigh/ })).toBeTruthy()
    expect(await pane.find({ text: /ctx 26% · 263k/ })).toBeTruthy()
    expect(await pane.find({ text: /Onda 3 · parada/ })).toBeTruthy()
  })

  test(`faixa acima do prompt avisa a migration com o link (${surface})`, async ($, on) => {
    await montar($, on)
    const faixa = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'AbovePrompt', props: { hasSurvey: false } as any })
    expect(await faixa.find({ text: /migration 117 esperando o Studio/ })).toBeTruthy()
  })
}

const iniciar = async ($: any, on: any, isInteractive: boolean) => {
  const abertos: string[] = []
  const relogio = mock.clock(on, { now: AGORA })
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify({ ...COLETA, agentes: [], migrations: [] }), stderr: '' } }))
  on('command.register', () => ({ value: undefined }))
  on('ui.open', (_$: any, e: any) => {
    abertos.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('session.start', () => ({ cwd: '/repo' }))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive })
  await relogio.advance(1) // deixa a primeira coleta terminar dentro do teste
  return abertos
}

test('sessão interativa nasce com o painel das ondas aberto', async ($, on) => {
  expect(await iniciar($, on, true)).toContain('ondas')
})

test('sessão de fundo não abre o painel sem novidade', async ($, on) => {
  expect(await iniciar($, on, false)).toEqual([])
})
