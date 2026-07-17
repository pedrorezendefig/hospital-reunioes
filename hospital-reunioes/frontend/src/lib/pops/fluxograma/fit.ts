/**
 * Fit-to-content do palco do fluxograma (issue #235).
 *
 * Função pura: dado o bounding box do SVG e as dimensões do container, devolve
 * a escala e o pan iniciais para o diagrama inteiro caber no palco. O palco
 * centra o conteúdo (flex + transform-origin no centro), então o pan do fit é
 * sempre a origem; a escala é o fator que faz o desenho caber, sem ampliar
 * além de 100% quando o diagrama é menor que o container.
 */

export interface DimensoesFit {
  largura: number;
  altura: number;
}

export interface FitPalco {
  escala: number;
  pan: { x: number; y: number };
}

const FIT_NEUTRO: FitPalco = { escala: 1, pan: { x: 0, y: 0 } };

function medidaUtil(d: DimensoesFit): boolean {
  return Number.isFinite(d.largura) && d.largura > 0 && Number.isFinite(d.altura) && d.altura > 0;
}

export function calcularFit(svg: DimensoesFit, container: DimensoesFit): FitPalco {
  if (!medidaUtil(svg) || !medidaUtil(container)) return FIT_NEUTRO;
  const escala = Math.min(1, container.largura / svg.largura, container.altura / svg.altura);
  return { escala, pan: { x: 0, y: 0 } };
}
