import { expect, mock, test } from 'claude-code/testing'

import {
  agentesDoPrd, alvo, assinatura, atividadeDaSessao, comSemPrd, corDaDuracao, declaradasAplicadas, detalhe, duracaoDaOnda, etapas, focoDaSessao, linhagem,
  nomeCurtoDaSessao, ondasDoPrd, pendentes, prdsVisiveis, esperaDeFora, rotuloDoAlvo, rotuloDoShell, SEM_PRD, sessoesDoPrd,
  prontasDoPrd, situacaoDaOnda, subidaDoPr, precisaDeVoce, agentesDaFatia, temposDaFatia, tempoCurto, pedidoDaOnda,
} from '../hooks/register'
import type { Coleta, SubAgente } from '../types'

const AGORA = 1_800_000_000_000
// recorte real do /api/data (PRDs 1128 e 1129), com a #1132 forçada em PR aberto e CI vermelho
const BRUTO = {"os":{"repo":"pedrorezendefig/hospital-reunioes","prds":[{"n":1129,"titulo":"PRD: Contas médicas, Gestão (memória por tela, ensinar regra, Validação, Conferência da coordenação, Contratos, Habilitação, ditado; ADR 0070)","ondas":[[1139],[1140,1143,1144],[1141,1142,1146],[1145],[1147]],"issues":[{"n":1147,"titulo":"docs: manual do PRD #1129","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1147","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1139,1140,1141,1142,1143,1144,1145,1146]},{"n":1146,"titulo":"Contas médicas: tabela de preço em PDF ou planilha com mapeamento proposto pela IA","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1146","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1140]},{"n":1145,"titulo":"Contas médicas: ditado nos campos de texto longo","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1145","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1141,1142,1143]},{"n":1144,"titulo":"Contas médicas: Contratos e aviso de reajuste no sino","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1144","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1139]},{"n":1143,"titulo":"Contas médicas: Conferência da coordenação (cenários, Passo C, lembretes, tela)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1143","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1131,1137,1139]},{"n":1142,"titulo":"Contas médicas: fila de Validação (regras pendentes, bloqueados, observações, Retorno, enviar ao cadastro)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1142","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1139,1140]},{"n":1141,"titulo":"Contas médicas: ensinar uma regra nova com proposta da IA e reanalisar contas afetadas","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1141","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1140]},{"n":1140,"titulo":"Contas médicas: Memória da operadora por tela (editar, decidir, histórico, exportar) e biblioteca de tabelas","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1140","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1139]},{"n":1139,"titulo":"Contas médicas: migration 118 e tela de Habilitação (perfil x permissão, registro)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1139","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]}]},{"n":1128,"titulo":"PRD: Contas médicas, IA e Painel (Passo A e Passo B pelo adaptador com JSON schema e ZDR, se necessário, marcações, reenvio com nota de saída, Painel; ADR 0070)","ondas":[[1130,1132,1133,1136],[1131,1137],[1134,1135],[1138]],"issues":[{"n":1138,"titulo":"docs: manual do PRD #1128","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1138","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1131,1132,1133,1134,1135,1136,1137]},{"n":1137,"titulo":"Contas médicas: Painel (nota por semana, causa-raiz, itens que faltam, produção, nível de evidência, custo)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1137","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130]},{"n":1136,"titulo":"Contas médicas: reenvio da conta corrigida e nota de saída","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1136","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1135,"titulo":"Contas médicas: Passo B, comparação com a memória e conferência das linhas da IA","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1135","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130,1131]},{"n":1134,"titulo":"Contas médicas: se necessário sempre incluído (PRESCRITO_SN) e classe de UTI do dia","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1134","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1131]},{"n":1133,"titulo":"Contas médicas: prescrição lida por coordenada de coluna","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1133","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1132,"titulo":"Contas médicas: marcações de caixa e botão e formulário em branco aprendido","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1132","fase":"pr_aberto","pr":1150,"ci":"vermelho","veredito":null,"conflito":false,"versao":null,"por":[]},{"n":1131,"titulo":"Contas médicas: Passo A, eventos do prontuário com página e trecho","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1131","fase":"bloqueada","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[1130]},{"n":1130,"titulo":"Contas médicas: migration 117 e adaptador de IA (JSON schema, ZDR, cache, custo por chamada, modelo por passo)","estado":"OPEN","url":"https://github.com/pedrorezendefig/hospital-reunioes/issues/1130","fase":"fila","pr":null,"ci":null,"veredito":null,"conflito":false,"versao":null,"por":[]}]}]},"agentes":[{"nome":"onda-ia-onda1","status":"busy","estado":"working","inicio":0}],"prdSessoes":{"onda-ia-onda1":1128},"migrations":[{"numero":117,"arquivo":"117_contas_medicas_ia.sql","caminho":"/tmp/fechar_onda/onda-ia-onda1/117_contas_medicas_ia.sql","sessao":"onda-ia-onda1","mtime":0,"linhas":210},{"numero":116,"arquivo":"116_contas_medicas_fundacao.sql","caminho":"/tmp/fechar_onda/onda-a-onda1/116_contas_medicas_fundacao.sql","sessao":"onda-a-onda1","mtime":0,"linhas":587}],"aplicada":116}
const COLETA = {
  ...BRUTO,
  migrations: BRUTO.migrations.map(m => ({ ...m, mtime: AGORA - 12 * 60_000 })),
  // as migrations do .claude/fluxo.json do Hospital
  migracoes: { pasta: 'hospital-reunioes/supabase/migrations', aplicar: 'cole no Studio', editor: 'https://studio.exemplo/sql/new' },
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

test('a fala "apliquei a migration N" é declaração; futuro, negativa e outra frase não são', () => {
  expect(declaradasAplicadas('apliquei a migration 118 no Studio, pode seguir')).toEqual([118])
  expect(declaradasAplicadas('Apliquei as migrations 117 e 118')).toEqual([117, 118])
  expect(declaradasAplicadas('já apliquei a migration 116, 117, 118')).toEqual([116, 117, 118])
  expect(declaradasAplicadas('vou aplicar a migration 118 agora')).toEqual([])
  expect(declaradasAplicadas('não apliquei a migration 118 ainda')).toEqual([])
  expect(declaradasAplicadas('apliquei o patch 118')).toEqual([])
  expect(declaradasAplicadas('a migration 118 está esperando')).toEqual([])
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
  // na linha da Onda, a bloqueadora já está dita uma vez só
  expect(detalhe(i1137, false)).toBe('bloqueada')
})

test('sub-agente cai na fatia pelo número da issue ou do PR', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  expect(AGENTES.map(a => alvo(a, prd))).toEqual([1132, 1132])
  expect(alvo(sub({ descricao: 'Implementa #9999' }), prd)).toBeNull()
  // "#1150" sem a palavra PR: não é issue, é o PR da #1132 (os corretores da onda falam assim)
  expect(alvo(sub({ descricao: 'Rebase conflito #1150' }), prd)).toBe(1132)
  expect(rotuloDoAlvo(sub({ descricao: 'Rebase conflito #1150' }), prd)).toBe('#1132 (PR #1150)')
  expect(rotuloDoAlvo(sub({ descricao: 'Implementa #1133' }), prd)).toBe('#1133')
  expect(rotuloDoAlvo(sub({ descricao: 'Audita a fila' }), prd)).toBe('Audita a fila')
})

test('foco da sessão: os sub-agentes vivos; sem vivo, o último que acabou', () => {
  const vivo = sub({ id: 'vivo', sessao: 'onda-gestao-onda4', descricao: 'Implementar #1143' })
  const outroVivo = sub({ id: 'vivo2', sessao: 'onda-gestao-onda4', tipo: 'hr-revisor', descricao: 'Revisar PR 1150' })
  const velho = sub({ id: 'velho', sessao: 'onda-gestao-onda3', terminou: true, fim: AGORA - 900_000 })
  const recente = sub({ id: 'recente', sessao: 'onda-gestao-onda3', tipo: 'hr-corretor', terminou: true, fim: AGORA - 60_000 })
  const ags = [velho, vivo, recente, outroVivo]
  expect(focoDaSessao('onda-gestao-onda4', ags, AGORA).map(a => a.id)).toEqual(['vivo', 'vivo2'])
  expect(focoDaSessao('onda-gestao-onda3', ags, AGORA).map(a => a.id)).toEqual(['recente'])
  expect(focoDaSessao('onda-gestao-onda5', ags, AGORA)).toEqual([])
  // parado (sem end_turn, sem escrita há mais de 10 min) não é vivo: vira o "último"
  const parado = sub({ id: 'parado', sessao: 'onda-x', fim: AGORA - 11 * 60_000 })
  expect(focoDaSessao('onda-x', [parado], AGORA).map(a => a.id)).toEqual(['parado'])
  expect(nomeCurtoDaSessao('onda-gestao-onda4')).toBe('gestao-onda4')
})

test('sub-agente vai ao PRD do alvo, mesmo com a sessão mapeada para outro PRD', () => {
  // a passagem da onda-ia cita primeiro "nem no PRD #1129" e o coletar.sh mapeia a sessão para o 1129
  const prds = BRUTO.os.prds.map(p => p.n !== 1128 ? p : {
    ...p, issues: p.issues.map(i => i.n === 1135 ? { ...i, fase: 'pr_aberto', pr: 1179 } : i),
  })
  const cor = sub({ sessao: 'onda-ia-onda3', id: 'cor', tipo: 'hr-corretor', descricao: 'Corrige must-fix do PR #1179' })
  // na onda-gestao (PRD #1129), um revisor do PR #1179 também vai ao PRD #1128
  const cruz = sub({ sessao: 'onda-gestao-onda3', id: 'cruz', tipo: 'hr-revisor', descricao: 'Revisa PR #1179', inicio: AGORA - 900_000 })
  const solto = sub({ sessao: 'onda-gestao-onda3', id: 'solto', tipo: 'general-purpose', descricao: 'Audita a fila' })
  const gest = sub({ sessao: 'onda-gestao-onda3', id: 'gest', descricao: 'Implementa issue #1141', inicio: AGORA })
  const c = {
    ...comEm(COLETA),
    os: { ...BRUTO.os, prds },
    agentes: [
      { nome: 'onda-ia-onda3', status: 'busy', estado: 'working', inicio: 0 },
      { nome: 'onda-gestao-onda3', status: 'busy', estado: 'working', inicio: 0 },
      { nome: 'onda-c-onda1', status: 'busy', estado: 'working', inicio: 0 },
    ],
    prdSessoes: { 'onda-ia-onda3': 1129, 'onda-gestao-onda3': 1129, 'onda-c-onda1': 1129 },
    subAgentes: [cor, cruz, solto, gest],
  } as Coleta
  const p1128 = c.os!.prds.find(p => p.n === 1128)!
  const p1129 = c.os!.prds.find(p => p.n === 1129)!
  expect(agentesDoPrd(c, p1128).map(a => `${a.id}:${alvo(a, p1128)}`)).toEqual(['cruz:1135', 'cor:1135'])
  // sem alvo em nenhum PRD, o sub-agente fica no PRD da sessão, em "outros agentes"
  expect(agentesDoPrd(c, p1129).map(a => a.id)).toEqual(['solto', 'gest'])
  // a sessão vai ao PRD do alvo do seu sub-agente mais recente; sem sub-agente, fica no da passagem
  expect(sessoesDoPrd(c, 1128).map(s => s.nome)).toEqual(['onda-ia-onda3'])
  expect(sessoesDoPrd(c, 1129).map(s => s.nome)).toEqual(['onda-gestao-onda3', 'onda-c-onda1'])
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

test('issue humana fechada sem PR: esteira de uma etapa só, feita, e conta como pronta no PRD', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const humana = { ...prd.issues.find(x => x.n === 1130)!, estado: 'CLOSED', fase: 'encerrada_sem_pr' as const }
  expect(etapas(humana, AGENTES, AGORA).map(s => `${s.nome}:${s.estado}`)).toEqual(['fechada sem PR:feita'])
  const noAr = { ...prd.issues.find(x => x.n === 1131)!, estado: 'CLOSED', fase: 'em_producao' as const }
  expect(prontasDoPrd({ ...prd, issues: [humana, noAr, prd.issues.find(x => x.n === 1132)!] })).toBe(2)
})

test('onda com fatia em PR anda; onda só bloqueada fica parada', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const porN = (ns: number[]) => ns.map(n => prd.issues.find(i => i.n === n)!)
  expect(situacaoDaOnda(porN(prd.ondas[0]!), [], prd, AGORA)).toBe('andando')
  expect(situacaoDaOnda(porN(prd.ondas[2]!), [], prd, AGORA)).toBe('parada')
})

// a fila-alvo da passagem onda-ia-onda1.md, com uma issue de outro PRD e uma que não existe
const PASSAGENS = {
  'onda-ia': { ondas: { '1': [1130, 1132, 1133], '2': [1131, 1136, 1137, 1139], '3': [1134, 1135], '4': [1138, 9999] }, escritas: [1, 2] },
}

test('ondas do PRD vêm da passagem da linhagem da sessão; sem passagem, das colunas do OS', () => {
  const c = { ...comEm(COLETA), passagens: PASSAGENS } as Coleta
  const prd = c.os!.prds.find(p => p.n === 1128)!
  const ondas = ondasDoPrd(c, prd)
  expect(ondas.map(o => `${o.numero}:${o.issues.join(',')}`)).toEqual(['1:1130,1132,1133', '2:1131,1136,1137', '3:1134,1135', '4:1138'])
  // a onda da sessão viva, a escrita sem sessão e a que ainda não tem passagem
  expect(ondas.map(o => `${o.passagem}:${o.sessao?.nome ?? '-'}`)).toEqual(['viva:onda-ia-onda1', 'escrita:-', 'nao:-', 'nao:-'])
  // o PRD #1129 não tem sessão viva nem passagem: colunas do OS, numeradas
  const outro = c.os!.prds.find(p => p.n === 1129)!
  expect(ondasDoPrd(c, outro).map(o => `${o.numero}:${o.passagem}`)).toEqual(['1:null', '2:null', '3:null', '4:null', '5:null'])
  expect(ondasDoPrd(comEm(COLETA), prd).map(o => o.issues)).toEqual(prd.ondas)
  expect(linhagem('onda-gestao-onda4')).toBe('onda-gestao')
})

test('resumo da onda parada diz qual bloqueadora está na mão do humano', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1129)!
  const porN = new Map(prd.issues.map(i => [i.n, i.n === 1142 ? { ...i, fase: 'humana' as const } : i]))
  const i1145 = porN.get(1145)!
  expect(esperaDeFora([i1145], [1145], porN)).toBe('espera #1141 #1142 (humana) #1143')
  expect(esperaDeFora([i1145], [1145])).toBe('espera #1141 #1142 #1143')
  expect(esperaDeFora([i1145], [1141, 1142, 1143, 1145])).toBeNull()
})

