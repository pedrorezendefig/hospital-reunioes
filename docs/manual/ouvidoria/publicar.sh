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

# Os MP4 não ficam no git (.gitignore desta pasta), mas o index.html aponta para
# eles e cada deploy da Vercel é uma cópia nova: publicar sem os arquivos deixa
# todos os quadros de vídeo quebrados no manual do time. Por isso a falta trava a
# publicação em vez de passar batido.
VIDEOS=$(grep -oE 'src="[^"]+\.mp4"' "$ORIGEM/index.html" | sed 's/^src="//; s/"$//' | sort -u)
FALTANDO=""
for v in $VIDEOS; do
  if [ -f "$ORIGEM/$v" ]; then
    cp "$ORIGEM/$v" "$DESTINO/$v"
  else
    FALTANDO="$FALTANDO $v"
  fi
done
if [ -n "$FALTANDO" ]; then
  echo "vídeos que o index.html usa e não estão nesta pasta:$FALTANDO" >&2
  echo "baixe do manual publicado antes de republicar:" >&2
  echo "  for v in$FALTANDO; do curl -fL -o \"$ORIGEM/\$v\" \"https://manual-ouvidoria-hsm.vercel.app/\$v\"; done" >&2
  exit 1
fi

echo "pronto em $DESTINO ($(ls "$DESTINO" | tr '\n' ' '))"
if [ "${1:-}" = "--dry-run" ]; then
  echo "dry-run: nada publicado."
  exit 0
fi
cd "$DESTINO" && npx vercel@latest deploy --prod --yes
[ -d "$DESTINO/.vercel" ] && cp -R "$DESTINO/.vercel" "$ORIGEM"/ && echo "vínculo .vercel guardado (fica fora do git)"
