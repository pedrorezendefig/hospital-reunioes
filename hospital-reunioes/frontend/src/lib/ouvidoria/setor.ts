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

/**
 * Um bloco de leitura do caso (ADR 0041). Quem precisa distinguir as variantes
 * lê a `chave`, nunca a posição: no caso protegido a lista vem com um item só.
 */
export interface BlocoDoCaso {
  chave: string;
  rotulo: string;
  texto: string;
}

export const CHAVE_RESUMO = "resumo";
export const CHAVE_RELATO = "relato_integral";
export const CHAVE_NOTA = "nota_da_ouvidoria";

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
  /**
   * Os blocos de leitura do caso, na ordem em que a área os lê (ADR 0041).
   * Ausente quando o backend está uma versão atrás do frontend.
   */
  blocos?: BlocoDoCaso[];
  /**
   * Por que o caso chegou com um bloco só, quando chegou (RN-79 e a emenda de
   * 01/09/2026 do ADR 0041). O texto é do servidor: a tela não decide o corte
   * nem inventa o motivo dele.
   */
  aviso?: string | null;
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

const ROTULO_NOTA = "NOTA DA OUVIDORIA";

/**
 * Os blocos que a tela mostra, exatamente os que o servidor montou.
 *
 * A tela não decide o que a área lê: o corte do caso protegido (RN-79) é do
 * servidor, e reconstruir aqui um resumo ou um relato a partir do que ainda
 * está em mãos reabriria o buraco que o corte fechou.
 *
 * Backend uma versão atrás manda só o `extrato`, e sem esta ponte a tela
 * ficaria sem o caso. Aí o extrato entra como a nota da ouvidoria, que é o que
 * ele sempre foi.
 */
export function blocosDoCaso(caso: CasoDoPortal): BlocoDoCaso[] {
  if (caso.blocos?.length) return caso.blocos;
  return [{ chave: CHAVE_NOTA, rotulo: ROTULO_NOTA, texto: caso.extrato }];
}

/**
 * A formatação de cada bloco. Três aparências distintas porque a RN-60 proíbe
 * fundir os blocos ou dar a eles a mesma formatação: quem lê precisa saber, de
 * relance, o que é palavra do paciente e o que é interpretação da Ouvidoria.
 *
 * O resumo tem destaque tipográfico (é o que decide em segundos se o caso é da
 * área); o relato fica em fundo neutro, que é o corpo do caso; a nota ganha
 * moldura própria, para nunca se confundir com o relato.
 */
export const CLASSE_DO_BLOCO: Record<string, string> = {
  // `whitespace-pre-wrap` também aqui: no canal aberto o resumo são os
  // primeiros caracteres do que o cidadão digitou, com as quebras de linha
  // dele, e sem isso o texto colapsa numa linha só.
  [CHAVE_RESUMO]: "text-base font-semibold text-slate-900 leading-snug whitespace-pre-wrap",
  [CHAVE_RELATO]:
    "text-sm text-slate-700 leading-relaxed whitespace-pre-wrap rounded-xl bg-slate-50 border border-slate-200 px-3 py-2.5",
  [CHAVE_NOTA]:
    "text-sm text-slate-700 leading-relaxed whitespace-pre-wrap rounded-xl bg-primary/5 border border-primary/20 border-l-4 border-l-primary px-3 py-2.5",
};

/** Chave que a tela ainda não conhece cai na formatação da nota: bloco novo do
 * servidor aparece na tela, e nunca com a cara de outro bloco. */
export function classeDoBloco(chave: string): string {
  return CLASSE_DO_BLOCO[chave] ?? CLASSE_DO_BLOCO[CHAVE_NOTA];
}

/**
 * O piso que faz a resposta da área dizer o que foi FEITO (RN-61).
 *
 * O mesmo número do servidor (`ouvidoria_respostas.MINIMO_DE_CARACTERES`), que
 * é quem recusa de verdade: aqui ele só evita oferecer um envio que termina em
 * recusa previsível.
 */
export const MINIMO_DA_RESPOSTA = 20;

/**
 * O teto da resposta da área (issue #512, decisão de 02/09/2026).
 *
 * O mesmo número do servidor (`ouvidoria_respostas.MAXIMO_DE_CARACTERES`), que
 * é quem recusa de verdade. Sem este espelho o responsável escrevia 12.000
 * caracteres, o botão ficava habilitado e o envio voltava 422.
 */
