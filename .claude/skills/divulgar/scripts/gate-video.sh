#!/usr/bin/env bash
# Gate anti-travamento do vídeo da /divulgar (regra 10 do CLAUDE.md global).
#
# Três provas, e o vídeo só é entregue se as três passam:
#   1. fps constante 30 (r_frame_rate e avg_frame_rate iguais a 30/1);
#   2. nenhum congelamento de 0,5 s ou mais fora das paradas planejadas
#      (ffmpeg freezedetect=n=-60dB:d=0.5);
#   3. o MP4 toca no Chrome real (Playwright com channel="chrome", servido por
#      HTTP: o Chromium do Playwright não tem H.264 e acusaria erro em todo MP4).
#
# Uso: bash gate-video.sh <video.mp4> [--parada INICIO-FIM ...]
#   --parada  janela em segundos onde uma imagem parada é planejada (por
#             exemplo a logo inteira e parada da assinatura, 41.5-44). Um
#             congelamento só passa se cabe inteiro numa janela declarada.
# Saída 0 = passou; 1 = reprovado (não entrega); 2 = uso errado.
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: bash gate-video.sh <video.mp4> [--parada INICIO-FIM ...]" >&2; exit 2; }
VIDEO="$1"; shift
[ -f "$VIDEO" ] || { echo "vídeo não encontrado: $VIDEO" >&2; exit 2; }
PARADAS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --parada) PARADAS="$PARADAS $2"; shift ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
  shift
done
FALHOU=""

echo "== 1. fps constante 30"
FPS=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=r_frame_rate,avg_frame_rate -of csv=p=0 "$VIDEO")
if [ "$FPS" = "30/1,30/1" ]; then
  echo "ok ($FPS)"
else
  echo "REPROVADO: r_frame_rate,avg_frame_rate = $FPS (esperado 30/1,30/1)"
  FALHOU=1
fi

echo "== 2. congelamento de 0,5 s ou mais"
METADADOS=$(ffmpeg -nostdin -hide_banner -i "$VIDEO" \
  -vf "freezedetect=n=-60dB:d=0.5,metadata=mode=print:file=-" -map 0:v -f null - 2>/dev/null)
CONGELAS=$(printf '%s\n' "$METADADOS" \
  | awk -F= '/freeze_start/ { s = $2 } /freeze_end/ { print s, $2 }')
# Congelamento que vai até o fim do vídeo não tem freeze_end: o fim é a duração.
INICIO_ABERTO=$(printf '%s\n' "$METADADOS" \
  | awk -F= '/freeze_start/ { s = $2; aberto = 1 } /freeze_end/ { aberto = 0 } END { if (aberto) print s }')
if [ -n "$INICIO_ABERTO" ]; then
  DURACAO=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
  CONGELAS="$CONGELAS
$INICIO_ABERTO $DURACAO"
fi
NAO_PLANEJADOS=0
while read -r ini fim; do
  [ -n "$ini" ] || continue
  planejado=""
  for janela in $PARADAS; do
    a="${janela%-*}"; b="${janela#*-}"
    if awk -v i="$ini" -v f="$fim" -v a="$a" -v b="$b" 'BEGIN { exit !(i >= a && f <= b) }'; then
      planejado=1
    fi
  done
  if [ -n "$planejado" ]; then
    echo "parada planejada: $ini s a $fim s"
  else
    echo "REPROVADO: imagem parada de $ini s a $fim s fora das paradas planejadas"
    NAO_PLANEJADOS=$((NAO_PLANEJADOS + 1))
  fi
done <<EOF
$CONGELAS
EOF
if [ "$NAO_PLANEJADOS" -eq 0 ]; then echo "ok"; else FALHOU=1; fi

echo "== 3. toca no Chrome real"
PASTA=$(cd "$(dirname "$VIDEO")" && pwd)
ARQUIVO=$(basename "$VIDEO")
PY="${PYTHON:-python3}"
if ! "$PY" -c "import playwright" 2>/dev/null; then
  echo "REPROVADO: $PY sem o pacote playwright (pip install playwright, ou PYTHON=<python que tem>)"
  FALHOU=1
else
  if ! "$PY" - "$PASTA" "$ARQUIVO" <<'PYEOF'
import functools, http.server, sys, threading, urllib.parse
from playwright.sync_api import sync_playwright

pasta, arquivo = sys.argv[1], sys.argv[2]
class Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


servidor = http.server.ThreadingHTTPServer(
    ("127.0.0.1", 0), functools.partial(Quieto, directory=pasta)
)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{servidor.server_port}/{urllib.parse.quote(arquivo)}"

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    pagina = navegador.new_page()
    pagina.set_content(f'<video id="v" muted playsinline src="{url}"></video>')
    pagina.evaluate("document.getElementById('v').play()")
    pagina.wait_for_timeout(3000)
    estado = pagina.evaluate(
        "(() => { const v = document.getElementById('v');"
        " return {erro: v.error && v.error.code, pronto: v.readyState,"
        " duracao: v.duration, tempo: v.currentTime}; })()"
    )
    navegador.close()
servidor.shutdown()

ok = (
    not estado["erro"]
    and estado["pronto"] >= 2
    and estado["duracao"] > 0
    and estado["tempo"] > 1
)
print(("ok " if ok else "REPROVADO: ") + str(estado))
sys.exit(0 if ok else 1)
PYEOF
  then
    FALHOU=1
  fi
fi

if [ -n "$FALHOU" ]; then
  echo "GATE REPROVADO: não entregue este vídeo."
  exit 1
fi
echo "GATE OK"
