/**
 * A Caixa alta vista pelo teste de componente (ADR 0080, issue #1454).
 *
 * A regra mora no `@layer base` do `globals.css` e o jsdom não a aplica. O que
 * um teste de componente consegue provar é a outra metade: que o dado digitado
 * (nome da reunião, título do POP, nome de pessoa, setor) carrega `normal-case`
 * entre ele e o elemento de Texto curto que o embrulha.
 */

/**
 * Os elementos que a regra base põe em caixa alta. É a mesma lista do seletor
 * do `globals.css`, e `app/caixa-alta.test.ts` confere as duas uma contra a
 * outra: trocar uma sem a outra fica vermelho.
 */
export const SELETOR_DO_TEXTO_CURTO = 'h1, h2, h3, button, label, th, [role="tab"], nav a, .etiqueta';

/**
 * O texto deste elemento aparece como foi escrito?
 *
 * Sobe do elemento até a raiz. O primeiro que decidir, decide: `normal-case`
 * diz que sim; a classe `uppercase` do Tailwind diz que não; o parágrafo (que
 * a regra base devolve à caixa mista) diz que sim; um elemento de Texto curto
 * diz que não.
 * Ninguém no caminho: é Texto corrido, sim.
 */
export function apareceComoFoiEscrito(elemento: Element): boolean {
  for (let atual: Element | null = elemento; atual; atual = atual.parentElement) {
    if (atual.classList.contains("normal-case")) return true;
    if (atual.classList.contains("uppercase")) return false;
    if (atual.tagName === "P") return true;
    if (atual.matches(SELETOR_DO_TEXTO_CURTO)) return false;
  }
  return true;
}
