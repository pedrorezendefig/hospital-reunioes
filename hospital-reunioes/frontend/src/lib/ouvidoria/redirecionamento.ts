/**
 * O Redirecionamento pelo ouvidor, lido da trilha (issue #710, PRD #706,
 * ADR 0055).
 *
 * O ouvidor tira o caso de uma área e o aciona em outra na mesma requisição. O
 * motivo NÃO ganha coluna: ele vive na observação do movimento de saída, com um
 * prefixo fixo, e é de lá que o Dossiê o lê.
 *
 * Este módulo é o único lugar do frontend que desmonta essa frase. O prefixo é
 * o contrato entre os dois lados (`_PREFIXO` de
 * `app/services/ouvidoria_redirecionamento.py`): mudá-lo lá sem mudá-lo aqui
 * faz o rótulo sumir da linha do tempo em silêncio, e é por isso que ele mora
 * numa constante exportada, com teste próprio.
 *
 * Irmão de `devolucao-a-ouvidoria`, e separado dele de propósito: as duas
 * observações vão para a MESMA coluna da MESMA trilha, e é o prefixo que
 * separa o ato da área do ato do ouvidor. Sem a separação, a contagem de
 * devoluções do Dossiê passaria a incluir os redirecionamentos da própria
 * Ouvidoria, que é justamente o que o ADR 0055 manda evitar.
 */

import type { EventoDaTrilha } from "./trilha";

/**
 * O rótulo que abre a observação do movimento de saída. Palavra por palavra o
 * `_PREFIXO` do módulo do backend.
 */
export const PREFIXO_DO_REDIRECIONAMENTO = "Redirecionado pelo ouvidor";

/** O que o backend escreve entre o prefixo e o setor de onde o caso saiu. */
const ABERTURA_DO_SETOR = " (de ";

/** O fecho do setor mais o separador do motivo, numa marca só. */
const FECHO_DO_SETOR = "): ";

/**
 * A descrição que o servidor dá às duas arestas de saída para
 * `em_classificacao`, palavra por palavra o `ROTULO_DO_ESTADO["em_classificacao"]`
 * de `app/services/ouvidoria_trilha.py`.
 */
const DESCRICAO_DA_VOLTA_A_CLASSIFICACAO = "Caso em classificação";

/** O redirecionamento como a linha do tempo o mostra. */
export interface RedirecionamentoLido {
  /** A área de onde o caso saiu, congelada na observação pelo servidor. */
  setor: string;
  motivo: string;
}

function desmontar(texto: string): RedirecionamentoLido | null {
  const inicio = PREFIXO_DO_REDIRECIONAMENTO.length + ABERTURA_DO_SETOR.length;
  const corte = texto.indexOf(FECHO_DO_SETOR, inicio);
  if (corte < 0) return null;
  return {
    setor: texto.slice(inicio, corte),
    // `slice` e não `split`: o motivo é texto livre de até 10.000 caracteres e
    // pode conter "): " à vontade. Cortar em toda ocorrência perderia tudo o
    // que vem depois da primeira.
    motivo: texto.slice(corte + FECHO_DO_SETOR.length),
  };
}

/**
 * O redirecionamento que este evento da trilha é, ou nulo quando ele é outra
 * coisa.
 *
 * Três condições, pelo mesmo raciocínio do módulo da Devolução à Ouvidoria,
 * porque nenhuma sozinha basta:
 *
 * - só a frase não basta: a resposta da área é texto livre de quem tem o link
 *   do setor, e nada impede o titular de escrever "Redirecionado pelo ouvidor
 *   (de X): ..." no campo do que foi feito;
 * - o que elimina esse caso é `sistema`, que é o `autor_id` nulo de quem agiu
 *   sem login. O redirecionamento é ato do ouvidor LOGADO, então aqui a régua
 *   é a inversa da devolução: `sistema` falso;
 * - e a descrição, que nomeia a transição no grafo. Sem ela, uma observação de
 *   encerramento escrita à mão com a mesma abertura passaria por
 *   redirecionamento.
 */
export function redirecionamentoDoEvento(evento: EventoDaTrilha): RedirecionamentoLido | null {
  if (evento.descricao !== DESCRICAO_DA_VOLTA_A_CLASSIFICACAO) return null;
  if (evento.sistema) return null;
  if (typeof evento.texto !== "string") return null;
  if (!evento.texto.startsWith(`${PREFIXO_DO_REDIRECIONAMENTO}${ABERTURA_DO_SETOR}`)) return null;
  return desmontar(evento.texto);
}

