#!/usr/bin/env bash
set -euo pipefail

# import_planmode.sh — Importa plano do plan mode pra docs/planejamento/em-andamento/plan-mode/.
#
# Uso:
#   import_planmode.sh                          # mais recente em ~/.claude/plans/
#   import_planmode.sh --source <path>          # arquivo específico
#   import_planmode.sh <hook-input-json>        # chamado pelo hook PostToolUse:ExitPlanMode
#
# Não commita — deixa o arquivo staged.

show_help() {
  cat <<EOF
Uso:
  import_planmode.sh                          # importa o mais recente em ~/.claude/plans/
  import_planmode.sh --source <path>          # importa arquivo específico
  import_planmode.sh <hook-input-json>        # chamado pelo hook ExitPlanMode

Copia o plano externo pra docs/planejamento/em-andamento/plan-mode/<timestamp>-<slug>.md
adicionando frontmatter mínimo + bloco de header de progresso vazio.

Idempotente: se já existir arquivo com mesmo slug nos últimos 60s, skipa.
Skipa silencioso se docs/planejamento/em-andamento/plan-mode/ não existir.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

DEST_DIR="docs/planejamento/em-andamento/plan-mode"
if [[ ! -d "$DEST_DIR" ]]; then
  echo "Pasta '$DEST_DIR' não existe no CWD ($(pwd)) — skip silencioso" >&2
  exit 0
fi

SOURCE=""
if [[ "${1:-}" == "--source" && -n "${2:-}" ]]; then
  SOURCE="$2"
elif [[ -n "${1:-}" && "${1:0:1}" == "{" ]]; then
  HOOK_CWD=$(echo "${1}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('cwd', ''))" 2>/dev/null || echo "")
  if [[ -n "$HOOK_CWD" && "$HOOK_CWD" != "$(pwd)" ]]; then
    cd "$HOOK_CWD" 2>/dev/null || true
  fi
  SOURCE=$(ls -t ~/.claude/plans/*.md 2>/dev/null | head -1)
else
  SOURCE=$(ls -t ~/.claude/plans/*.md 2>/dev/null | head -1)
fi

if [[ -z "$SOURCE" || ! -f "$SOURCE" ]]; then
  echo "ERRO: sem source válido (tentou $SOURCE)" >&2
  exit 1
fi

H1=$(head -20 "$SOURCE" | grep -m 1 "^# " | head -1 | sed 's/^# *//')
if [[ -n "$H1" ]]; then
  SLUG=$(echo "$H1" | python3 -c "
import sys, re, unicodedata
text = sys.stdin.read().strip()
text = ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))
text = re.sub(r'[—–-]', ' ', text)
text = re.sub(r'[^a-zA-Z0-9]+', '-', text).lower().strip('-')
print(text[:60])
")
else
  SLUG=$(basename "$SOURCE" .md | sed 's/^image-[0-9]*-//' | cut -c 1-60)
fi

if [[ -z "$SLUG" ]]; then
  SLUG="plano-sem-titulo"
fi

NOW=$(date "+%Y-%m-%d-%H%M")
NOW_HUMAN=$(date "+%Y-%m-%d %H:%M")
NOW_ISO=$(date "+%Y-%m-%dT%H:%M:%S%z" | sed 's/\(..\)$/:\1/')
DEST="$DEST_DIR/$NOW-$SLUG.md"

EXISTING=$(find "$DEST_DIR" -name "*-$SLUG.md" -newermt "60 seconds ago" 2>/dev/null | head -1 || true)
if [[ -n "$EXISTING" ]]; then
  echo "[noop] Plano '$SLUG' já importado em $EXISTING (últimos 60s)"
  exit 0
fi

BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "nenhum")

TITLE=$(echo "$H1" | sed 's/"/\\"/g')
if [[ -z "$TITLE" ]]; then
  TITLE="Plano importado de $(basename "$SOURCE")"
fi

{
  cat <<EOF
---
slug: $SLUG
title: "$TITLE"
status: rascunho
plan_source: plan-mode-claude
author: Pedro Rezende <pmrdef@gmail.com>
date_created: $NOW_ISO
date_last_touched: $NOW_ISO
branch: $BRANCH
chronicle: null
pr: null
sha_inicio: $SHA
sha_atual: $SHA
estimativa_horas: null
fase_atual: "importado do plan mode — aguardando refinamento"
fase_numero: 1
fases_total: 1
tarefas_total: 0
tarefas_concluidas: 0
imported_from: $SOURCE
---

> ## Progresso: 0%
> **Fase 1 de 1** — importado do plan mode — aguardando refinamento
> **0 de 0 tarefas** concluídas
> **Última atualização:** $NOW_HUMAN · SHA \`$SHA\`
> **Branch:** \`$BRANCH\`

EOF
  cat "$SOURCE"
} > "$DEST"

git add "$DEST" 2>/dev/null || true

echo "✓ Plano importado em $DEST"
echo "  Source: $SOURCE"
echo "  Próximo passo: revise frontmatter (fase_atual, fases_total) + rode 'bash .claude/skills/planejamento/scripts/recalc_progress.sh $DEST'"
