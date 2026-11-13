/**
 * A Avaliação do QR (issue #1622, ADR 0086): a nota de 1 a 5 que o cartaz abre
 * antes da Manifestação guiada. Não vira protocolo e não guarda nada de quem
 * avaliou; quem pede retorno segue para a manifestação.
 */

import { TITULOS_DO_CARTAZ, type TituloDoCartaz } from "@/lib/ouvidoria/pontos";

/** Os oito motivos da tela N2, na ordem da especificação. O valor é o que o
 * servidor aceita (lista fechada no backend e no CHECK da migration 140). */
export const MOTIVOS_DA_AVALIACAO: { valor: string; rotulo: string }[] = [
  { valor: "atencao_equipe", rotulo: "Atenção da equipe" },
  { valor: "tempo_espera", rotulo: "Tempo de espera" },
  { valor: "informacao_recebida", rotulo: "Informação recebida" },
  { valor: "limpeza", rotulo: "Limpeza" },
  { valor: "conforto", rotulo: "Conforto" },
  { valor: "atendimento_medico", rotulo: "Atendimento médico" },
  { valor: "atendimento_enfermagem", rotulo: "Atendimento de enfermagem" },
  { valor: "recepcao", rotulo: "Recepção" },
];

export const TAMANHO_DO_COMENTARIO = 500;

/** A nota de 1 a 3 pergunta se a pessoa quer retorno; a 4 e a 5 oferecem o
 * elogio (tela N3). */
export function perguntaRetorno(nota: number): boolean {
  return nota <= 3;
}

/** O título da tela N1: o mesmo do cartaz daquele ponto. */
export function tituloDaNota(titulo: TituloDoCartaz | null | undefined): string {
  const achado = TITULOS_DO_CARTAZ.find((t) => t.valor === titulo);
  return (achado ?? TITULOS_DO_CARTAZ[0]).rotulo;
}

/** O corpo do envio: Pular manda só a nota; comentário em branco não vai. */
export function montarAvaliacao(
  nota: number,
  motivos: string[],
  comentario: string,
  pulou: boolean
): { nota: number; motivos?: string[]; comentario?: string } {
  if (pulou) return { nota };
  const texto = comentario.trim();
  return {
    nota,
    ...(motivos.length ? { motivos } : {}),
    ...(texto ? { comentario: texto } : {}),
  };
}