// a #1191 (sem PRD pai, PR aberto) na fila fixa da onda-b, e uma in-progress de um sócio, sem sessão
const SOLTAS = [
  { n: 1191, titulo: 'Contas médicas: OCR da página digitalizada', estado: 'OPEN', url: 'u', fase: 'pr_aberto', pr: 1203, ci: 'verde', veredito: null, conflito: false, versao: null, por: [] },
  { n: 1205, titulo: 'fix solto', estado: 'OPEN', url: 'u', fase: 'em_andamento', pr: null, ci: null, veredito: null, conflito: false, versao: null, por: [] },
]
const ONDA_B = { nome: 'onda-b-onda1', status: 'busy', estado: 'working', inicio: 0 }
const SEM_PRD_NA_COLETA = {
  os: { ...BRUTO.os, soltas: SOLTAS },
  agentes: [...COLETA.agentes, ONDA_B],
  passagens: { ...PASSAGENS, 'onda-b': { ondas: { '1': [1191] }, escritas: [1] } },
}

test('issue sem PRD pai andando vira o grupo "Sem PRD", com a sessão da fila dela', () => {
  const c = { ...comEm(COLETA), ...SEM_PRD_NA_COLETA, os: comSemPrd(SEM_PRD_NA_COLETA.os as Coleta['os']) } as Coleta
  expect(prdsVisiveis(c, false).map(p => p.n)).toEqual([1128, SEM_PRD])
  const sem = c.os!.prds.find(p => p.n === SEM_PRD)!
  expect(sem.issues.map(i => i.n)).toEqual([1191, 1205])
  // a passagem da onda-b não cita PRD: a sessão vai ao grupo pela fila fixa
  expect(sessoesDoPrd(c, SEM_PRD).map(s => s.nome)).toEqual(['onda-b-onda1'])
  expect(ondasDoPrd(c, sem).map(o => `${o.numero}:${o.issues.join(',')}:${o.sessao?.nome}`)).toEqual(['1:1191:onda-b-onda1'])
  // sem issue solta, não há grupo
  expect(comSemPrd(BRUTO.os as Coleta['os'])!.prds.map(p => p.n)).toEqual([1129, 1128])
})

