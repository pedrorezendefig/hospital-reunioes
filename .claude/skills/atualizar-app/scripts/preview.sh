#!/usr/bin/env bash
# preview.sh — diagnostica a stack docker-compose do Hospital Reuniões
# e imprime um bloco "isso é o que vai acontecer quando você rodar apply.sh".
#
# Uso:
#   bash .claude/skills/atualizar-app/scripts/preview.sh
#
# Saída:
#   - stdout: preview formatado para o usuário ler
#   - exit 0: preview ok, pode prosseguir
#   - exit 1: pré-requisito faltando (Docker off, .env ausente, etc.)

set -euo pipefail

# PATH precisa incluir o bin do Docker Desktop — por consistência com apply.sh,
# e porque alguns subcomandos `docker compose` também chamam o credential helper.
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"

# ── Localização ────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
COMPOSE_DIR="$REPO_ROOT/hospital-reunioes"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"

# Fallback: docker no PATH
if [ ! -x "$DOCKER" ]; then
  DOCKER="$(command -v docker || true)"
fi

# ── Pré-checagens ──────────────────────────────────────────────
fail() { printf '\n❌ %s\n' "$1" >&2; exit 1; }

[ -n "$DOCKER" ] || fail "Docker CLI não encontrado (nem em /Applications/Docker.app nem no PATH)."
"$DOCKER" ps >/dev/null 2>&1 || fail "Docker Desktop não está respondendo. Abra o Docker Desktop e tente de novo."
[ -f "$COMPOSE_FILE" ] || fail "docker-compose.yml não encontrado em $COMPOSE_FILE"
[ -f "$COMPOSE_DIR/.env" ] || fail ".env não encontrado em $COMPOSE_DIR/.env — docker compose precisa dele."

# ── Helpers ────────────────────────────────────────────────────
container_state() {
  # Retorna: "running" | "exited" | "absent"
  # Obs: docker inspect emite "\n" em stdout quando o container não existe,
  # mesmo com 2>/dev/null — por isso precisamos strip do output.
  local name="$1"
  local state
  state="$("$DOCKER" inspect -f '{{.State.Status}}' "$name" 2>/dev/null | tr -d '[:space:]')"
  [ -z "$state" ] && state="absent"
  echo "$state"
}

image_age_human() {
  # Idade da imagem do container (ou "sem container")
  local name="$1"
  local created
  created="$("$DOCKER" inspect -f '{{.Created}}' "$name" 2>/dev/null | tr -d '[:space:]')"
  if [ -z "$created" ]; then
    echo "sem container"
    return
  fi
  # macOS date: converte ISO → epoch
  local created_epoch now_epoch delta
  created_epoch="$(date -j -f "%Y-%m-%dT%H:%M:%S" "${created%%.*}" "+%s" 2>/dev/null || echo 0)"
  now_epoch="$(date +%s)"
  delta=$(( now_epoch - created_epoch ))
  if [ "$delta" -lt 120 ]; then
    echo "${delta}s atrás"
  elif [ "$delta" -lt 7200 ]; then
    echo "$(( delta / 60 ))min atrás"
  elif [ "$delta" -lt 172800 ]; then
    echo "$(( delta / 3600 ))h atrás"
  else
    echo "$(( delta / 86400 ))d atrás"
  fi
}

port_occupant() {
  # Retorna: "livre" | "hr-frontend" | "hr-backend" | "docker-alheio:<name>" | "processo:<cmd>:<pid>"
  local port="$1"
  local line
  line="$(lsof -iTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR==2 {print $1, $2}')"
  if [ -z "$line" ]; then
    echo "livre"
    return
  fi
  local cmd pid
  cmd="$(echo "$line" | awk '{print $1}')"
  pid="$(echo "$line" | awk '{print $2}')"

  # É docker? Descobre qual container publica essa porta.
  if [ "$cmd" = "com.docke" ] || [ "$cmd" = "com.docker.backend" ]; then
    local container
    container="$("$DOCKER" ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | awk -v p=":$port->" '$0 ~ p {print $1; exit}')"
    if [ -z "$container" ]; then
      echo "docker-desktop-nativo"
    elif [ "$container" = "hr-frontend" ] || [ "$container" = "hr-backend" ]; then
      echo "$container"
    else
      echo "docker-alheio:$container"
    fi
  else
    echo "processo:$cmd:$pid"
  fi
}

git_changes_summary() {
  # git diff --stat apenas nos paths passados; resume em 1 linha.
  # Considera unstaged + staged + untracked (para não perder arquivos novos).
  local path="$1"
  cd "$REPO_ROOT"
  local modified untracked
  modified="$(git diff --name-only HEAD -- "$path" 2>/dev/null | wc -l | tr -d ' ')"
  untracked="$(git ls-files --others --exclude-standard "$path" 2>/dev/null | wc -l | tr -d ' ')"
  local total=$(( modified + untracked ))
  if [ "$total" -eq 0 ]; then
    echo "sem mudanças desde HEAD"
  else
    local names
    names="$( { git diff --name-only HEAD -- "$path"; git ls-files --others --exclude-standard "$path"; } 2>/dev/null | head -3 | sed "s|${path}/||" | tr '\n' ',' | sed 's/,$//; s/,/, /g')"
    if [ "$total" -gt 3 ]; then
      echo "$total arquivos modificados ($names, +$((total - 3)) outros)"
    else
      echo "$total arquivos modificados ($names)"
    fi
  fi
}

