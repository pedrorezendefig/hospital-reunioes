#!/usr/bin/env bash
# Instala (ou remove) o dashboard do workflow como serviço do macOS (launchd).
#
#   tools/workflow-dashboard/install-launchd.sh            # instala/atualiza
#   tools/workflow-dashboard/install-launchd.sh uninstall  # remove
#
# Rode a partir da ÁRVORE PRINCIPAL do repo (não de um worktree de issue):
# o serviço fica apontando para o caminho onde este script mora, e worktrees
# de issue são apagados depois do merge.
set -euo pipefail

LABEL="com.hospital-reunioes.workflow-dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/workflow-dashboard.log"
PORT=8799
DOMAIN="gui/$(id -u)"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVE="$ROOT/tools/workflow-dashboard/serve.py"

if [[ "${1:-}" == "uninstall" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ serviço removido ($LABEL)"
  exit 0
fi

# worktree de issue tem .git como arquivo; a árvore principal tem diretório
if [[ -f "$ROOT/.git" ]]; then
  echo "✗ $ROOT parece ser um worktree de issue (efêmero)." >&2
  echo "  Rode este script a partir da árvore principal do repo." >&2
  exit 1
fi

PYTHON3="$(command -v python3)"
GH_BIN="$(command -v gh || true)"
if [[ -z "$GH_BIN" ]]; then
  echo "⚠ gh não encontrado no PATH — a aba de issues ficará vazia." >&2
fi
# launchd nasce com PATH mínimo (/usr/bin:/bin); injeta python3/gh/git
SVC_PATH="$(dirname "$PYTHON3"):${GH_BIN:+$(dirname "$GH_BIN"):}/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON3</string>
    <string>$SERVE</string>
    <string>--port</string><string>$PORT</string>
    <string>--no-open</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$SVC_PATH</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "✓ serviço instalado: $LABEL"
echo "  painel:  http://localhost:$PORT"
echo "  logs:    $LOG"
echo "  remover: tools/workflow-dashboard/install-launchd.sh uninstall"
