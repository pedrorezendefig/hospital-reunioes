"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** O mouse fica em cima este tanto antes de abrir: passar de raspão não abre. */
export const ABRE_EM_MS = 150;
/** E sai este tanto antes de fechar: o caminho até o que abriu não fecha. */
export const FECHA_EM_MS = 180;

type Eventos = { onMouseEnter: () => void; onMouseLeave: () => void; onClick: () => void };

/**
 * A intenção de hover das Entregas (ADR 0092, decisão 4), uma regra só para
 * os números e para as linhas da lista: abre com 150 ms de mouse em cima,
 * fecha 180 ms depois da saída, o clique fixa (e o segundo clique solta e
 * fecha), e no celular o toque, que chega como clique, alterna.
 *
 * Esta é a forma de um grupo (issue #1703): um alvo aberto por vez. Abrir
 * outro, pelo mouse ou pelo clique, fecha o anterior; com um alvo fixo, o
 * mouse nos outros não abre nada, e o clique noutro fixa o outro.
 *
 * Devolve a chave do alvo aberto (ou `null`) e os eventos de cada alvo.
 */
export function useIntencaoDeHoverDeUmaVez<Chave>() {
  const [aberta, setAberta] = useState<Chave | null>(null);
  const [fixa, setFixa] = useState<Chave | null>(null);
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limpar = useCallback(() => {
    if (relogio.current !== null) clearTimeout(relogio.current);
    relogio.current = null;
  }, []);

  useEffect(() => limpar, [limpar]);

  const depois = useCallback(
    (ms: number, chave: Chave | null) => {
      limpar();
      relogio.current = setTimeout(() => setAberta(chave), ms);
    },
    [limpar],
  );

  const alvo = useCallback(
    (chave: Chave): Eventos => ({
      onMouseEnter: () => {
        if (fixa === null) depois(ABRE_EM_MS, chave);
      },
      onMouseLeave: () => {
        if (fixa === null) depois(FECHA_EM_MS, null);
      },
      onClick: () => {
        limpar();
        const solta = fixa === chave;
        setFixa(solta ? null : chave);
        setAberta(solta ? null : chave);
      },
    }),
    [fixa, depois, limpar],
  );

  return { aberta, alvo };
}

/** A intenção de hover de um alvo só: os números do topo. */
export function useIntencaoDeHover() {
  const { aberta, alvo } = useIntencaoDeHoverDeUmaVez<true>();
  return { aberto: aberta === true, alvo: alvo(true) };
}
