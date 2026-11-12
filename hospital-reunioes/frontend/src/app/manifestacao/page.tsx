"use client";

/**
 * Formulário público da Ouvidoria pelo site do hospital, sem cartaz.
 *
 * Quem chega com o código de um cartaz (`/manifestacao?p=`, o formato de antes
 * da ADR 0086) é redirecionado ao endereço curto `/a/{código}` pelo
 * `next.config.ts`, antes de esta página abrir.
 */

import { ManifestacaoPublica } from "@/components/ouvidoria/ManifestacaoPublica";

export default function ManifestacaoPage() {
  return <ManifestacaoPublica codigoDoCartaz={null} />;
}
