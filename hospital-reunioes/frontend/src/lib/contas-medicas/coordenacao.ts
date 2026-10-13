/**
 * A Conferência da coordenação de Contas médicas: tipos, rotas e textos
 * (issue #1143, PRD #1129, adendo v1.1).
 *
 * O servidor manda os lembretes abertos já agrupados por conta, a do mais
 * antigo primeiro, com os três números somados. Quem não tem a permissão
 * recebe 403 e nenhum dado de cenário ou de lembrete.
 */

import { dataCurta, ROTULO_SITUACAO } from "./guia";

export const ROTA_COORDENACAO = "/api/contas-medicas/coordenacao";
export const ROTA_CENARIOS = `${ROTA_COORDENACAO}/cenarios`;

export type EstadoDaMarcacao = "INCLUIDO" | "NAO_SE_APLICA";

export interface InsumoDoLembrete {
  codigo: string;
  descricao: string | null;
  quantidade: number | null;
  preco_tabela: number | null;
  valor: number | null;
}

export interface Lembrete {
  id: string;
  cenario: { codigo: string | null; nome: string | null; orientacao: string | null };
  data: string | null;
  setor: string | null;
  evidencia_pagina: number | null;
  evidencia_trecho: string | null;
  etiquetas: string[];
  criado_em: string | null;
  insumos: InsumoDoLembrete[];
}

export interface ContaComLembrete {
  conta_id: string;
  numero_atendimento: string | null;
  paciente_rotulo: string | null;
  numero_conta: string | null;
  operadora: string | null;
  situacao: string | null;
  concluida_em: string | null;
  periodo_inicio: string | null;
  periodo_fim: string | null;
  lembretes: Lembrete[];
}

export interface Conferencia {
  numeros: { lembretes_abertos: number; contas_com_lembrete: number; valor_a_conferir: number };
  contas: ContaComLembrete[];
  pode_cadastrar: boolean;
}

export interface InsumoDoCenario {
  codigo: string;
  descricao: string | null;
  quantidade: number;
  na_tabela?: boolean;
}

export interface Cenario {
  id: string;
  codigo: string;
  nome: string;
  operadora_sigla: string | null;
  gatilho_texto: string;
  orientacao: string | null;
  ativo: boolean;
  insumos: InsumoDoCenario[];
}

/** O que a pessoa confere e salva: o cenário sem id nem código. */
export type CamposDoCenario = Omit<Cenario, "id" | "codigo">;

export interface AbaDeCenarios {
  cenarios: Cenario[];
  operadoras: { sigla: string; nome: string | null }[];
}

export function cenarioVazio(): CamposDoCenario {
  return {
    nome: "",
    operadora_sigla: null,
    gatilho_texto: "",
    orientacao: null,
    ativo: true,
    insumos: [{ codigo: "", descricao: "", quantidade: 1 }],
  };
}

/** "concluída em 09/10", "em correção": a situação da conta na faturista. */
export function situacaoNaFaturista(conta: Pick<ContaComLembrete, "situacao" | "concluida_em">): string {
  const rotulo = (conta.situacao && ROTULO_SITUACAO[conta.situacao]) || conta.situacao || "";
  const texto = rotulo.charAt(0).toLowerCase() + rotulo.slice(1);
  if (conta.concluida_em && conta.situacao?.startsWith("CONCLUIDA")) return `${texto} em ${dataCurta(conta.concluida_em)}`;
  return texto;
}

/** "03/10 · CTI ADULTO" */
export function dataESetor(lembrete: Pick<Lembrete, "data" | "setor">): string {
  return [lembrete.data ? dataCurta(lembrete.data) : null, lembrete.setor].filter(Boolean).join(" · ");
}
