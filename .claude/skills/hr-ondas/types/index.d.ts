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

/** O Bash em primeiro plano que a sessão da onda está rodando agora. */
export type Shell = { descricao: string; comando: string; inicio: number }

/** A última frase que o orquestrador da sessão escreveu: o status de cada passo da /onda-enxuta. */
export type Fala = { texto: string; em: number }

export type Agente = {
  nome: string
  status: string
  estado: string | null
  inicio: number
  sessao?: string
  shell?: Shell | null
  fala?: Fala | null
}

/** Ondas de uma linhagem de sessão ("onda-gestao"), lidas das passagens: fila-alvo fixa e passagens escritas. */
export type Passagem = { ondas: Record<string, number[]>; escritas: number[] }

/** Uma rodada do fechar_onda.py na sessão: fim null enquanto roda. */
export type Subida = { sessao: string; prs: number[]; inicio: number; fim: number | null }

/** Início e fim dos checks do PR; fim null enquanto algum roda. */
export type Ci = { inicio: number; fim: number | null }

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
  /** `soltas`: issues sem PRD pai em andamento (coletar.sh); o mod as junta no grupo "Sem PRD". */
  os: { repo: string; prds: Prd[]; soltas?: Issue[] } | null
  agentes: Agente[]
  prdSessoes: Record<string, number>
  subAgentes?: SubAgente[]
  subidas?: Subida[]
  ci?: Record<string, Ci>
  migrations: Migration[]
  passagens?: Record<string, Passagem>
  aplicada: number | null
  em: number
  /** Hora da última resposta do Hospital OS; menor que `remotoEm` quando o `os` é o de antes. */
  osEm?: number | null
  /** Hora da última busca no GitHub, OS e health (cache compartilhado entre as sessões). */
  remotoEm?: number | null
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