const SUBIDA_EM_CURSO = [{ sessao: 'onda-ia-onda1', prs: [1150], inicio: AGORA - 120_000, fim: null }]
const CI_RODANDO = { '1150': { inicio: AGORA - 9 * 60_000, fim: null } }

const montar = async ($: any, on: any, extra: Record<string, unknown> = {}) => {
  mock.clock(on, { now: AGORA })
  on('process.run', () => ({
    value: { exitCode: 0, stdout: JSON.stringify({ ...COLETA, subAgentes: AGENTES, subidas: SUBIDA_EM_CURSO, ci: CI_RODANDO, ...extra }), stderr: '' },
  }))
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', (_$: any, e: any, next: any) => (e.component === 'Pane' ? null : next(e)))
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
    // monitoramento: o detalhe dos agentes (modelo, esforço, contexto) fica escondido
    expect(await pane.find({ text: /hr-revisor/ })).toBeUndefined()
    expect(await pane.find({ text: /Opus 5\.5/ })).toBeUndefined()
    expect(await pane.find({ text: /ctx 26%/ })).toBeUndefined()
    expect(await pane.find({ text: /Onda 3 · parada/ })).toBeTruthy()
    // tempos: a onda desde o primeiro agente, a subida em curso da sessão, o CI pelos checks
    expect(await pane.find({ text: /Onda 1 · andando · 10 min/ })).toBeTruthy()
    expect(await pane.find({ text: /subida #1150/ })).toBeTruthy()
    expect(await pane.find({ text: /^ · 2:00$/ })).toBeTruthy()
    expect(await pane.find({ text: /^9 min$/ })).toBeTruthy()
    // /ondas detalhe mostra de novo o agente, o modelo e o contexto
    await $.command.run({ command: 'ondas', args: 'detalhe', origin: 'user', presentation: 'text' })
    expect(await pane.find({ text: /hr-revisor/ })).toBeTruthy()
    expect(await pane.find({ text: /Opus 5\.5 · xhigh/ })).toBeTruthy()
    expect(await pane.find({ text: /ctx 26% · 263k/ })).toBeTruthy()
    expect(await pane.find({ text: /^ #1132 \(PR #1150\)$/ })).toBeTruthy()
    expect(await pane.find({ text: /ia-onda1 · Opus 5\.5/ })).toBeTruthy()
  })

  test(`painel sem link: só o editor SQL da migration; a Fatia mostra o tempo de cada etapa (${surface})`, async ($, on) => {
    await montar($, on)
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    const hrefs = (await pane.findAll({ type: 'Link' })).map(l => String((l.props as { href?: string }).href))
    expect(hrefs).toEqual(['https://studio.exemplo/sql/new'])
    expect(await pane.find({ text: /^#1132$/ })).toBeTruthy()
    // implementar 9:30 do agente que terminou, CI 9 min dos checks; a esteira embaixo fica só com as marcas
    expect(await pane.find({ text: /^9 min$/ })).toBeTruthy()
    expect(await pane.find({ text: /^10 min$/ })).toBeTruthy()
    // sem o número do PR na linha da Fatia
    expect(await pane.find({ text: /^PR #1150$/ })).toBeUndefined()
  })

  test(`Fatia no ar de Onda já encerrada ainda mostra o tempo de cada etapa (${surface})`, async ($, on) => {
    const prd = COLETA.os.prds.find(p => p.n === 1128)!
    const noAr = { ...prd.issues.find(i => i.n === 1132)!, estado: 'CLOSED', fase: 'em_producao', ci: null }
    const os = { ...COLETA.os, prds: [{ ...prd, ondas: [[1130, 1133, 1136]], issues: prd.issues.map(i => (i.n === 1132 ? noAr : i)) }] }
    // a sessão que levou a #1132 já acabou: os sub-agentes dela vêm só do histórico
    const historico = [
      sub({ sessao: 'sid-velho', id: 'h-imp', tipo: 'onda-implementador', descricao: 'Implementa issue #1132', inicio: AGORA - 90 * 60_000, fim: AGORA - 68 * 60_000, terminou: true }),
      sub({ sessao: 'sid-velho', id: 'h-rev', tipo: 'onda-revisor', descricao: 'Revisor PR #1150', inicio: AGORA - 60 * 60_000, fim: AGORA - 56 * 60_000, terminou: true }),
    ]
    await montar($, on, {
      os, subAgentes: [], subidas: [], historico, // a sessão da onda segue viva: o PRD fica no painel
      ci: { '1150': { inicio: AGORA - 66 * 60_000, fim: AGORA - 61 * 60_000 } },
      subidasFeitas: { '1150': 519 },
    })
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    expect(await pane.find({ text: /^✓ 1 no ar$/ })).toBeTruthy()
    for (const t of [/^22 min$/, /^5 min$/, /^4 min$/, /^9 min$/]) expect(await pane.find({ text: t })).toBeTruthy()
  })

  test(`bloco "Precisa de você" junta migration, Onda parada, Fatia humana e CI vermelho (${surface})`, async ($, on) => {
    await montar($, on, { ondasEstado: [{ id: 'hsm-ouv-onda2', estado: 'erro', prd: 1128, texto: 'health falhou' }] })
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    expect(await pane.find({ text: /^Precisa de você/ })).toBeTruthy()
    expect(await pane.find({ text: /migration 117 cole no Studio/ })).toBeTruthy()
    // o motivo vai inteiro na linha de baixo, sem a URL no meio
    expect(await pane.find({ text: / quebrou$/ })).toBeTruthy()
    expect(await pane.find({ text: /^health falhou$/ })).toBeTruthy()
    expect(await pane.find({ text: /CI vermelho · / })).toBeTruthy()
    expect(await pane.find({ text: /Nada espera você/ })).toBeUndefined()
  })

  test(`painel numera as ondas pelo terminal e mostra a fala da sessão (${surface})`, async ($, on) => {
    const agentes = [{ ...COLETA.agentes[0]!, fala: { texto: 'Aguardando o CI do PR #1150.\nDetalhe que não aparece.', em: AGORA - 4 * 60_000 } }]
    await montar($, on, { passagens: PASSAGENS, agentes })
    await $.command.run({ command: 'ondas', args: 'detalhe', origin: 'user', presentation: 'text' })
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    expect(await pane.find({ text: /Onda 1 · onda-ia-onda1 · andando/ })).toBeTruthy()
    expect(await pane.find({ text: /Onda 2 · na fila · passagem escrita/ })).toBeTruthy()
    expect(await pane.find({ text: /Onda 3 · parada · passagem: ainda não/ })).toBeTruthy()
    expect(await pane.find({ text: /💬 Aguardando o CI do PR #1150\. · há 4 min/ })).toBeTruthy()
    expect(await pane.find({ text: /Detalhe que não aparece/ })).toBeUndefined()
  })

  test(`issue sem PRD aparece no grupo "Sem PRD" com PR, CI e esteira (${surface})`, async ($, on) => {
    await montar($, on, SEM_PRD_NA_COLETA)
    const pane = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'Pane', requestId: 'ondas', props: {} as any })
    expect(await pane.find({ text: /^Sem PRD$/ })).toBeTruthy()
    expect(await pane.find({ text: /Onda 1 · onda-b-onda1 · andando/ })).toBeTruthy()
    expect(await pane.find({ text: /PR #1203/ })).toBeUndefined()
    expect(await pane.find({ text: /OCR da página digitalizada/ })).toBeTruthy()
    expect(await pane.find({ text: /CI ✓/ })).toBeTruthy()
    expect(await pane.find({ text: /em andamento/ })).toBeTruthy()
  })

  test(`faixa acima do prompt avisa a migration com o link (${surface})`, async ($, on) => {
    await montar($, on)
    const faixa = await $.ui.mount({ plugin: 'hr-ondas', surface, component: 'AbovePrompt', props: { hasSurvey: false } as any })
    expect(await faixa.find({ text: /migration 117 esperando você: cole no Studio/ })).toBeTruthy()
  })
}

test('copiar SQL põe o arquivo inteiro no clipboard, confere e nunca aponta para o VS Code', async ($, on) => {
  const SQL = '-- 117\nCREATE TABLE x (\n  id int\n);\n\nSELECT 1;\n'
  const lidos: string[] = []
  const copiados: string[] = []
  const avisos: string[] = []
  mock.clock(on, { now: AGORA })
  on('process.run', (_$: any, e: any) => ({
    value: e.argv[0] === '/usr/bin/pbpaste'
      ? { exitCode: 0, stdout: copiados.at(-1) ?? '', stderr: '' }
      : { exitCode: 0, stdout: JSON.stringify(COLETA), stderr: '' },
  }))
  on('fs.read', (_$: any, e: any) => {
    lidos.push(e.path)
    return { value: SQL }
  })
  on('ui.copy', (_$: any, e: any) => {
    copiados.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', (_$: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', () => null)
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' })
  const pane = await $.ui.mount({ plugin: 'hr-ondas', surface: 'terminal', component: 'Pane', requestId: 'ondas', props: {} as any })
  expect(await pane.find({ text: /VS Code/ })).toBeUndefined()
  await pane.press({ key: 'copiar-117' })
  expect(lidos).toEqual(['/tmp/fechar_onda/onda-ia-onda1/117_contas_medicas_ia.sql'])
  expect(copiados).toEqual([SQL])
  expect(avisos.some(a => /Migration 117 copiada inteira \(210 linhas\)/.test(a))).toBe(true)
})

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

test('cor da duração: amarelo no p75, vermelho no p90, etapa sem teto sem cor', () => {
  expect(corDaDuracao('onda-implementador', 29 * 60_000)).toBeUndefined()
  expect(corDaDuracao('onda-implementador', 30 * 60_000)).toBe('warning')
  expect(corDaDuracao('onda-implementador', 35 * 60_000)).toBe('error')
  expect(corDaDuracao('CI', 12 * 60_000)).toBe('error')
  expect(corDaDuracao('subida', 10 * 60_000)).toBe('warning')
  expect(corDaDuracao('no ar', 999 * 60_000)).toBeUndefined()
})

test('rótulo do shell: subida e CI pelo padrão, o resto pela description', () => {
  const subida = 'cd /r; python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs 1171 1169 --sessao onda-gestao-onda2 > log'
  expect(rotuloDoShell('Roda a subida', subida)).toBe('subida #1171 #1169')
  expect(rotuloDoShell('Simula a subida', `${subida} --dry-run`)).toBe('Simula a subida')
  // o comando citado num comentário (heredoc) não é subida
  expect(rotuloDoShell('Dá baixa na #1142', "cat > b.md <<'EOF'\nrode `fechar_onda.py --prs 1178`\nEOF")).toBe('Dá baixa na #1142')
  expect(rotuloDoShell('', 'gh pr checks 1169 --watch')).toBe('esperando o CI do PR #1169')
  expect(rotuloDoShell('', 'gh run watch 123')).toBe('esperando o CI')
  expect(rotuloDoShell('Comenta o relatório da onda no PRD 1129', 'gh issue comment 1129')).toBe('Comenta o relatório da onda no PRD 1129')
  expect(rotuloDoShell('', 'cd /repo; git status --short')).toBe('git status --short')
})

test('esteira com tempos: soma dos agentes, CI pelos checks, subida em curso; migration pendente tira a cor', () => {
  const prd = comEm(COLETA).os!.prds.find(p => p.n === 1128)!
  const i = prd.issues.find(x => x.n === 1132)!
  const ags = [
    sub({ id: 'imp', descricao: 'Implementa #1132', terminou: true, inicio: AGORA - 40 * 60_000, fim: AGORA - 5 * 60_000 }),
    sub({ id: 'cor', tipo: 'hr-corretor', descricao: 'Corrige PR 1150', inicio: AGORA - 3 * 60_000, fim: AGORA - 60_000 }),
  ]
  const subida = { sessao: 'onda-ia-onda1', prs: [1150], inicio: AGORA - 11 * 60_000, fim: null }
  const por = Object.fromEntries(etapas(i, ags, AGORA, { ci: { inicio: AGORA - 9 * 60_000, fim: null }, subida }).map(s => [s.nome, s]))
  expect(por.implementar).toEqual({ nome: 'implementar', estado: 'feita', ms: 35 * 60_000, cor: 'error' })
  expect(por.CI).toEqual({ nome: 'CI', estado: 'falhou', ms: 9 * 60_000, cor: 'warning' })
  expect(por.corrigir).toEqual({ nome: 'corrigir', estado: 'agora', ms: 3 * 60_000, cor: undefined })
  expect(por.subida).toEqual({ nome: 'subida', estado: 'agora', ms: 11 * 60_000, cor: 'warning' })
  const esperandoStudio = etapas(i, ags, AGORA, { subida, migrationPendente: true }).find(s => s.nome === 'subida')!
  expect(esperandoStudio.ms).toBe(11 * 60_000)
  expect(esperandoStudio.cor).toBeUndefined()
  // sem checks nem subida, a etapa não inventa tempo
  expect(etapas(i, [], AGORA).map(s => s.ms)).toEqual([undefined, undefined, undefined, undefined, undefined])
})

test('agentes onda-* contam como hr-*; o histórico entra sem repetir o vivo; a subida encerrada vem do registro', () => {
  const c = comEm(COLETA)
  const prd = c.os!.prds.find(p => p.n === 1128)!
  const i = { ...prd.issues.find(x => x.n === 1132)!, fase: 'em_producao' as const, estado: 'CLOSED' }
  const vivo = sub({ id: 'imp', tipo: 'onda-implementador', descricao: 'Implementa issue #1132', terminou: true, inicio: AGORA - 50 * 60_000, fim: AGORA - 20 * 60_000 })
  const historico = [
    { ...vivo, fim: AGORA - 45 * 60_000 }, // o mesmo arquivo lido antes: vale o vivo
    sub({ id: 'rev', tipo: 'onda-revisor', descricao: 'Revisor PR #1150', terminou: true, inicio: AGORA - 15 * 60_000, fim: AGORA - 13 * 60_000 }),
    sub({ id: 'cor', tipo: 'onda-corretor', descricao: 'Corrige must-fix do PR 1150', terminou: true, inicio: AGORA - 12 * 60_000, fim: AGORA - 11 * 60_000 - 20_000 }),
    sub({ id: 'outro', tipo: 'onda-revisor', descricao: 'Revisor PR #9999', terminou: true }),
  ]
  const ags = agentesDaFatia({ ...c, historico }, prd, [vivo], 1132)
  expect(ags.map(a => a.id)).toEqual(['imp', 'rev', 'cor'])
  const lista = etapas(i, ags, AGORA, { ci: { inicio: AGORA - 19 * 60_000, fim: AGORA - 16 * 60_000 }, subidaS: 519 })
  expect(temposDaFatia(lista).map(s => `${s.nome} ${tempoCurto(s.ms)}`)).toEqual([
    'implementar 30 min', 'CI 3 min', 'revisar 2 min', 'corrigir 40 s', 'subida 9 min',
  ])
  expect(lista.map(s => s.estado)).toEqual(['feita', 'feita', 'feita', 'feita', 'feita', 'feita'])
})

test('botão resolver: lança a sessão daquele item pelo resolver.sh, com o pedido pela entrada padrão', async ($, on) => {
  const chamadas: { argv: string[]; stdin?: string }[] = []
  const avisos: string[] = []
  mock.clock(on, { now: AGORA })
  on('process.run', (_$: any, e: any) => {
    const argv = [...e.argv] as string[]
    if (argv[1]?.endsWith('resolver.sh')) {
      chamadas.push({ argv: argv.slice(2), stdin: e.init?.stdin })
      return { value: { exitCode: 0, stdout: 'Sessão acompanhar-1137 aberta: entre nela no Claude Agents\n', stderr: '' } }
    }
    const prd = COLETA.os.prds.find(p => p.n === 1128)!
    const os = { ...COLETA.os, prds: [{ ...prd, issues: prd.issues.map(i => (i.n === 1137 ? { ...i, fase: 'humana' } : i)) }] }
    return { value: { exitCode: 0, stdout: JSON.stringify({ ...COLETA, os, migrations: [] }), stderr: '' } }
  })
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_$: any, e: any) => { avisos.push(e.text ?? e); return { value: undefined } })
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', (_$: any, e: any, next: any) => (e.component === 'Pane' ? null : next(e)))
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' } as any)
  const pane = await $.ui.mount({ plugin: 'hr-ondas', surface: 'terminal', component: 'Pane', requestId: 'ondas', props: {} as any })
  expect(await pane.find({ text: /resolver abre no Claude Agents uma sessão só daquele item/ })).toBeTruthy()
  await pane.press({ key: 'resolver-i1137' })
  expect(chamadas).toHaveLength(1)
  expect(chamadas[0]!.argv).toEqual(['acompanhar-1137'])
  expect(chamadas[0]!.stdin).toMatch(/A issue #1137 é humana/)
  expect(avisos.at(-1)).toMatch(/Sessão acompanhar-1137 aberta/)
  await pane.unmount()
})

test('atividade da sessão: subida em curso ganha do shell; tempo da onda do primeiro agente até agora', () => {
  const c = comEm({ ...COLETA, subAgentes: AGENTES, subidas: SUBIDA_EM_CURSO } as typeof COLETA)
  const s = { ...c.agentes[0]!, shell: { descricao: 'Comenta', comando: 'gh', inicio: AGORA - 5000 } }
  expect(atividadeDaSessao(s, c)).toEqual({ texto: 'subida #1150', inicio: AGORA - 120_000 })
  expect(atividadeDaSessao(s, { ...c, subidas: [] })).toEqual({ texto: 'Comenta', inicio: AGORA - 5000 })
  expect(atividadeDaSessao({ ...s, shell: null }, { ...c, subidas: [] })).toBeNull()
  expect(subidaDoPr(c, 1150)?.inicio).toBe(AGORA - 120_000)
  expect(subidaDoPr(c, null)).toBeUndefined()
  const prd = c.os!.prds.find(p => p.n === 1128)!
  const onda1 = prd.ondas[0]!.map(n => prd.issues.find(i => i.n === n)!)
  expect(duracaoDaOnda(onda1, AGENTES, prd, AGORA)).toBe(600_000) // o revisor ainda trabalha: até agora
  expect(duracaoDaOnda(onda1, [], prd, AGORA)).toBeNull()
})

test('Hospital OS sem resposta: o painel guarda o último retrato e avisa a idade', async ($, on) => {
  let coletas = 0
  const relogio = mock.clock(on, { now: AGORA })
  on('process.run', () => {
    coletas += 1
    return { value: { exitCode: 0, stdout: JSON.stringify(coletas === 1 ? COLETA : { ...COLETA, os: null }), stderr: '' } }
  })
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  on('ui.render', () => null)
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' })
  await relogio.advance(3 * 60_000)
  await $.command.run({ command: 'ondas', args: '', origin: 'user', presentation: 'text' })
  expect(coletas).toBe(2)
  const pane = await $.ui.mount({ plugin: 'hr-ondas', surface: 'terminal', component: 'Pane', requestId: 'ondas', props: {} as any })
  expect(await pane.find({ text: /PedroOS sem resposta, PRDs de há 3 min/ })).toBeTruthy()
  expect(await pane.find({ text: /PRD #1128/ })).toBeTruthy()
  expect(await pane.find({ text: /fora do ar/ })).toBeUndefined()
})

test('assinatura muda quando agente termina, subida fecha ou migration chega; não muda com o shell', () => {
  const base = { agentes: [{ nome: 'onda-x', status: 'busy', estado: null, inicio: 0 }], subAgentes: AGENTES, subidas: [], migrations: [] }
  const a = assinatura(base)
  expect(assinatura({ ...base, agentes: [{ ...base.agentes[0]!, shell: { descricao: 'x', comando: 'ls', inicio: 1 } }] })).toBe(a)
  expect(assinatura({ ...base, subAgentes: AGENTES.map(x => ({ ...x, terminou: true })) })).not.toBe(a)
  expect(assinatura({ ...base, subidas: [{ sessao: 'onda-x', prs: [1], inicio: 0, fim: 5 }] })).not.toBe(a)
  expect(assinatura({ ...base, agentes: [{ ...base.agentes[0]!, status: 'idle' }] })).not.toBe(a)
})

test('relógio coleta sem ir ao GitHub; evento do workflow pede coleta fresca uma vez', async ($, on) => {
  const chamadas: string[][] = []
  let terminou = false
  const relogio = mock.clock(on, { now: AGORA })
  on('process.run', (_$: any, e: any) => {
    chamadas.push([...e.argv])
    const subAgentes = [{ ...AGENTES[1]!, terminou }]
    return { value: { exitCode: 0, stdout: JSON.stringify({ ...COLETA, subAgentes }), stderr: '' } }
  })
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('session.start', () => ({ cwd: '/repo' }))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: false })
  await relogio.advance(10_001)
  const frescas = () => chamadas.filter(c => JSON.stringify(c).includes('--fresco')).length
  expect(chamadas.length).toBe(2)
  expect(frescas()).toBe(0)
  terminou = true // o revisor terminou: evento
  await relogio.advance(10_000)
  expect(frescas()).toBe(1)
  await relogio.advance(10_000) // nada mudou de novo
  expect(frescas()).toBe(1)
})

test('/ondas todos pede o OS inteiro; /ondas ativos volta ao recorte', async ($, on) => {
  const chamadas: string[][] = []
  mock.clock(on, { now: AGORA })
  on('process.run', (_$: any, e: any) => {
    chamadas.push([...e.argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(COLETA), stderr: '' } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: '' }))
  await $.command.run({ command: 'ondas', args: 'todos', origin: 'user', presentation: 'text' })
  await $.command.run({ command: 'ondas', args: 'ativos', origin: 'user', presentation: 'text' })
  expect(chamadas.map(c => c.slice(2))).toEqual([['--fresco', '--todos'], ['--fresco']])
})

test('precisa de você: Onda em erro primeiro, depois a que espera, a Fatia humana e o CI vermelho, cada um com a sua sessão', () => {
  const c = comEm(COLETA)
  const prd = c.os!.prds.find(p => p.n === 1128)!
  const humana = { ...prd.issues.find(i => i.n === 1137)!, fase: 'humana' as const }
  const os = { ...c.os!, prds: [{ ...prd, issues: prd.issues.map(i => (i.n === 1137 ? humana : i)) }] }
  const lista = precisaDeVoce({
    ...c,
    os,
    ondasEstado: [
      { id: 'a-onda1', estado: 'pronto-para-voce', prd: 1128, texto: null },
      { id: 'b-onda2', estado: 'erro', prd: null, texto: 'rollback' },
    ],
  })
  const textos = lista.map(x => `${x.rotulo} ${x.texto}`)
  expect(textos.slice(0, 2)).toEqual(['Onda b-onda2 quebrou', 'Onda a-onda1 espera você'])
  expect(lista[0]!.detalhe).toBe('rollback')
  expect(textos.slice(2).sort()).toEqual([
    `#1132 CI vermelho · ${prd.issues.find(i => i.n === 1132)!.titulo}`,
    `#1137 é sua · ${humana.titulo}`,
  ])
  // cada item abre a sua sessão: a Onda pelo Fechar a Onda, a humana pelo acompanhar, o CI vermelho pelo conserto
  expect(lista.slice(0, 2).map(x => x.sessao?.nome)).toEqual(['fechar-b-onda2', 'fechar-a-onda1'])
  expect(lista.slice(2).map(x => x.sessao?.nome).sort()).toEqual(['acompanhar-1137', 'ci-pr-1150'])
  expect(lista[0]!.sessao!.prompt).toMatch(/estado_onda\.py ler --sessao b --onda 2/)
  expect(lista[0]!.sessao!.prompt).toMatch(/estado_onda\.py resolvido --sessao b --onda 2/)
  expect(lista.find(x => x.rotulo === '#1137')!.sessao!.prompt).toMatch(/gh issue view 1137 --comments[\s\S]*feche/)
  expect(lista.find(x => x.rotulo === '#1132')!.sessao!.prompt).toMatch(/PR #1150 da issue #1132 está com o CI vermelho/)
  // a sessão da própria Onda viva: o botão só traz o Claude Agents
  expect(lista[0]!.sessao!.viva).toBeNull()
  expect(pedidoDaOnda({ id: 'b-onda2', estado: 'erro', prd: null, texto: null }, ['b-onda2'])!.viva).toBe('b-onda2')
  // linhagem e número do Estado da Onda valem mais que o nome; nome que não vira comando, sem sessão
  expect(pedidoDaOnda({ id: 'x-onda9', estado: 'erro', prd: null, texto: null, sessao: 'hsm-x', onda: 9 }, [])!.prompt).toMatch(/--sessao hsm-x --onda 9/)
  expect(pedidoDaOnda({ id: 'a; rm -rf ~', estado: 'erro', prd: null, texto: null }, [])).toBeNull()
  // nada pendente: lista vazia, e o painel diz "Nada espera você"
  expect(precisaDeVoce({ ...c, os: { ...c.os!, prds: [] } })).toEqual([])
})
