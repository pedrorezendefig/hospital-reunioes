/**
 * O alvo mínimo de toque do celular (issue #496, PRD #471, RN-75, D-02).
 *
 * 44px é o piso do WCAG 2.5.5 e o tamanho que o botão de menu do cabeçalho da
 * casa já usa (`components/layout/Header`). É requisito de acessibilidade, e
 * não gosto: um botão de 28px de altura numa lista densa erra o dedo e acerta
 * a linha de baixo, e na fila da Ouvidoria a linha de baixo é outro caso.
 *
 * Vale só abaixo de 768px. No computador o ponteiro acerta o controle compacto
 * sem esforço, e esticar tudo para 44px afundaria a linha de 64px que a
 * issue #495 desenhou.
 */

/** Para o controle que já tem largura própria: só o piso de altura. */
export const ALTURA_DE_TOQUE = "min-h-[44px] md:min-h-0";

/** Para o botão de ícone, que não tem texto para lhe dar tamanho. */
export const ALVO_DE_TOQUE = "min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0";
