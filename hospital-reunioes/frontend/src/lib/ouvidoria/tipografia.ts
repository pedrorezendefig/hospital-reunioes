/**
 * A caixa das letras da Ouvidoria (issue #489, PRD #471, RN-76, D-19).
 *
 * A regra é uma só: caixa alta é de RÓTULO CURTO (título de seção, rótulo de
 * campo, carimbo de estado, rótulo de botão) e nunca de texto corrido (resumo,
 * relato, resposta da área, justificativa, aviso). Frase inteira em maiúscula
 * grita, some com a silhueta das palavras e atrasa justamente a leitura que
 * precisa ser cuidadosa: o que o paciente escreveu.
 *
 * Ela mora aqui, e não só na cabeça de quem escreve o JSX, porque é o teste
 * que a aplica. A varredura de `app/ouvidoria/tipografia.test.tsx` percorre as
 * telas renderizadas, junta tudo o que sai em caixa alta e passa cada pedaço
 * por `ehRotuloCurto`: o parágrafo que amanhã nascer dentro de um bloco em
 * maiúscula cai ali, sem depender de alguém reparar.
 *
 * Duas notas sobre o COMO, que valem para quem for aplicar a regra:
 *
 * 1. A caixa alta é do CSS (`uppercase`), nunca do texto escrito no código.
 *    Assim o DOM continua guardando a palavra como ela se escreve: o leitor de
 *    tela anuncia "Encerrar" em vez de soletrar, a busca da página acha
 *    "encerrar" e a tradução do navegador não recebe uma sopa de maiúsculas.
 *    Escrever "ENCERRAR" no JSX perderia tudo isso, e sem volta.
 * 2. Navegação fica de fora. A porta para outra tela não é dado nem ação, no
 *    resto da casa nenhuma navegação é caixa alta, e a barra de atalhos ainda
 *    é a única linha do módulo sem folga de largura (RN-77, D-16).
 */

/**
 * O teto do rótulo curto, em caracteres.
 *
 * Sai do maior rótulo que o módulo usa hoje, "Aguardando seu encerramento"
 * (27), com uma folga pequena. Acima disso o que se está escrevendo já é
 * frase, e frase não vai para caixa alta, por mais que caiba na linha.
 */
export const TETO_DO_ROTULO_CURTO = 30;

/**
 * Ponto, exclamação e interrogação são o que fecha uma frase. Um rótulo curto
 * que os carrega não é rótulo: é uma frase curta, e ela também grita em
 * maiúscula. Os dois pontos ficam de fora de propósito, porque o rótulo os usa
 * para apresentar o que vem depois.
 */
const PONTUACAO_DE_FRASE = /[.!?]/;

/**
 * Este texto pode ir para caixa alta?
 *
 * Vazio passa: bloco sem texto próprio (o que só embrulha outros) não grita
 * nada, e reprová-lo faria a varredura acusar a moldura em vez do conteúdo.
 */
export function ehRotuloCurto(texto: string | null | undefined): boolean {
  const limpo = (texto ?? "").replace(/\s+/g, " ").trim();
  if (limpo.length > TETO_DO_ROTULO_CURTO) return false;
  return !PONTUACAO_DE_FRASE.test(limpo);
}