export const MAXIMO_DA_RESPOSTA = 10_000;

/** O teto como o responsável o lê. Estático, e não `toLocaleString`, para a
 * frase da tela não depender do locale do navegador. */
const MAXIMO_ESCRITO = "10.000";

/** A partir de quanto o contador aparece. Antes disso ele só ocuparia espaço
 * numa tela que já é longa: resposta real tem centenas de caracteres, não
 * milhares. */
const MARGEM_DO_AVISO = 1_000;

/** Os caracteres de formatação do Unicode (categoria Cf), os de largura zero
 * incluídos. O `trim` não os enxerga, e o servidor os descarta antes de medir
 * (`ouvidoria_respostas._sem_invisiveis`). */
const INVISIVEIS = /\p{Cf}/gu;

/**
 * Quantos caracteres esta resposta tem para o servidor.
 *
 * Contar `texto.length` seria contar unidades UTF-16, e o servidor conta code
 * points depois de tirar os invisíveis. As duas contagens divergem em texto
 * real: "Ok, ja resolvido 👍👍" tem 21 unidades UTF-16 e 19 code points, então
 * o botão liberava um envio que o servidor recusa com 422, com o campo
 * visivelmente cheio. O mesmo com um caractere de largura zero colado no texto.
 */
export function tamanhoDaResposta(texto: string): number {
  return [...texto.replace(INVISIVEIS, "").trim()].length;
}

/**
 * Quantos caracteres esta resposta tem para o TETO do servidor.
 *
 * Duas contagens porque o servidor tem duas: o piso mede o texto já
 * normalizado (é ele que o ouvidor lê), e o teto mede o texto como chegou,
 * antes de normalizar (normalizar dezenas de MB só para depois recusá-los é o
 * custo que o teto existe para evitar). Medir o teto com a contagem do piso
 * liberaria o botão para um texto que o servidor recusa: mil caracteres de
 * largura zero colados no fim somem do piso e continuam contando no teto.
 *
 * O `trim` fica porque a tela apara antes de enviar
 * (`montarFormularioDeResposta`): o que se mede aqui é exatamente a string que
 * o servidor vai medir, e não uma aproximação dela.
 *
 * A conta é antes da sanitização de travessão, do mesmo jeito que no servidor.
 * O sanitizador troca cada travessão por vírgula e espaço, então o texto
 * gravado pode ficar maior que o medido, no pior caso o dobro. Isso é aceito:
 * o teto existe contra o POST de dezenas de MB na trilha imutável, e 20.000
 * caracteres continuam sendo um Dossiê que abre.
 */
export function tamanhoBrutoDaResposta(texto: string): number {
  return [...texto.trim()].length;
}

/** A resposta precisa dizer o que foi FEITO: espaço em branco não vale, e uma
 * palavra solta chega ao ouvidor como caso respondido sem conteúdo. E precisa
 * caber na trilha: acima do teto o servidor devolve 422, então o botão que
 * continuasse habilitado estaria mentindo (issue #512). */
export function respostaDoSetorValida(texto: string): boolean {
  return (
    tamanhoDaResposta(texto) >= MINIMO_DA_RESPOSTA &&
    tamanhoBrutoDaResposta(texto) <= MAXIMO_DA_RESPOSTA
  );
}

/**
 * O que a tela diz sobre o teto, ou nada quando ainda não há o que dizer.
 *
 * Contador só perto do limite: o responsável que escreve três linhas nunca vê
 * o aviso, e quem está chegando lá descobre antes de apertar o botão, não pelo
 * 422. Acima do teto a frase é a mesma do servidor
 * (`ouvidoria_respostas.RECUSA_LONGA`), para a tela não ensinar uma saída
 * diferente da que o servidor ensinaria.
 */
export function avisoDoTetoDaResposta(texto: string): string | null {
  const tamanho = tamanhoBrutoDaResposta(texto);
  if (tamanho > MAXIMO_DA_RESPOSTA) {
    return `A resposta passou de ${MAXIMO_ESCRITO} caracteres. Resuma o que foi feito e mande o detalhamento como anexo.`;
  }
  if (tamanho > MAXIMO_DA_RESPOSTA - MARGEM_DO_AVISO) {
    return `Restam ${MAXIMO_DA_RESPOSTA - tamanho} caracteres do limite de ${MAXIMO_ESCRITO}.`;
  }
  return null;
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
