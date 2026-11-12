"use client";

/**
 * O endereço curto do cartaz, `/a/{código}` (issue #1617, ADR 0086 decisão 5).
 *
 * É o que o cartaz A4 imprime e o QR carrega, e as URLs antigas
 * (`/ouvidoria/qr?p=` e `/manifestacao?p=`) redirecionam para cá. Nesta fatia
 * ele abre o formulário público com o código do ponto; a fatia da tela de nota
 * troca o destino, e o cartaz que já está na parede continua valendo.
 *
 * Quem decide se o caso entra com origem é o servidor, pelo código: ponto
 * ativo grava a origem, ponto aposentado ou código que ninguém cadastrou entra
 * sem origem, e nunca numa página de erro (ADR 0036, decisão 6).
 */

import { useParams } from "next/navigation";
import { ManifestacaoPublica } from "@/components/ouvidoria/ManifestacaoPublica";

export default function EnderecoCurtoDoCartaz() {
  const { codigo } = useParams<{ codigo: string }>();
  return <ManifestacaoPublica codigoDoCartaz={codigo ?? null} />;
}
