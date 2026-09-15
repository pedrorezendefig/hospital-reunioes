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
#
# O parsing só entende `src="...mp4"`. Um src fora desse formato não seria
# copiado NEM reportado: a trava falharia aberta, publicando um vídeo a menos e
# saindo com sucesso, que é exatamente o que ela existe para impedir. Por isso o
# piso de sanidade: quantos .mp4 aparecem DENTRO de atributo tem que bater com
# quantos o parsing reconheceu.
#
# A contagem é de `=` seguido do valor, e não da string `.mp4` solta: `.mp4` em
# comentário HTML ou em prosa visível ("os vídeos são arquivos .mp4") não é src
# nenhum, e contá-lo faria uma frase inocente do manual impedir toda
# republicação, mandando a pessoa caçar um src quebrado que não existe.
#
# As três buscas ignoram a caixa. `grep -o '\.mp4'` e um parsing sensível a
# maiúsculas deixariam `src="video.MP4"` escapar das DUAS contagens ao mesmo
# tempo: o piso bateria e o vídeo sumiria do deploy, a mesma falha aberta de
# antes com outra roupa.
MENCOES=$(grep -oiE '=[[:space:]]*["'"'"'][^"'"'"']+\.mp4["'"'"']' "$ORIGEM/index.html" | wc -l | tr -d ' ')
BRUTOS=$(grep -oiE 'src="[^"]+\.mp4"' "$ORIGEM/index.html" | sed 's/^[Ss][Rr][Cc]="//; s/"$//')
RECONHECIDOS=$(printf '%s\n' "$BRUTOS" | grep -c . || true)
if [ "$RECONHECIDOS" != "$MENCOES" ]; then
  echo "o index.html tem $MENCOES atributos apontando para .mp4 e o parsing reconheceu $RECONHECIDOS." >&2
  echo "algum deles saiu do formato src=\"...\": conserte o parsing antes de publicar," >&2
  echo "senão o vídeo que escapou some do deploy sem ninguém avisar." >&2
  exit 1
fi

VIDEOS=$(printf '%s\n' "$BRUTOS" | sort -u)
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

# `[ -d ... ] && cp && echo` como última linha faz o script sair 1 quando não há
# .vercel, ou seja, anunciar falha depois de publicar com sucesso. Em bloco, o
# status final é o do deploy.
if [ -d "$DESTINO/.vercel" ]; then
  cp -R "$DESTINO/.vercel" "$ORIGEM"/
  echo "vínculo .vercel guardado (fica fora do git)"
fi
