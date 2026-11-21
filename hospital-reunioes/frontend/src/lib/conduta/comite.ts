/**
 * O lado do Comitê do Canal de Conduta (issue #1824): os tipos que a API
 * devolve, os rótulos da tela e a chamada autenticada às rotas do módulo.
 *
 * Quem decide o que cada pessoa pode fazer é o servidor: a caixa "O QUE FAZER
 * AGORA" chega pronta, com o motivo do botão bloqueado.
 */
import { createClient } from "@/lib/supabase/client";

export type Rito = "encaminhamento" | "rapido" | "completo";
export type Escopo = "dentro" | "fora" | "misto";
export type Situacao = "em_triagem" | "em_andamento" | "encerrado";

export interface ItemDaMinhaVez {
  id: string;
  protocolo: string;
  etapa: string | null;
  rito: Rito | null;
  acao: string;
  prazo_em: string | null;
  prazo_vencido: boolean;
  faltam_dias: number | null;
}

export interface CasoDaLista {
  id: string;
  protocolo: string;
  etapa: string | null;
  rito: Rito | null;
  categoria: string | null;
  situacao: Situacao;
  prazo_em: string | null;
  prazo_vencido: boolean;
  faltam_dias: number | null;
}

export interface Caixa {
  frase: string;
  botao: string | null;
  como_fazer: string[];
  acao: string | null;
  bloqueio: string | null;
}

export interface Contestacao {
  escopo: Escopo;
  categoria: string;
  rito: Rito;
  destino: string | null;
  motivo: string;
  votos: number;
  resultado: "mantida" | "acatada" | null;
}

export interface MembroDoCaso {
  id: string;
  nome: string | null;
  papel: string;
}

export interface ContestacaoDeParticipacao {
  id: string;
  contestado: string | null;
  motivo: string;
  votos: number;
  resultado: "confirmada" | "rejeitada" | null;
  pode_decidir: boolean;
}

export interface Citado {
  id: string;
  nome: string | null;
  ligado: boolean;
}

export interface CasoAberto extends CasoDaLista {
  membros_do_caso: MembroDoCaso[];
  pode_contestar_participacao: boolean;
  contestacoes_de_participacao: ContestacaoDeParticipacao[];
  citados: Citado[];
  relato: string;
  escopo: Escopo | null;
  destino: string | null;
  papel: string | null;
  trilho: { nome: string; estado: "concluida" | "atual" | "pendente" }[];
  o_que_fazer_agora: Caixa;
  contestacao: Contestacao | null;
  pode_contestar: boolean;
  prorrogacao: { justificativa: string | null; bloqueio: string | null } | null;
  orientacao: string | null;
  triagem_em: string | null;
  conferida_em: string | null;
  encerrado_em: string | null;
  desfecho: string | null;
}

export const RITOS: { valor: Rito; rotulo: string; prazo: string }[] = [
  { valor: "encaminhamento", rotulo: "Encaminhamento", prazo: "5 dias úteis" },
  { valor: "rapido", rotulo: "Rápido", prazo: "20 dias corridos" },
  { valor: "completo", rotulo: "Completo", prazo: "30 dias corridos, prorrogável uma vez" },
];

export const ESCOPOS: { valor: Escopo; rotulo: string }[] = [
  { valor: "dentro", rotulo: "Dentro do canal" },
  { valor: "fora", rotulo: "Fora do canal" },
  { valor: "misto", rotulo: "Misto" },
];

export const CATEGORIAS: { valor: string; rotulo: string }[] = [
  { valor: "A", rotulo: "A. Conduta e relações" },
  { valor: "B", rotulo: "B. Patrimônio" },
  { valor: "C", rotulo: "C. Integridade nos negócios" },
  { valor: "D", rotulo: "D. Registros e informação" },
  { valor: "E", rotulo: "E. Segurança e conformidade" },
  { valor: "F", rotulo: "F. Não sei classificar" },
];

export const DESTINOS: { valor: string; rotulo: string }[] = [
  { valor: "dp", rotulo: "Departamento Pessoal" },
  { valor: "ouvidoria", rotulo: "Ouvidoria" },
  { valor: "nsp", rotulo: "Núcleo de Segurança do Paciente" },
  { valor: "gestor", rotulo: "Liderança direta ou DP" },
];

/** Os motivos de impedimento da especificação (seção 3.3). */
export const MOTIVOS_DE_IMPEDIMENTO: { valor: string; rotulo: string }[] = [
  { valor: "parte", rotulo: "Parte do caso" },
  { valor: "chefia_direta", rotulo: "Chefia direta de envolvido" },
  { valor: "parentesco", rotulo: "Parentesco" },
  { valor: "relacao_pessoal", rotulo: "Relação pessoal" },
  { valor: "interesse", rotulo: "Interesse no resultado" },
];

export const SITUACOES:{ valor: Situacao; rotulo: string }[] = [
  { valor: "em_triagem", rotulo: "Em triagem" },
  { valor: "em_andamento", rotulo: "Em andamento" },
  { valor: "encerrado", rotulo: "Encerrado" },
];

const ETAPAS: Record<string, string> = {
  triagem: "Triagem",
  contestada: "Triagem contestada",
  encaminhamento: "Encaminhamento",
  apuracao: "Apuração",
  encerrado: "Encerrado",
};

export function rotuloDaEtapa(etapa: string | null): string {
  return ETAPAS[etapa ?? "triagem"] ?? etapa ?? "Triagem";
}

export function rotuloDoRito(rito: Rito | null): string {
  return RITOS.find((r) => r.valor === rito)?.rotulo ?? "Rito ainda não definido";
}

/** "Faltam 12 dias", "Vence hoje", "Venceu há 3 dias". */
export function textoDoPrazo(faltam: number | null, encerrado = false): string {
  if (encerrado) return "Encerrado";
  if (faltam === null) return "Prazo depois da triagem";
  if (faltam > 1) return `Faltam ${faltam} dias`;
  if (faltam === 1) return "Falta 1 dia";
  if (faltam === 0) return "Vence hoje";
  return faltam === -1 ? "Venceu há 1 dia" : `Venceu há ${-faltam} dias`;
}

export async function chamarComite<T>(caminho: string, opcoes: { method?: string; body?: unknown } = {}): Promise<T> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  const headers: Record<string, string> = { Authorization: `Bearer ${session?.access_token ?? ""}` };
  if (opcoes.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/comite-de-conduta${caminho}`, {
    method: opcoes.method ?? "GET",
    headers,
    body: opcoes.body !== undefined ? JSON.stringify(opcoes.body) : undefined,
  });
  if (!res.ok) {
    const corpo = await res.json().catch(() => null);
    const detalhe = typeof corpo?.detail === "string" ? corpo.detail : "Não foi possível concluir. Tente de novo.";
    throw new Error(detalhe);
  }
  return (await res.json()) as T;
}
