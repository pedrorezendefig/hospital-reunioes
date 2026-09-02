"use client";

import {
  distintivoDeNovidades,
  type ContagemDeNovidades,
} from "@/lib/ouvidoria/novidades";

interface Props {
  contagem: ContagemDeNovidades;
  /** Posicionamento, que muda entre o menu lateral e a barra do celular. */
  className?: string;
}

/**
 * O distintivo numérico do item Ouvidoria (issue #487, PRD #470, RN-69).
 *
 * O desenho é o do distintivo do sino de notificações, que é o contador que
 * este app já tinha, com uma diferença deliberada: sem `animate-pulse`. O PRD
 * recusou o pedido original de "fazer piscar" (piscar cansa, atrapalha a
 * acessibilidade e some justo quando o olho chega), e o ponto da fila ao lado
 * já nasceu permanente.
 *
 * A cor é a de acento (`primary`), a mesma do ponto na linha da fila, e não o
 * vermelho do sino: vermelho neste módulo já significa prazo estourado, e
 * novidade não é atraso.
 *
 * `role="status"` porque é isto que ele é, um valor que muda sozinho, e porque
 * dá ao teste uma fronteira própria para consultar: um número solto casa com
 * qualquer coisa numa tela cheia. O rótulo vai no `aria-label` porque um "3"
 * anunciado sozinho não diz nada, e entra no nome acessível do link inteiro
 * ("Ouvidoria, 3 casos com novidade").
 */
export function DistintivoDeNovidades({ contagem, className }: Props) {
  const distintivo = distintivoDeNovidades(contagem);
  if (!distintivo) return null;
  return (
    <span
      role="status"
      aria-label={distintivo.rotulo}
      title={distintivo.rotulo}
      className={`min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-white text-[10px] font-bold inline-flex items-center justify-center ${
        className ?? ""
      }`}
    >
      {distintivo.texto}
    </span>
  );
}
