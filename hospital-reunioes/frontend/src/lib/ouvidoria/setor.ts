/**
 * Portal do setor por link tokenizado (issue #326, ADR 0034 decisão 4).
 *
 * A lógica que a página pública precisa, fora do JSX: o gate de verdade é o
 * backend (token, estado, anexos), mas a tela não pode oferecer um envio que
 * termina em recusa previsível.
 */

/** O pedido de prorrogação do caso, quando existe (issue #333). */
export interface PedidoDeProrrogacao {
  id: string;
  justificativa: string;
  dias_uteis_pedidos: number;
  prazo_anterior: string | null;
  prazo_novo: string | null;
  status: "pendente" | "aprovada" | "negada";
  solicitada_em: string;
  solicitante_nome: string;
  decidida_em: string | null;
  decidida_por_nome: string | null;
  decisao_justificativa: string | null;
  /**
   * Se aprovar este pedido concederia prazo de verdade, e o motivo quando nao
   * (issue #373). So o painel do ouvidor recebe: o portal do setor nao decide,
   * entao a listagem publica nao carrega os dois campos.
   */
  aprovacao_possivel?: boolean;
  motivo_da_aprovacao?: string | null;
}

/** O bloco de prorrogação que a página mostra: regras, porta aberta ou não. */
export interface ProrrogacaoNoPortal {
  regras: string[];
  max_dias_uteis: number;
  permitida: boolean;
  motivo: string | null;
  pedido: PedidoDeProrrogacao | null;
}

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
  /** Ausente quando o backend está uma versão atrás do frontend. */
  prorrogacao?: ProrrogacaoNoPortal;
  /**
   * O que o servidor não pôde ler para montar esta resposta (issue #449).
   * Ausente quando o backend está uma versão atrás do frontend, e ausente não é
   * "nada degradou": é não saber.
   */
  degradado?: string[];
}

/** A frase que substitui o prazo quando o calendário não pôde ser confirmado. */
export const SEM_CONFIRMACAO_DO_CALENDARIO = "sem confirmação do calendário";

/**
 * A frase de prazo que o portal pode afirmar.
 *
 * O rótulo ("vence em 2 dias úteis") é contado com a tabela de feriados. Quando
 * a leitura dela falha, o servidor conta feriado como dia útil e o número sai
 * mais curto do que é, sem nada denunciando isso (issue #449). Para quem tem
 * que responder no prazo, uma frase errada é pior que frase nenhuma.
 *
 * `degradado` ausente também tira a frase: é o backend uma versão atrás, que
 * não tem como dizer se leu o calendário, e presumir que leu é a mesma aposta
 * que esta função existe para não fazer.
 */
export function rotuloDePrazoDoPortal(caso: CasoDoPortal): string {
  if (!caso.degradado || caso.degradado.includes("feriados")) return SEM_CONFIRMACAO_DO_CALENDARIO;
  return caso.rotulo_prazo;
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

/**
 * O pedido de prazo precisa de justificativa e de um número de dias dentro do
 * limite do formulário. O gate de verdade é o backend, que ainda aplica o teto
 * de 30 dias úteis da entrada; a tela só não oferece um envio que termina em
 * recusa previsível.
 */
export function pedidoDeProrrogacaoValido(
  justificativa: string,
  dias: number,
  maxDias: number
): boolean {
  return justificativa.trim().length > 0 && Number.isInteger(dias) && dias >= 1 && dias <= maxDias;
}

/** O que o titular lê sobre o pedido que já existe no caso. */
export function situacaoDoPedido(pedido: PedidoDeProrrogacao): string {
  if (pedido.status === "pendente") {
    return "A Ouvidoria ainda não decidiu o seu pedido de prorrogação. O prazo acima continua valendo.";
  }
  if (pedido.status === "aprovada") {
    return "A Ouvidoria aprovou a prorrogação. O prazo acima já é o prazo novo.";
  }
  return "A Ouvidoria negou a prorrogação. O prazo acima continua valendo.";
}

/**
 * O cartão "Precisa de mais prazo?" tem o que dizer ao titular.
 *
 * A página é pública e aberta do celular por gente de fora, então tudo aqui é
 * lido com guarda. A guarda de leitura, porém, deixava o cartão nascer vazio
 * quando o backend não mandava o bloco (versão atrás, resposta em cache):
 * título, ícone e uma lista sem itens, dizendo nada (issue #375, item 21).
 *
 * Qualquer uma das três coisas é conteúdo: as regras, a porta aberta (o botão
 * de pedir) e a explicação de por que ela está fechada, incluindo o pedido que
 * já existe. Nenhuma delas, e o cartão não aparece.
 */
export function cartaoDeProrrogacaoTemConteudo(
  prorrogacao: ProrrogacaoNoPortal | undefined | null
): boolean {
  if (!prorrogacao) return false;
  return Boolean(
    prorrogacao.regras?.length ||
      prorrogacao.permitida ||
      prorrogacao.motivo ||
      prorrogacao.pedido
  );
}
