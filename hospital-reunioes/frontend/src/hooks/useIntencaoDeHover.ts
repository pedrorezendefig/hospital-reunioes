"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** O mouse fica em cima este tanto antes de abrir: passar de raspão não abre. */
export const ABRE_EM_MS = 150;
/** E sai este tanto antes de fechar: o caminho até o que abriu não fecha. */
export const FECHA_EM_MS = 180;

/**
 * A intenção de hover das Entregas (ADR 0092, decisão 4), uma regra só para
 * os números e, na fatia da lista, para as linhas: abre com 150 ms de mouse em
 * cima, fecha 180 ms depois da saída, o clique fixa (e o segundo clique solta e
 * fecha), e no celular o toque, que chega como clique, alterna.
 *
 * Devolve se está aberto e os eventos para espalhar no alvo.
 */
export function useIntencaoDeHover() {
  const [aberto, setAberto] = useState(false);
  const [fixo, setFixo] = useState(false);
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limpar = useCallback(() => {
    if (relogio.current !== null) clearTimeout(relogio.current);
    relogio.current = null;
  }, []);

  useEffect(() => limpar, [limpar]);

  const depois = useCallback(
    (ms: number, abrir: boolean) => {
      limpar();
      relogio.current = setTimeout(() => setAberto(abrir), ms);
    },
    [limpar],
  );

  const onMouseEnter = useCallback(() => {
    if (!fixo) depois(ABRE_EM_MS, true);
  }, [fixo, depois]);

  const onMouseLeave = useCallback(() => {
    if (!fixo) depois(FECHA_EM_MS, false);
  }, [fixo, depois]);

  const onClick = useCallback(() => {
    limpar();
    setFixo(!fixo);
    setAberto(!fixo);
  }, [fixo, limpar]);

  return { aberto, alvo: { onMouseEnter, onMouseLeave, onClick } };
}
