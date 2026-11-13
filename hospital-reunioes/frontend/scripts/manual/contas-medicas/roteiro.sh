#!/usr/bin/env bash
# Refaz os prints da página de Contas médicas do manual (issue #1724, ADR 0094,
# decisão 5) pelo playwright-cli, contra o app LOCAL e com o seed fictício.
#
# Uso (com o Supabase local e o app local no ar):
#   bash hospital-reunioes/frontend/scripts/manual/contas-medicas/roteiro.sh
#   BASE=http://localhost:3010 bash .../roteiro.sh
#   ENV_LOCAL=/caminho/do/.env bash .../roteiro.sh   (padrão: hospital-reunioes/.env)
#
# O roteiro semeia antes (semear.py), entra como a faturista de exemplo e
# fotografa numa pasta de rascunho. Antes de levar os PNGs para a página, a
# guarda lê o texto de cada print e recusa tudo se algum mostra o nome de uma
# pessoa ou de um paciente que o seed não pôs no banco: o repositório é público.

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/contas-medicas"
BASE="${BASE:-http://localhost:3000}"
SESSAO="manual-contas-medicas-1724"

case "$BASE" in
  http://localhost:*|http://127.0.0.1:*) ;;
  *) echo "recusado: '$BASE' não é o app local." >&2; exit 1 ;;
esac

python3 "$AQUI/semear.py"

RASCUNHO="$(mktemp -d)"
trap 'rm -rf "$RASCUNHO"; playwright-cli -s="$SESSAO" close >/dev/null 2>&1 || true' EXIT

# O prints.js com o endereço, a pasta de rascunho e o seed no lugar das marcas.
CODIGO="$(python3 - "$AQUI" "$BASE" "$RASCUNHO" <<'PY'
import json, pathlib, sys
aqui, base, saida = sys.argv[1:4]
seed = json.loads(pathlib.Path(aqui, "seed.json").read_text(encoding="utf-8"))
codigo = pathlib.Path(aqui, "prints.js").read_text(encoding="utf-8")
print(
    codigo.replace("__BASE__", base)
    .replace("__SAIDA__", saida)
    .replace("__SEED__", json.dumps(seed, ensure_ascii=False))
)
PY
)"

playwright-cli -s="$SESSAO" open "$BASE/login" >/dev/null
playwright-cli -s="$SESSAO" resize 1440 900 >/dev/null
playwright-cli -s="$SESSAO" run-code "$CODIGO" >"$RASCUNHO/saida.txt" || true
if ! grep -q '^### Result' "$RASCUNHO/saida.txt" || grep -q '^### Error' "$RASCUNHO/saida.txt"; then
  echo "falhou: os prints não saíram." >&2
  sed -n '/### Error/,/###/p' "$RASCUNHO/saida.txt" >&2
  exit 1
fi

# O run-code devolve, na linha depois de "### Result", o texto de cada print
# como uma string JSON.
python3 - "$RASCUNHO/saida.txt" "$RASCUNHO/textos.json" <<'PY'
import json, pathlib, sys
linhas = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
resultado = json.loads(linhas[linhas.index("### Result") + 1])
pathlib.Path(sys.argv[2]).write_text(resultado, encoding="utf-8")
PY

python3 "$AQUI/semear.py" --guarda "$RASCUNHO/textos.json"

mkdir -p "$SAIDA"
echo "prints em $SAIDA:"
for png in "$RASCUNHO"/*.png; do
  mv "$png" "$SAIDA/"
  echo "  $(basename "$png")"
done
