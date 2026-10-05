/**
 * A regra de onde o painel flutuante encosta (issue #777).
 *
 * Fica aqui, e não dentro do componente, porque é geometria pura: o menu de
 * ações da fila precisa dela para escapar do card que o recortava, e num
 * `useLayoutEffect` ela só seria exercitada com `getBoundingClientRect` e
 * `offsetHeight` forjados no jsdom, que é o teste testando o dublê.
 */

import { describe, expect, it } from "vitest";

import { posicaoDoFlutuante, FOLGA_DO_FLUTUANTE as FOLGA } from "./flutuante";

const PAINEL = { altura: 100, largura: 208 };
const JANELA = { altura: 800, largura: 1200 };

describe("posicaoDoFlutuante (issue #777)", () => {
  it("encosta abaixo do gatilho quando há espaço", () => {
    const { top } = posicaoDoFlutuante({ top: 200, bottom: 232, right: 900 }, PAINEL, JANELA);

    expect(top).toBe(232 + FOLGA);
  });

  it("alinha a borda direita do painel com a do gatilho", () => {
    const { left } = posicaoDoFlutuante({ top: 200, bottom: 232, right: 900 }, PAINEL, JANELA);

    expect(left).toBe(900 - PAINEL.largura);
  });

  it("deixa um respiro entre o gatilho e o painel", () => {
    // Sem folga o menu nasce colado no botão que o abriu, e a borda de um
    // vira a borda do outro. O quanto é gosto; que exista, não.
    const gatilho = { top: 200, bottom: 232, right: 900 };

    const { top } = posicaoDoFlutuante(gatilho, PAINEL, JANELA);

    expect(top).toBeGreaterThan(gatilho.bottom);
  });

  it("vira para cima quando o painel não cabe abaixo", () => {
    // O gatilho a 60px do rodapé não tem onde pendurar 100px de painel. Com
    // `position: fixed` não existe rolagem que alcance o que passou do
    // rodapé: sem virar, o menu simplesmente não aparece.
    const { top } = posicaoDoFlutuante({ top: 708, bottom: 740, right: 900 }, PAINEL, JANELA);

    expect(top).toBe(708 - FOLGA - PAINEL.altura);
  });

  it("não deixa o painel sair por cima do topo da janela", () => {
    // Janela baixa e gatilho perto do topo: não cabe abaixo nem acima. O
    // painel encosta no topo em vez de subir para fora da tela.
    const { top } = posicaoDoFlutuante(
      { top: 40, bottom: 72, right: 900 },
      PAINEL,
      { altura: 150, largura: 1200 }
    );

    expect(top).toBe(FOLGA);
  });

  it("não deixa o painel sair pela esquerda numa tela estreita", () => {
    const { left } = posicaoDoFlutuante(
      { top: 200, bottom: 232, right: 150 },
      PAINEL,
      { altura: 800, largura: 320 }
    );

    expect(left).toBe(FOLGA);
  });
});
