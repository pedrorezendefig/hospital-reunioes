#!/usr/bin/env bash
# Publica o Manual do usuário na Vercel (ADR 0057, decisões 5 e 6).
#
# Um comando só: lint do texto, build do Starlight, conferidor do draft, vídeos
# reencodados para 720p, trava de tamanho e deploy de uma cópia fora do repo (a
# Vercel recusa publicar de dentro de um repo com outro projeto vinculado, a
# mesma pedra da /divulgar).
#
# Uso: bash docs/manual/publicar.sh [--dry-run] [--saida <dir>] [--pular-build]
#   --dry-run      monta a pasta e para antes de publicar.
#   --saida        pasta de montagem (padrão: $TMPDIR/manual-hsm).
#   --pular-build  usa a pasta de saída como ela está, sem lint nem build. É o
#                  seam dos testes da trava de tamanho e do reencode, e serve
#                  para republicar uma saída já montada.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE="$RAIZ/docs/manual"
TETO_MB=90

DRY_RUN=""
PULAR_BUILD=""
# O nome da pasta vira o nome do projeto no primeiro deploy da Vercel.
SAIDA="${TMPDIR:-/tmp}/manual-hsm"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --pular-build) PULAR_BUILD=1 ;;
    --saida) SAIDA="$2"; shift ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$PULAR_BUILD" ]; then
  echo "== lint do manual"
  python3 "$RAIZ/tools/lint_manual.py" --dir "$SITE/src/content/docs"

  echo "== build do site"
  (cd "$SITE" && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build)

  echo "== conferindo o que ficou em draft"
  python3 "$RAIZ/tools/checar_build_manual.py" --dir "$SITE"

  rm -rf "$SAIDA"
  mkdir -p "$SAIDA"
  cp -R "$SITE/dist/." "$SAIDA/"
  [ -d "$SITE/.vercel" ] && cp -R "$SITE/.vercel" "$SAIDA/"
fi

# Os MP4 que as páginas usam. Vídeo de tarefa nasce em public/video/ e já vem no
# dist; Vídeo de percepção de valor que a página de Novidades embute mora em
# docs/comunicacao/ e é copiado aqui. O que a página aponta e ninguém acha trava
# a publicação: subir com o quadro do vídeo quebrado é pior do que não subir.
echo "== vídeos"
VIDEOS=$(grep -rhoiE 'src="[^"]+\.mp4"' "$SAIDA" --include="*.html" | sed 's/^[Ss][Rr][Cc]="//; s/"$//' | sort -u || true)
FALTANDO=""
for caminho in $VIDEOS; do
  destino="$SAIDA/${caminho#/}"
  if [ ! -f "$destino" ]; then
    origem=$(find "$RAIZ/docs/comunicacao" -name "$(basename "$caminho")" -type f | head -1)
    if [ -n "$origem" ]; then
      mkdir -p "$(dirname "$destino")"
      cp "$origem" "$destino"
    else
      FALTANDO="$FALTANDO $(basename "$caminho")"
      continue
    fi
  fi
  # 720p H.264 no lugar: vídeo que já é menor não cresce.
  temporario="$destino.720.mp4"
  ffmpeg -y -loglevel error -i "$destino" \
    -vf "scale=-2:'min(720,ih)'" -c:v libx264 -preset veryfast -crf 28 \
    -movflags +faststart -c:a aac -b:a 96k "$temporario"
  mv "$temporario" "$destino"
done
if [ -n "$FALTANDO" ]; then
  echo "vídeo que a página usa e não existe nem em docs/comunicacao:$FALTANDO" >&2
  echo "renderize a composição do vídeo antes de publicar." >&2
  exit 1
fi

TAMANHO_MB=$(( $(du -sk "$SAIDA" | cut -f1) / 1024 ))
echo "== tamanho da publicação: ${TAMANHO_MB} MB (teto ${TETO_MB} MB)"
if [ "$TAMANHO_MB" -gt "$TETO_MB" ]; then
  echo "a pasta a publicar tem ${TAMANHO_MB} MB e o teto é ${TETO_MB} MB." >&2
  echo "o plano onde o site mora recusa acima de 100 MB: corte ou encurte vídeo antes de publicar." >&2
  exit 1
fi

if [ -n "$DRY_RUN" ]; then
  echo "dry-run: nada publicado. A pasta pronta ficou em $SAIDA"
  exit 0
fi

(cd "$SAIDA" && npx vercel@latest deploy --prod --yes)

# Em bloco, e não com `&&` na última linha: sem o .vercel o script sairia 1 e
# anunciaria falha depois de publicar com sucesso.
if [ -d "$SAIDA/.vercel" ]; then
  cp -R "$SAIDA/.vercel" "$SITE/"
  echo "vínculo .vercel guardado (fica fora do git)"
fi
