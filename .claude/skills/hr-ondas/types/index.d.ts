export type Fase =
  | 'triagem' | 'fila' | 'bloqueada' | 'em_andamento' | 'pr_aberto'
  | 'mergeada' | 'em_producao' | 'humana' | 'encerrada_sem_pr'

export type Issue = {
  n: number
  titulo: string
  estado: string
  url: string
  fase: Fase
  pr: number | null
  ci: string | null
  veredito: string | null
  conflito: boolean
  versao: string | null
  por: number[]
}

export type Prd = { n: number; titulo: string; ondas: number[][]; issues: Issue[] }

export type Agente = { nome: string; status: string; estado: string | null; inicio: number; sessao?: string }

/** Sub-agente de uma sessão de onda (hr-implementador, hr-revisor, hr-corretor). */
export type SubAgente = {
  sessao: string
  id: string
  tipo: string
  descricao: string
  esforco: string | null
  modelo: string | null
  inicio: number
  fim: number
  ctx: number
  terminou: boolean
}

export type Migration = {
  numero: number
  arquivo: string
  caminho: string
  sessao: string
  mtime: number
  linhas: number
}

export type Coleta = {
  os: { repo: string; prds: Prd[] } | null
  agentes: Agente[]
  prdSessoes: Record<string, number>
  subAgentes?: SubAgente[]
  migrations: Migration[]
  aplicada: number | null
  em: number
}

export type EsperaCi = { pr: number | null; url: string }

declare module 'claude-code' {
  interface PluginState {
    'hr-ondas': {
      coleta: Coleta | null
      erro: string | null
      todos: boolean
      esperaCi: EsperaCi | null
    }
  }
}
