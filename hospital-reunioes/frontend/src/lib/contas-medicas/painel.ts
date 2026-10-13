/**
 * O Painel de Contas médicas: tipos e textos (issue #1137, PRD #1128, ADR 0070).
 *
 * O servidor manda cada cartão e cada bloco na própria chave, já somados; a
 * tela desenha o que veio. A faturista recebe só `producao`, e a tela mostra
 * só esse bloco. Um cartão novo (o da coordenação, #1143) é uma chave nova e
 * um componente novo, sem mexer nos outros.
 */

import { dataCurta, reais } from "./guia";

export const ROTA_PAINEL = "/api/contas-medicas/painel";

export type CausaRaiz =
  | "DISPENSACAO"
  | "REGRA_AUTOMATICA"
  | "CADASTRO_PRECO"
  | "REGISTRO_ASSISTENCIAL"
  | "LANCAMENTO_MANUAL";

export type NivelDeEvidencia = "REGISTRADO" | "PRESCRITO" | "PRESCRITO_SN" | "POR_REGRA";

export type TipoDeConta = "parcial" | "unica";

export interface LinhaDeProducao {
  faturista_id: string | null;
  nome: string | null;
  contas: number;
  com_pendencia: number;
  valor_incluido: number;
  valor_retirado: number;
  taxa_nao_procede: number | null;
}

export type IncluidoNaSemana = { semana: string } & Record<NivelDeEvidencia, number>;

export interface Painel {
  semana: { inicio: string; fim: string };
  filtros: { operadoras: { id: string; sigla: string; nome: string }[] };
  nota_media?: { semana: number | null; anterior: number | null };
  contas_concluidas?: { total: number };
  valor_apontado?: { total: number; ja_incluido: number };
  nao_procede?: { linhas: number; de: number; taxa: number | null };
  nota_por_semana?: { semana: string; nota_media: number | null; contas: number }[];
  causa_raiz?: { causa: CausaRaiz; valor: number; percentual: number }[];
  itens_que_faltam?: { codigo: string; descricao: string | null; contas: number; valor: number }[];
  producao: LinhaDeProducao[];
  nivel_evidencia?: IncluidoNaSemana[];
  custo_ia?: { total_usd: number; medio_por_conta_usd: number; contas: number };
  /** Só para quem tem a Conferência da coordenação (#1143). */
  coordenacao?: { valor_incluido: number; lembretes_incluidos: number };
}

export interface FiltrosDoPainel {
  semana: string;
  operadora: string;
  tipo: TipoDeConta | "";
}

export const ROTULO_CAUSA: Record<CausaRaiz, string> = {
  DISPENSACAO: "Dispensação",
  REGRA_AUTOMATICA: "Regra automática",
  CADASTRO_PRECO: "Cadastro e preço",
  REGISTRO_ASSISTENCIAL: "Registro assistencial",
  LANCAMENTO_MANUAL: "Lançamento manual",
};

/** Quem corrige, por causa-raiz (spec do diretor, item 15.2). */
export const QUEM_CORRIGE: Record<CausaRaiz, string> = {
  DISPENSACAO: "farmácia e enfermagem",
  REGRA_AUTOMATICA: "TI e consultoria MV",
  CADASTRO_PRECO: "credenciamento e cadastro",
  REGISTRO_ASSISTENCIAL: "enfermagem e corpo clínico",
  LANCAMENTO_MANUAL: "faturamento",
};

export const NIVEIS: NivelDeEvidencia[] = ["REGISTRADO", "PRESCRITO", "PRESCRITO_SN", "POR_REGRA"];

export const ROTULO_NIVEL: Record<NivelDeEvidencia, string> = {
  REGISTRADO: "Registrado",
  PRESCRITO: "Prescrito",
  PRESCRITO_SN: "Prescrito SN",
  POR_REGRA: "Por regra",
};

export const ROTULO_TIPO: Record<TipoDeConta, string> = {
  parcial: "Parcial",
  unica: "Única",
};

/** A rota com os filtros: a semana sempre; operadora e tipo só quando escolhidos. */
export function rotaDoPainel(filtros: FiltrosDoPainel): string {
  const params = new URLSearchParams({ semana: filtros.semana });
  if (filtros.operadora) params.set("operadora_id", filtros.operadora);
  if (filtros.tipo) params.set("tipo", filtros.tipo);
  return `${ROTA_PAINEL}?${params.toString()}`;
}

/** O dia de hoje no navegador, como data ISO: o servidor acha a segunda da semana. */
export function hojeIso(agora: Date = new Date()): string {
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${agora.getFullYear()}-${mes}-${dia}`;
}

/** "05/10 a 11/10/2026" */
export function rotuloDaSemana(semana: { inicio: string; fim: string }): string {
  return `${dataCurta(semana.inicio)} a ${dataCurta(semana.fim)}/${semana.fim.slice(0, 4)}`;
}

const NOTA = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const PORCENTO = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const DOLAR = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "70" ou "70,5"; sem conta concluída, "sem nota". */
export function textoDaNota(nota: number | null): string {
  return nota === null ? "sem nota" : NOTA.format(nota);
}

/** "R$ 1.212,00" */
export function textoEmReais(valor: number): string {
  return `R$ ${reais(valor)}`;
}

/** "US$ 1,20" */
export function textoEmDolar(valor: number): string {
  return `US$ ${DOLAR.format(valor)}`;
}

/** Uma fração (0,2) em por cento ("20%"); sem linha nenhuma, "sem linhas". */
export function textoDaTaxa(taxa: number | null): string {
  return taxa === null ? "sem linhas" : `${PORCENTO.format(taxa * 100)}%`;
}

/** Um percentual já em pontos (63,5) com o sinal: "63,5%". */
export function textoDoPercentual(percentual: number): string {
  return `${PORCENTO.format(percentual)}%`;
}