# ── Coleta de estado ───────────────────────────────────────────
FE_STATE="$(container_state hr-frontend)"
BE_STATE="$(container_state hr-backend)"
FE_AGE="$(image_age_human hr-frontend)"
BE_AGE="$(image_age_human hr-backend)"

PORT_3000="$(port_occupant 3000)"
PORT_8000="$(port_occupant 8000)"

FE_DIFF="$(git_changes_summary "hospital-reunioes/frontend")"
BE_DIFF="$(git_changes_summary "hospital-reunioes/backend")"

# ── Detecta conflitos (portas ocupadas por algo não-nosso) ────
CONFLICTS=()
check_conflict() {
  local port="$1" expected="$2" actual="$3"
  case "$actual" in
    livre) return ;;  # livre → ok
    "$expected") return ;;  # nosso container → ok, vai ser derrubado pelo down
    docker-desktop-nativo) CONFLICTS+=("Porta :$port ocupada por Docker Desktop sem container — provável Docker Desktop nativo. Não sei derrubar; verifique manualmente.") ;;
    docker-alheio:*) CONFLICTS+=("Porta :$port ocupada por container alheio: ${actual#docker-alheio:}. Não será tocado automaticamente.") ;;
    processo:*)
      local cmd="${actual#processo:}"; cmd="${cmd%%:*}"
      local pid="${actual##*:}"
      CONFLICTS+=("Porta :$port ocupada por processo não-Docker: $cmd (PID $pid). Precisa confirmar antes de matar.")
      ;;
  esac
}
check_conflict 3000 hr-frontend "$PORT_3000"
check_conflict 8000 hr-backend "$PORT_8000"

# ── Decide o que vai rebuildar (heurística: diff git) ─────────
FE_WILL_REBUILD="com cache de layers"
BE_WILL_REBUILD="com cache de layers"
if [[ "$FE_DIFF" != "sem mudanças desde HEAD" ]]; then
  FE_WILL_REBUILD="mudanças em frontend/ → provável rebuild"
fi
if [[ "$BE_DIFF" != "sem mudanças desde HEAD" ]]; then
  BE_WILL_REBUILD="mudanças em backend/ → provável rebuild (volume monta /app/app, hot-reload cobre em runtime)"
fi

# ── Imprime o bloco ────────────────────────────────────────────
state_badge() {
  case "$1" in
    running) echo "rodando" ;;
    exited)  echo "parado" ;;
    absent)  echo "ausente" ;;
    *) echo "$1" ;;
  esac
}

fmt_port() {
  case "$1" in
    livre) echo "livre" ;;
    hr-frontend|hr-backend) echo "nosso ($1)" ;;
    docker-desktop-nativo) echo "⚠  Docker Desktop nativo" ;;
    docker-alheio:*) echo "⚠  container alheio: ${1#docker-alheio:}" ;;
    processo:*)
      local rest="${1#processo:}"
      local cmd="${rest%%:*}"; local pid="${rest##*:}"
      echo "⚠  processo: $cmd (PID $pid)" ;;
  esac
}

cat <<EOF
┌─ atualizar-app · preview ──────────────────────────────
│ Estado atual
│   hr-frontend     $(state_badge "$FE_STATE") · imagem $FE_AGE
│   hr-backend      $(state_badge "$BE_STATE") · imagem $BE_AGE
│   :3000           $(fmt_port "$PORT_3000")
│   :8000           $(fmt_port "$PORT_8000")
│
│ Mudanças desde HEAD
│   frontend/       $FE_DIFF
│   backend/        $BE_DIFF
│
│ O que vai acontecer
│   1. docker compose down                         (~2s)
│      → para e remove hr-frontend, hr-backend
│   2. docker compose up -d --build                (~5-60s, depende do cache)
│      → frontend: $FE_WILL_REBUILD
│      → backend:  $BE_WILL_REBUILD
│   3. aguarda healthcheck backend (/api/health → 200)
│   4. aguarda frontend responder 200 em :3000
│
│ Resultado esperado
│   Frontend  http://localhost:3000
│   Backend   http://localhost:8000/api
│
│ Não toca
│   Supabase CLI (54351–54362) · outros projetos · containers sem prefixo hr-
EOF

if [ "${#CONFLICTS[@]}" -gt 0 ]; then
  echo "│"
  echo "│ ⚠  Conflitos detectados — requerem atenção antes de prosseguir:"
  for c in "${CONFLICTS[@]}"; do
    echo "│   • $c"
  done
fi

echo "└────────────────────────────────────────────────────────"

# Exit code informativo: 0 = ok, 2 = tem conflito (ainda pode prosseguir se user confirmar)
if [ "${#CONFLICTS[@]}" -gt 0 ]; then
  exit 2
fi
exit 0
