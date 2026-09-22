/**
 * Onde encostar um painel flutuante preso à janela (issue #777).
 *
 * O menu de ações da fila da Ouvidoria abria `position: absolute` dentro da
 * linha, e os dois cards que desenham a fila fecham em `overflow-hidden` para
 * clipar os filhos ao canto arredondado. O recorte acontece antes do
 * empilhamento, então o menu do caso no topo sumia inteiro atrás do bloco de
 * baixo, sem `z-index` que resolvesse. A saída é portar o painel para fora do
 * card e ancorá-lo por coordenada, que é o que esta conta entrega.
 *
 * Preso à janela, o painel não tem rolagem que o alcance: o que passou do
 * rodapé não existe. Por isso a conta escolhe o lado em vez de sempre descer,
 * e trava o resultado dentro da janela nos dois eixos.
 */

/** O respiro entre o gatilho e o painel, e entre o painel e a borda. */
export const FOLGA_DO_FLUTUANTE = 4;

/** O que a conta precisa saber do gatilho: onde ele começa, acaba e termina à direita. */
export type RetanguloDoGatilho = { top: number; bottom: number; right: number };

export type Medida = { altura: number; largura: number };

function travar(valor: number, minimo: number, maximo: number): number {
  // O mínimo vence o máximo: na janela menor que o painel os dois se cruzam, e
  // encostar no topo mostra o começo da lista, que é por onde se lê.
  return Math.max(minimo, Math.min(valor, maximo));
}

/**
 * A coordenada `fixed` do painel, alinhado pela direita do gatilho.
 *
 * Desce quando o painel inteiro cabe abaixo do gatilho, e sobe quando não
 * cabe. É o painel medido que decide, e não uma altura estimada pelo número de
 * itens: o menu da fila muda de tamanho com o estado do caso.
 */
export function posicaoDoFlutuante(
  gatilho: RetanguloDoGatilho,
  painel: Medida,
  janela: Medida,
  folga = FOLGA_DO_FLUTUANTE
): { top: number; left: number } {
  const cabeAbaixo = gatilho.bottom + folga + painel.altura <= janela.altura;
  const top = cabeAbaixo
    ? gatilho.bottom + folga
    : gatilho.top - folga - painel.altura;

  return {
    top: travar(top, folga, janela.altura - painel.altura - folga),
    left: travar(gatilho.right - painel.largura, folga, janela.largura - painel.largura - folga),
  };
}
