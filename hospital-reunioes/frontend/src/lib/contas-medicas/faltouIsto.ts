/**
 * O Faltou isto no Guia e a conversa com o Auditor (issue #1489, PRD #1484, ADR 0081).
 *
 * Quem decide é o servidor: quem pode apontar, a origem que o Auditor deu e
 * quem pode abrir o pedido para a Tecnologia. Aqui só se escreve o que a tela
 * mostra. O número do pedido não vem: na tela ele só está aberto ou não.
 */

import { dataCurta } from "@/lib/contas-medicas/guia";

export type OrigemDoFaltouIsto = "REGRA" | "LEITURA" | "DEFEITO";

export interface FaltouIsto {
  id: string;
  data: string;
  item: string;
  pagina: number | null;
  texto: string | null;
  origem: "PESSOA" | "AGENTE";
  classificacao: OrigemDoFaltouIsto | null;
  explicacao: string | null;
  criado_em?: string | null;
  pedido_aberto: boolean;
  pode_abrir_pedido: boolean;
}

export const ROTULO_DA_ORIGEM: Record<OrigemDoFaltouIsto, string> = {
  REGRA: "Falta regra",
  LEITURA: "Página não lida",
  DEFEITO: "Defeito do sistema",
};

/** "Faltou isto em 03/10, página 2: Equipo. Por que não achou?" */
export function falaDeQuemApontou(apontamento: FaltouIsto): string {
  const pagina = apontamento.pagina ? `, página ${apontamento.pagina}` : "";
  const texto = apontamento.texto ? ` ${apontamento.texto}` : "";
  return `Faltou isto em ${dataCurta(apontamento.data)}${pagina}: ${apontamento.item}.${texto}`;
}

/** Os dias do período da conta, em ISO, do primeiro ao último. */
export function diasDoPeriodo(inicio: string | null, fim: string | null): string[] {
  if (!inicio || !fim) return [];
  const dias: string[] = [];
  const atual = new Date(`${inicio.slice(0, 10)}T12:00:00Z`);
  const ultimo = new Date(`${fim.slice(0, 10)}T12:00:00Z`);
  while (atual <= ultimo && dias.length < 400) {
    dias.push(atual.toISOString().slice(0, 10));
    atual.setUTCDate(atual.getUTCDate() + 1);
  }
  return dias;
}
