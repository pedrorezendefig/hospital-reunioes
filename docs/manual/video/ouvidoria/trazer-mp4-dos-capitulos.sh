#!/usr/bin/env bash
# Traz os MP4 dos sete vídeos de capítulo da Ouvidoria para public/video/.
#
# Os capítulos foram gravados uma vez, em 03/09/2026, e não se regeram na
# migração do manual (issue #738): as composições vieram para
# docs/manual/video/ouvidoria/cap-N/ e o MP4 continua fora do git, como manda a
# decisão 3 do ADR 0057. Este script é o caminho de volta do arquivo para quem
# clonou o repositório ou vai publicar. Rode antes de `docs/manual/publicar.sh`:
# página publicada que exibe vídeo sem o arquivo trava a publicação de propósito.
#
# ONDE ESTÁ O MASTER. O original 1080p não está em lugar nenhum do repositório:
# a pasta da apresentação guarda uma cópia já reduzida a 720p e sem áudio (o
# `gerar.py` apaga o original depois de reencodar), e por isso ela NÃO serve de
# origem aqui, senão a publicação reencodaria em cima de uma derivada. O master
# vive hoje em dois lugares: o manual antigo publicado, que este PR está
# aposentando, e a cópia de trabalho desta entrega, que o `--de` aponta.
#
# DAQUI PARA A FRENTE o dono do master é o próprio site do manual: assim que a
# seção Ouvidoria publicar com os vídeos, `$NOVO/video/ouvidoria/cap-N.mp4`
# passa a ser a origem estável, e é ela que este script tenta primeiro. Por
# isso a ordem importa na hora de publicar: **suba o site novo com os vídeos
# antes de publicar o redirecionamento do endereço antigo**, senão o único
# master que resta é a cópia local de quem estiver com ela na máquina.
#
# Uso:
#   bash docs/manual/video/ouvidoria/trazer-mp4-dos-capitulos.sh [--de <pasta>]
#
#   --de <pasta>   pasta com uma cópia local dos sete (cap-N.mp4). Também pode
#                  vir pela variável de ambiente CAPITULOS_DE.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
DESTINO="$RAIZ/docs/manual/public/video/ouvidoria"
NOVO="https://manual-hsm.vercel.app"
ANTIGO="https://manual-ouvidoria-hsm.vercel.app"
COPIA="${CAPITULOS_DE:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --de) COPIA="$2"; shift ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
  shift
done

# MP4 de verdade tem "ftyp" a partir do quinto byte. Sem esta conferência, uma
# página de erro ou um redirecionamento seguido até o HTML de outro site entram
# na pasta com nome de vídeo, e a falha só aparece depois, no ffmpeg da
# publicação, quando já não há mais de onde baixar.
e_mp4() {
  [ -f "$1" ] && [ "$(dd if="$1" bs=1 skip=4 count=4 2>/dev/null)" = "ftyp" ]
}

# `-f` (erro de HTTP falha), `--max-redirs 0` (redirecionamento não é download:
# o endereço antigo passa a responder 308 para a home do manual novo assim que
# o redirecionamento sobe) e conferência do que chegou antes de manter o
# arquivo. Falha aqui é falha, não um HTML com nome de vídeo.
baixar() {
  local url="$1" alvo="$2"
  curl -fsS --max-redirs 0 -o "$alvo.parcial" "$url" 2>/dev/null || { rm -f "$alvo.parcial"; return 1; }
  if ! e_mp4 "$alvo.parcial"; then
    rm -f "$alvo.parcial"
    return 1
  fi
  mv "$alvo.parcial" "$alvo"
}

mkdir -p "$DESTINO"
FALTANDO=""
for n in 1 2 3 4 5 6 7; do
  alvo="$DESTINO/cap-$n.mp4"
  if e_mp4 "$alvo"; then
    echo "cap-$n: já está aqui"
    continue
  fi
  rm -f "$alvo"
  if [ -n "$COPIA" ] && e_mp4 "$COPIA/cap-$n.mp4"; then
    cp "$COPIA/cap-$n.mp4" "$alvo"
    echo "cap-$n: copiado de $COPIA"
  elif baixar "$NOVO/video/ouvidoria/cap-$n.mp4" "$alvo"; then
    echo "cap-$n: baixado do manual publicado"
  elif [ "$n" = "4" ] || [ "$n" = "6" ]; then
    # O manual antigo serve a gravação de 03/09, e no cap-4 e no cap-6 ela tem o
    # nome e o email de uma pessoa real desenhados na barra de topo (issue #738,
    # rodada 2 da revisão). A composição foi corrigida e os dois foram
    # re-renderizados; baixar do antigo traria o vídeo com o dado de volta.
    FALTANDO="$FALTANDO cap-$n"
  elif baixar "$ANTIGO/video-cap$n.mp4" "$alvo"; then
    echo "cap-$n: baixado do manual antigo"
  else
    FALTANDO="$FALTANDO cap-$n"
  fi
done

if [ -n "$FALTANDO" ]; then
  echo "não consegui trazer:$FALTANDO" >&2
  echo "as origens falharam, e cada uma falha por um motivo diferente:" >&2
  echo "  - a cópia local: passe --de <pasta> apontando para os cap-N.mp4;" >&2
  echo "  - o manual publicado: a seção Ouvidoria ainda não subiu com os vídeos;" >&2
  echo "  - o manual antigo: o endereço já redireciona, e download de HTML foi recusado." >&2
  echo "o cap-4 e o cap-6 nunca vêm do manual antigo: a gravação de lá mostra dados" >&2
  echo "de uma pessoa real, e os dois foram re-renderizados sem eles." >&2
  echo "a composição de cada capítulo está em docs/manual/video/ouvidoria/:" >&2
  echo "  npx --yes hyperframes@0.8.41 render --quality high -o <destino>" >&2
  exit 1
fi

echo
echo "os sete capítulos estão em $DESTINO:"
for n in 1 2 3 4 5 6 7; do
  alvo="$DESTINO/cap-$n.mp4"
  echo "  cap-$n.mp4  $(du -h "$alvo" | cut -f1)  $(file -b "$alvo")"
done
