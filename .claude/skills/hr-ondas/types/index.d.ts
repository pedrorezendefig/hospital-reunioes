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
  /** Ondas que quebraram ou esperam o humano, pelo Estado da Onda (~/.pedroos/ondas/<slug>). */
  ondasEstado?: EstadoOnda[]
  /** Sub-agentes de toda sessão recente do Projeto, viva ou encerrada (hooks/historico.py); `sessao` é o id. */
  historico?: SubAgente[]
  /** Segundos de cada subida pelo número do PR, do docs/spec/deploy/history.json da main. */
  subidasFeitas?: Record<string, number>
  /** As migrations do .claude/fluxo.json: null quando o Projeto não tem migration para o humano aplicar. */
  migracoes?: { pasta?: string; aplicar?: string; editor?: string } | null
  /** dono/nome do repositório, pelo remote origin */
  repo?: string | null
}

/**
 * Uma Onda em `erro` ou `pronto-para-voce`, com o texto do último evento daquele estado
 * e as issues dela que ficaram em `baixa`.
 */
export type EstadoOnda = {
  id: string
  estado: 'erro' | 'pronto-para-voce'
  prd: number | null
  texto: string | null
  baixas?: number[]
  /** a linhagem da sessão ("hsm-conector") e o número da Onda, como o estado_onda.py gravou */
  sessao?: string | null
  onda?: number | null
}

/** Título e estado de um card que uma Onda cita e o OS não traz (PRD fechado, issue solta). */
export type CardCitado = { titulo: string; aberto: boolean; em: number }

/** Algo que a sessão disparou e segue rodando: shell em primeiro ou segundo plano, Monitor, agente. */
export type Tarefa = {
  /** id do tool_use que a disparou; a task-notification o cita em <tool-use-id> */
  id: string
  tipo: 'shell' | 'shell-bg' | 'monitor' | 'agente'
  descricao: string
  comando: string | null
  /** subagent_type do agente */
  agente: string | null
  issue: number | null
  pr: number | null
  inicio: number
  /** texto do tool_result, onde a TaskStop acha o task-id */
  recibo: string | null
}

/** Uma Fatia que a sessão de onda está levando. */
export type FatiaDaFaixa = {
  issue: number
  pr: number | null
  /** status do estado_onda.py: fila, implementando, revisao, correcao, verde, baixa, mergeado */
  status: string | null
  /** correções que contam tentativa (conflito com PR irmão não conta) */
  tentativas: number
  veredito: 'LIMPO' | 'MUST-FIX' | null
}

/** A checagem da linha "Sessão: pode encerrar", feita no fim de cada turno. */
export type Encerrar = { abertos: number[]; mergeados: number[]; semCommit: number; worktree: string | null }

/** A fase desta sessão na esteira, inferida do que ela chama e escreve. */
export type Faixa = {
  /** a última skill da esteira que a sessão chamou */
  skill: string | null
  rodada: number | null
  /** primeira e última pergunta (P) da rodada */
  perguntas: [number, number] | null
  porta: string | null
  tarefas: Tarefa[]
  fatias: FatiaDaFaixa[]
  /** "espera você" que a onda gravou no estado_onda.py e ainda não resolveu */
  paradas: string[]
  /** PRs que a sessão abriu (gh pr create) ou subiu (fechar_onda.py --prs) */
  prs: number[]
  /** fim do último turno, enquanto nenhum outro começou */
  ociosaDesde: number | null
  encerrar: Encerrar | null
}

declare module 'claude-code' {
  interface PluginState {
    'hr-ondas': {
      coleta: Coleta | null
      erro: string | null
      todos: boolean
      /** `/ondas detalhe`: mostra modelo, contexto e fala dos agentes. */
      verDetalhe: boolean
      /** a faixa acima do prompt: a fase desta sessão */
      faixa: Faixa | null
      /** a hora que redesenha os cronômetros da faixa */
      relogio: number
      /** cards citados pelas Ondas que esperam você, buscados no GitHub (chave: número) */
      cards: Record<string, CardCitado>
    }
  }
}
