"use client";

/**
 * O endereço curto do cartaz, `/a/{código}` (issue #1617, ADR 0086 decisão 5).
 *
 * É o que o cartaz A4 imprime e o QR carrega, e as URLs antigas
 * (`/ouvidoria/qr?p=` e `/manifestacao?p=`) redirecionam para cá. Desde a
 * issue #1622 ele abre a nota de 1 a 5 do cartaz, e quem pede retorno segue
 * para a Manifestação guiada; o cartaz que já está na parede continua valendo.
 *
 * Quem decide se o caso entra com origem é o servidor, pelo código: ponto
 * ativo grava a origem, ponto aposentado ou código que ninguém cadastrou abre
 * a manifestação sem origem, e nunca uma página de erro (ADR 0036, decisão 6).
 */

import { useParams } from "next/navigation";
import { AvaliacaoPublica } from "@/components/ouvidoria/AvaliacaoPublica";

export default function EnderecoCurtoDoCartaz() {
  const { codigo } = useParams<{ codigo: string }>();
  return <AvaliacaoPublica codigoDoCartaz={codigo ?? ""} />;
}
