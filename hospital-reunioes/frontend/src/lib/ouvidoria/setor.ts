/**
 * Portal do setor por link tokenizado (issue #326, ADR 0034 decisão 4).
 *
 * A lógica que a página pública precisa, fora do JSX: o gate de verdade é o
 * backend (token, estado, anexos), mas a tela não pode oferecer um envio que
 * termina em recusa previsível.
 */

/** O que o GET público devolve para o titular. */
export interface CasoDoPortal {
  protocolo: string;
  setor: string;
  categoria: string;
  gravidade: string | null;
  extrato: string;
  identificacao: string | null;
  sigiloso: boolean;
  destinatario_nome: string;
  aceita_resposta: boolean;
  rotulo_prazo: string;
  prazo_estourado: boolean;
  minutos_uteis_restantes: number | null;
}

/** A resposta precisa dizer o que foi FEITO: espaço em branco não vale. */
export function respostaDoSetorValida(texto: string): boolean {
  return texto.trim().length > 0;
}

/**
 * Traduz a recusa do backend para o que o titular lê. O 410 chega com a
 * mensagem certa do servidor (link usado ou expirado); o 404 é seco de
 * propósito (não vaza se o caso existe) e ganha o texto aqui.
 */
export function mensagemDoPortal(status: number, detail: string | undefined): string {
  if (status === 404) {
    return "Este link não é válido. Confira se o endereço veio completo no email da Ouvidoria.";
  }
  if (detail) return detail;
  return "Não foi possível carregar este link agora. Tente novamente.";
}

/** O multipart do envio: a resposta aparada mais os anexos escolhidos. */
export function montarFormularioDeResposta(resposta: string, arquivos: File[]): FormData {
  const form = new FormData();
  form.set("resposta", resposta.trim());
  for (const arquivo of arquivos) {
    form.append("arquivos", arquivo);
  }
  return form;
}
