/**
 * O vocabulário da Demanda, do lado da tela (issue #637, PRD #634, ADR 0050).
 *
 * Só dado e função pura: rótulos, a máquina de estados que desenha os botões
 * de mover, e as duas contas do card (idade e atraso). Quem decide de verdade
 * é o backend, que responde 422 na transição proibida; esta tabela existe para
 * a tela não OFERECER um caminho que ela sabe que não existe.
 */

/** O prefixo da API da aba. */
export const BASE_TECNOLOGIA = "/api/admin/tecnologia";

/** A mesma frase em todo caminho de rede da aba, carregar e salvar. */
export const FALHA_DE_CONEXAO = "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";

/**
 * O motivo da recusa, dito pelo servidor.
 *
 * A tela não inventa causa: quem sabe por que recusou (Produto sem dono,
 * transição que não existe, responsável sem acesso) é a API, e é a frase dela
 * que a pessoa lê.
 */
export async function motivoDaRecusa(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
    if (corpo?.detail) return JSON.stringify(corpo.detail);
  } catch {
    // Resposta sem corpo JSON: sobra o status.
  }
  return `Não foi possível salvar (${resposta.status}).`;
}

/** O Produto como as escolhas da Demanda o veem. */
export type ProdutoDaEscolha = { id: string; nome: string; ativo: boolean };

/** Quem tem acesso à aba: dono de Produto, responsável e, adiante, @menção. */
export type PessoaDaAba = { id: string; nome_completo: string };

export type EstadoDemanda = "nova" | "em_andamento" | "aguardando" | "concluida" | "cancelada";

export type TipoDemanda =
  | "decisao"
  | "informacao"
  | "terceiro"
  | "ajuste"
  | "novo"
  | "defeito"
  | "consultoria";

export type PrioridadeDemanda = "baixa" | "normal" | "alta";

export type Demanda = {
  id: string;
  titulo: string;
  descricao: string | null;
  tipo: TipoDemanda;
  produto_id: string;
  produto_nome: string | null;
  estado: EstadoDemanda;
  responsavel_id: string | null;
  responsavel_nome: string | null;
  autor_id: string | null;
  prioridade: PrioridadeDemanda;
  prazo: string | null;
  criado_em: string | null;
  concluida_em: string | null;
  cancelada_em: string | null;
};

export type LinhaDaConversa = {
  id: string;
  autor_id: string | null;
  autor_nome: string | null;
  linha: string;
  texto: string;
  movimento_campo: string | null;
  criado_em: string | null;
};

/** A ordem das colunas no Quadro. */
export const ESTADOS: EstadoDemanda[] = ["nova", "em_andamento", "aguardando", "concluida", "cancelada"];

export const ESTADO_ROTULO: Record<EstadoDemanda, string> = {
  nova: "Nova",
  em_andamento: "Em andamento",
  aguardando: "Aguardando",
  concluida: "Concluída",
  cancelada: "Cancelada",
};

/**
 * As duas colunas que nascem recolhidas.
 *
 * O contador continua à vista: recolher é dar espaço às colunas vivas, não
 * esconder o que foi fechado (PRD #634, história 24).
 */
export const COLUNAS_RECOLHIDAS: EstadoDemanda[] = ["concluida", "cancelada"];

/** Espelho da tabela do backend (`app/services/tecnologia.py`). */
export const TRANSICOES: Record<EstadoDemanda, EstadoDemanda[]> = {
  nova: ["em_andamento", "aguardando", "concluida", "cancelada"],
  em_andamento: ["aguardando", "concluida", "cancelada"],
  aguardando: ["em_andamento", "concluida", "cancelada"],
  concluida: ["em_andamento"],
  cancelada: ["em_andamento"],
};

export function destinosDe(estado: EstadoDemanda): EstadoDemanda[] {
  return TRANSICOES[estado] ?? [];
}

export const TIPOS: TipoDemanda[] = [
  "decisao",
  "informacao",
  "terceiro",
  "ajuste",
  "novo",
  "defeito",
  "consultoria",
];

export const TIPO_ROTULO: Record<TipoDemanda, string> = {
  decisao: "Decisão",
  informacao: "Informação",
  terceiro: "Terceiro",
  ajuste: "Ajuste",
  novo: "Novo",
  defeito: "Defeito",
  consultoria: "Consultoria",
};

export const PRIORIDADES: PrioridadeDemanda[] = ["baixa", "normal", "alta"];

export const PRIORIDADE_ROTULO: Record<PrioridadeDemanda, string> = {
  baixa: "Baixa",
  normal: "Normal",
  alta: "Alta",
};

/** A partir daqui a idade vira vermelha (ADR 0050, decisão 5). */
export const IDADE_VERMELHA_A_PARTIR_DE = 14;

/** Quantos dias inteiros a Demanda tem. Data futura conta como zero. */
export function idadeEmDias(criadoEm: string | null, agora: Date = new Date()): number {
  if (!criadoEm) return 0;
  const nascimento = new Date(criadoEm);
  if (Number.isNaN(nascimento.getTime())) return 0;
  const dias = Math.floor((agora.getTime() - nascimento.getTime()) / 86_400_000);
  return dias > 0 ? dias : 0;
}

export function textoDaIdade(dias: number): string {
  if (dias <= 0) return "hoje";
  if (dias === 1) return "há 1 dia";
  return `há ${dias} dias`;
}

/**
 * Prazo vencido é atraso; sem prazo o card só envelhece.
 *
 * A comparação é de DIA, não de instante: o prazo é uma data (`2026-10-01`), e
 * medir por hora marcaria como atrasado, às 9 da manhã, um prazo que vence
 * hoje. O meio-dia é o mesmo truque do painel de Pendências, que tira a
 * diferença de fuso do caminho.
 */
export function estaAtrasado(prazo: string | null, agora: Date = new Date()): boolean {
  if (!prazo) return false;
  const vencimento = new Date(`${prazo}T12:00:00`);
  if (Number.isNaN(vencimento.getTime())) return false;
  const hoje = new Date(agora);
  hoje.setHours(12, 0, 0, 0);
  return vencimento.getTime() < hoje.getTime();
}

/** A data do prazo como a gente lê. */
export function prazoLegivel(prazo: string): string {
  return new Date(`${prazo}T12:00:00`).toLocaleDateString("pt-BR");
}

/** Data e hora da linha da Conversa. */
export function momentoLegivel(quando: string | null): string {
  if (!quando) return "";
  const d = new Date(quando);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
