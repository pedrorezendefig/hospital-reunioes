"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * Fecha um flutuante ao clicar fora dele e no Escape (issue #496).
 *
 * O comportamento já existia escrito à mão no menu de ações da fila
 * (`components/ouvidoria/ListaDaFila`), e o menu de atalhos do celular precisa
 * do mesmo. Duas cópias já são uma a mais: quem consertar o vazamento de
 * listener numa delas não vai lembrar da outra.
 *
 * O `fechar` vive num ref para o efeito depender só do `aberto`: com ele nas
 * dependências, a função inline de cada render trocaria os dois listeners do
 * documento a cada renderização.
 *
 * O `painel` é para o flutuante que sai por portal (issue #777): portado para
 * o `body`, ele deixa de ser descendente da `caixa`, e o clique num item dele
 * passaria por clique fora. O `mousedown` fecharia o menu e desmontaria o
 * botão antes de o `click` chegar nele, e a ação nunca aconteceria. Quem
 * flutua dentro da própria caixa não precisa passar nada.
 */
export function useFecharFlutuante(
  aberto: boolean,
  caixa: RefObject<HTMLElement | null>,
  fechar: () => void,
  painel?: RefObject<HTMLElement | null>
) {
  const acao = useRef(fechar);
  acao.current = fechar;

  useEffect(() => {
    if (!aberto) return;
    function foraDaCaixa(e: MouseEvent) {
      const alvo = e.target as Node;
      if (caixa.current?.contains(alvo)) return;
      if (painel?.current?.contains(alvo)) return;
      if (caixa.current) acao.current();
    }
    function noEscape(e: KeyboardEvent) {
      if (e.key === "Escape") acao.current();
    }
    document.addEventListener("mousedown", foraDaCaixa);
    document.addEventListener("keydown", noEscape);
    return () => {
      document.removeEventListener("mousedown", foraDaCaixa);
      document.removeEventListener("keydown", noEscape);
    };
  }, [aberto, caixa, painel]);
}