/**
 * O rótulo do movimento na linha do tempo. Ele substitui a descrição genérica
 * da transição ("Caso em classificação"), que não distingue o ato do ouvidor da
 * devolução da área nem do reacionamento, e é o que cumpre a promessa do
 * ADR 0055 de os dois serem legíveis meses depois.
 */
export function rotuloDoRedirecionamento(setor: string): string {
  return `${PREFIXO_DO_REDIRECIONAMENTO} (de ${setor})`;
}

/**
 * As marcas com que o servidor diz que o caso JÁ NÃO ESTÁ como a tela o mostra.
 *
 * São o começo, palavra por palavra, de `SAIU_DA_AREA_NO_MEIO`,
 * `FALHA_DEPOIS_DA_SAIDA` e `FALHA_DE_ESTADO_INDETERMINADO`, de
 * `app/routers/ouvidoria.py`. Elas são o contrato entre os dois lados, como o
 * prefixo da trilha aqui em cima: mudá-las lá sem mudá-las aqui faz a tela
 * parar de reler o caso em silêncio.
 *
 * Por que a marca, e não a FAIXA do status: o redirecionamento devolve **409
 * depois de escritas já aplicadas** em dois caminhos reais. O `restaurar` que
 * não casa linha (o relógio da área ficou parado e não voltou) responde 409 com
 * a primeira marca, e o 23514 da transição de ENTRADA, que no redirecionamento
 * só roda depois do ponto sem volta, sobe com a segunda marca e com o 409
 * preservado. Derivar "o caso se moveu" de `status >= 500` deixa esses dois
 * fora, e o ouvidor fica olhando um Dossiê que afirma a área antiga.
 *
 * A primeira marca cobre também o ramo em que o `parar` não casou linha e NADA
 * foi escrito. Reler ali continua certo: nesse ramo o caso saiu do estado de
 * origem por outra porta, então a tela está velha do mesmo jeito.
 */
const MARCAS_DO_CASO_QUE_SE_MOVEU = [
  "Este caso saiu da fila da área durante o envio",
  "O caso saiu da área anterior e está em classificação",
  "O redirecionamento não terminou.",
];

/** O que a tela faz depois de um redirecionamento que não deu 2xx. */
export interface FalhaDoRedirecionamento {
  /**
   * O que está na tela debaixo da modal pode estar velho: releia o caso ao
   * fechar.
   */
  releiaOCaso: boolean;
  /**
   * O ato passou do ponto sem volta. Repetir não é o caminho: a própria
   * resposta do servidor manda conferir antes de agir.
   */
  atoConsumido: boolean;
}

/**
 * O que fazer com uma resposta de redirecionamento que não foi 2xx
 * (issue #710).
 *
 * `status` nulo é a requisição que nem chegou a ter resposta.
 *
 * A régua é a marca que o servidor pôs no texto, e não a faixa do status. Na
 * dúvida a tela relê: a leitura a mais custa um GET, e a tela velha custa um
 * despacho errado. A recusa que o servidor decide antes de tocar no caso
 * (estado fora do par, mesma área, área sem responsável, motivo inválido, sem
 * perfil, limite de taxa) fecha sem releitura, com o que o ouvidor digitou
 * intacto.
 */
export function lerAFalhaDoRedirecionamento(
  status: number | null,
  detail: string | null
): FalhaDoRedirecionamento {
  const seMoveu =
    typeof detail === "string" && MARCAS_DO_CASO_QUE_SE_MOVEU.some((marca) => detail.startsWith(marca));
  return {
    atoConsumido: seMoveu,
    // 5xx e resposta nenhuma são o degrau em que o front NÃO SABE onde o caso
    // está. Não saber conta como "pode ter mudado", e não como "está tudo bem".
    releiaOCaso: seMoveu || status === null || status >= 500,
  };
}

/**
 * A frase que o ouvidor lê quando o redirecionamento deu certo (issue #710).
 *
 * Ela afirma as duas coisas que o servidor fez, e só elas: o caso está com a
 * área nova e a antiga foi avisada. Nada sobre o motivo nem sobre o email da
 * área nova, que é o que a tela não tem como conferir.
 */
export function confirmacaoDoRedirecionamento(setor: string): string {
  return `Caso redirecionado para ${setor}. A área anterior foi avisada.`;
}
