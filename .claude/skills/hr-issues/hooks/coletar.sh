#!/bin/bash
# Coleta do hr-issues: a visão do /minhas-issues em JSON (minhas_issues.py --json), só leitura.
# Cache em $TMPDIR/hr-issues/visao.json, compartilhado por todas as sessões: sem argumento,
# só recoleta com mais de 5 min; com --fresco (um gh que mudou issue ou PR), com mais de 30 s.
# Uma trava faz uma sessão só buscar; as outras leem o cache. Imprime o JSON numa linha.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
umask 077
# $TMPDIR do macOS já é do usuário; sem ele, ~/.cache (nunca o /tmp compartilhado)
BASE="${TMPDIR:-$HOME/.cache}"; BASE="${BASE%/}"
CACHE_DIR="${HR_ISSUES_CACHE:-$BASE/hr-issues}"; CACHE="$CACHE_DIR/visao.json"; TRAVA="$CACHE_DIR/trava"
RAIZ="$(cd "$(dirname "$0")/../../../.." && pwd)"
SCRIPT="$RAIZ/.claude/skills/minhas-issues/scripts/minhas_issues.py"
mkdir -p "$CACHE_DIR"
# pasta de outro dono ou link simbólico: não escreve nada nela
if [ -L "$CACHE_DIR" ] || [ ! -O "$CACHE_DIR" ]; then echo "cache $CACHE_DIR não é do usuário" >&2; exit 2; fi

limite=300
[ "$1" = "--fresco" ] && limite=30

idade() { echo $(( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0) )); }

if [ -s "$CACHE" ] && [ "$(idade "$CACHE")" -lt "$limite" ]; then
  cat "$CACHE"; exit 0
fi

# trava velha (sessão que morreu no meio) some depois de 3 min
[ -d "$TRAVA" ] && [ "$(idade "$TRAVA")" -gt 180 ] && rmdir "$TRAVA" 2>/dev/null
if ! mkdir "$TRAVA" 2>/dev/null; then
  [ -s "$CACHE" ] && { cat "$CACHE"; exit 0; }
  echo "outra sessão está coletando" >&2; exit 3
fi
trap 'rmdir "$TRAVA" 2>/dev/null' EXIT

cd "$RAIZ" || exit 2
novo="$CACHE.$$"
if python3 "$SCRIPT" --json > "$novo" 2> "$CACHE_DIR/erro.txt" && [ -s "$novo" ]; then
  mv "$novo" "$CACHE"
  cat "$CACHE"
else
  rm -f "$novo"
  head -c 300 "$CACHE_DIR/erro.txt" >&2
  exit 1
fi
