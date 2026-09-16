#!/usr/bin/env bash
# Traz os MP4 dos sete vídeos de capítulo da Ouvidoria para public/video/.
#
# Os capítulos foram gravados uma vez, em 03/09/2026, e não se regeram na
# migração do manual (issue #738): as composições vieram para
# docs/manual/video/ouvidoria/cap-N/ e o MP4 continua fora do git, como manda a
# decisão 3 do ADR 0057. Este script é o caminho de volta do arquivo para quem
# clonou o repositório ou vai publicar.
#
# Rode antes de `bash docs/manual/publicar.sh`: página publicada que exibe
# vídeo sem o arquivo trava a publicação de propósito.
#
# Uso: bash docs/manual/video/ouvidoria/trazer-mp4-dos-capitulos.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
DESTINO="$RAIZ/docs/manual/public/video/ouvidoria"
# A cópia que a apresentação em pptx já baixou, quando ela existe nesta máquina.
CACHE="$RAIZ/docs/comunicacao/ouvidoria/apresentacao/videos"
# O manual antigo, enquanto ele ainda serve os arquivos. Quando o
# redirecionamento de docs/manual/redirecionamento/ subir, este endereço passa a
# responder com o site novo e deixa de servir MP4: a partir daí a origem é o
# próprio site publicado.
ANTIGO="https://manual-ouvidoria-hsm.vercel.app"

mkdir -p "$DESTINO"
FALTANDO=""
for n in 1 2 3 4 5 6 7; do
  alvo="$DESTINO/cap-$n.mp4"
  if [ -f "$alvo" ]; then
    echo "cap-$n: já está aqui"
    continue
  fi
  if [ -f "$CACHE/video-cap$n.mp4" ]; then
    cp "$CACHE/video-cap$n.mp4" "$alvo"
    echo "cap-$n: copiado da apresentação"
    continue
  fi
  if curl -fsL -o "$alvo" "$ANTIGO/video-cap$n.mp4"; then
    echo "cap-$n: baixado do manual antigo"
  else
    rm -f "$alvo"
    FALTANDO="$FALTANDO cap-$n"
  fi
done

if [ -n "$FALTANDO" ]; then
  echo "não consegui trazer:$FALTANDO" >&2
  echo "a composição de cada um está em docs/manual/video/ouvidoria/, e o render é" >&2
  echo "  npx --yes hyperframes@0.8.41 render --quality high -o <destino>" >&2
  exit 1
fi
echo "os sete capítulos estão em $DESTINO"
