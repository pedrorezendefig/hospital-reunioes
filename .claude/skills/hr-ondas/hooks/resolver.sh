#!/bin/bash
# O botão resolver do "Precisa de você": abre a sessão de um item no Claude Agents.
#
# Uso: resolver.sh <nome-da-sessao> [--viva <sessao>]   (o pedido chega pela entrada padrão)
#
# 1. Com --viva e essa sessão rodando (a da própria Onda), ou com uma sessão de mesmo nome já rodando
#    (clique repetido), não lança nada.
# 2. Senão, lança a sessão de fundo pelo lancar_sessao.sh da onda (ambiente limpo, sem MCP), na pasta
#    principal do Projeto, com o pedido num arquivo temporário apagado logo depois.
# 3. Traz para a frente a aba do Terminal que já roda o `claude agents --cwd <pasta>`; sem ela, abre uma
#    janela nova com ele. É ali que a sessão aparece para o humano entrar.
# A última linha da saída é o aviso que o painel mostra.
set -u
export PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

NOME="${1:-}"; shift || true
VIVA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --viva) VIVA="${2:-}"; shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
  shift
done
valido() { case "$1" in ''|-*|*[!A-Za-z0-9._-]*) return 1 ;; esac; }
valido "$NOME" || { echo "nome de sessão inválido: $NOME" >&2; exit 2; }
[ -z "$VIVA" ] || valido "$VIVA" || { echo "sessão inválida: $VIVA" >&2; exit 2; }

AQUI="$(cd "$(dirname "$0")" && pwd)"
COMUM=$(git -C "$AQUI" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || {
  echo "não achei o repositório de $AQUI" >&2; exit 1; }
PASTA="$(dirname "$COMUM")"
case "$PASTA" in /*) ;; *) echo "pasta inválida: $PASTA" >&2; exit 1 ;; esac
case "$PASTA" in *[\"\'\\]*) echo "pasta com aspas não vai para o Terminal: $PASTA" >&2; exit 1 ;; esac

viva() { claude agents --json 2>/dev/null | jq -e --arg n "$1" 'any(.[]; .name == $n)' >/dev/null; }

if [ -n "$VIVA" ] && viva "$VIVA"; then
  aviso="A sessão $VIVA já cuida disso: entre nela no Claude Agents"
elif viva "$NOME"; then
  aviso="A sessão $NOME já está aberta no Claude Agents"
else
  PEDIDO="$(cat)"
  [ -n "$PEDIDO" ] || { echo "pedido vazio" >&2; exit 2; }
  LANCAR="$PASTA/.claude/skills/onda-enxuta/scripts/lancar_sessao.sh"
  [ -f "$LANCAR" ] || { echo "sem o lançador em $LANCAR" >&2; exit 1; }
  arq=$(mktemp "${TMPDIR:-/tmp}/hr-ondas-pedido.XXXXXX") || exit 1
  printf '%s\n' "$PEDIDO" > "$arq"
  saida=$(bash "$LANCAR" "$NOME" "$arq" --cwd "$PASTA" 2>&1); r=$?
  rm -f "$arq"
  [ $r = 0 ] || { echo "$saida" | tail -3 >&2; exit $r; }
  aviso="Sessão $NOME aberta: entre nela no Claude Agents"
fi

# A aba que já roda o `claude agents --cwd <pasta>`, pelo tty (o mesmo jeito do PedroOS, terminal.js)
tty=$(ps -A -o tty=,args= | awk -v alvo="claude agents --cwd $PASTA" '
  { t = $1; $1 = ""; sub(/^ +/, ""); sub(/^[^ ]*\//, ""); sub(/ +$/, ""); if ($0 == alvo && t ~ /^ttys[0-9]+$/) { print t; exit } }')
focou=nao
if [ -n "$tty" ]; then
  focou=$(osascript -e 'tell application "Terminal"' -e 'repeat with w in windows' -e 'repeat with t in tabs of w' \
    -e "if tty of t is \"/dev/$tty\" then" -e 'set selected of t to true' -e 'set index of w to 1' -e 'activate' \
    -e 'return "sim"' -e 'end if' -e 'end repeat' -e 'end repeat' -e 'return "nao"' -e 'end tell' 2>/dev/null)
fi
if [ "$focou" != sim ]; then
  osascript -e 'tell application "Terminal"' -e 'activate' \
    -e "do script \"cd '$PASTA' && env -u ANTHROPIC_API_KEY claude agents --cwd '$PASTA'\"" -e 'end tell' >/dev/null || {
    echo "$aviso, mas não consegui abrir o Terminal: rode claude agents --cwd $PASTA"; exit 0; }
fi
echo "$aviso"
