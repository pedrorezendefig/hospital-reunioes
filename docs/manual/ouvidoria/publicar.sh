#!/usr/bin/env bash
# Publica o manual da Ouvidoria na Vercel.
#
# Logo e fonte não vivem nesta pasta (ADR 0044, decisão 4): a cópia única está em
# docs/comunicacao/_assets/. Este script traz os dois antes de publicar, copia a
# pasta para fora do repo (a Vercel recusa publicar de dentro de um repo git com
# outro projeto vinculado) e sobe.
#
# Uso: bash docs/manual/ouvidoria/publicar.sh [--dry-run]
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ORIGEM="$RAIZ/docs/manual/ouvidoria"
ASSETS="$RAIZ/docs/comunicacao/_assets"
DESTINO="${TMPDIR:-/tmp}/manual-ouvidoria-publish"

for a in "$ASSETS/logo-hsm.png" "$ASSETS/fonts/HPSimplified_Rg.ttf"; do
  [ -f "$a" ] || { echo "asset não encontrado: $a" >&2; exit 1; }
done

rm -rf "$DESTINO"; mkdir -p "$DESTINO"
cp -R "$ORIGEM"/index.html "$ORIGEM"/img "$DESTINO"/
cp "$ASSETS/logo-hsm.png" "$ASSETS/fonts/HPSimplified_Rg.ttf" "$DESTINO"/
[ -d "$ORIGEM/.vercel" ] && cp -R "$ORIGEM/.vercel" "$DESTINO"/

echo "pronto em $DESTINO ($(ls "$DESTINO" | tr '\n' ' '))"
if [ "${1:-}" = "--dry-run" ]; then
  echo "dry-run: nada publicado."
  exit 0
fi
cd "$DESTINO" && npx vercel@latest deploy --prod --yes
[ -d "$DESTINO/.vercel" ] && cp -R "$DESTINO/.vercel" "$ORIGEM"/ && echo "vínculo .vercel guardado (fica fora do git)"
