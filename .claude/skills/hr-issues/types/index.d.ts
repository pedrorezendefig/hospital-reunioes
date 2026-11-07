/** Uma issue como o `minhas_issues.py --json` a entrega. */
export type Item = {
  n: number
  titulo: string
  /** "triagem", "fila de agente", "humana", "em andamento", "PR #N", "entregue dd/mm", "não vai ser feita" */
  fase: string
  selos: string[]
  quem: string[]
  fechada: boolean
}

export type Fatia = Item & { travadaPor: number[] }

export type Prd = { n: number; titulo: string; fatias: Fatia[] }

export type Caixa = 'triagem' | 'fila' | 'humana' | 'andamento' | 'pr' | 'entregue'

export type Visao = {
  login: string
  repo: string | null
  agora: string
  semaforo: { cor: 'verde' | 'amarelo' | 'vermelho'; detalhe: string }
  abertas: number
  caminho: Record<Caixa, Item[]>
  prds: Prd[]
  tecnologia: { bug: Item[]; melhoria: Item[] }
  janelaDias: number
  plano: string[]
}

/** Uma sessão que o clique num número abriu (hooks/lancar.sh). */
export type Lancamento = {
  tipo: 'prd' | 'issue' | 'humana' | 'triagem'
  n: number
  nome: string
  estado: 'abrindo' | 'aberta' | 'falhou'
  /** A linha do `claude --bg` (id e nome), ou o erro. */
  detalhe: string
  em: number
}

declare module 'claude-code' {
  interface PluginState {
    'hr-issues': {
      visao: Visao | null
      erro: string | null
      /** Hora (ms) em que a visão chegou. */
      em: number | null
      /** Sessões abertas pelo clique, por `<tipo>-<n>`: o segundo clique não abre outra. */
      lancadas: Record<string, Lancamento>
    }
  }
}
