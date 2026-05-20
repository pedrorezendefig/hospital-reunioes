#!/usr/bin/env bash
# apply.sh — derruba e reconstrói a stack docker-compose do Hospital Reuniões
# com o código atual, aguarda healthchecks e devolve as URLs.
#
# Uso:
#   bash .claude/skills/atualizar-app/scripts/apply.sh [PID_A_MATAR ...]
#
# Args opcionais:
#   Lista de PIDs (não-Docker) a matar antes do compose up. Use quando o preview
#   detectou processo em :3000 ou :8000 e o usuário já confirmou derrubar.
#
# Saída:
#   - Marcos (etapas numeradas) em stdout
#   - exit 0: stack no ar, URLs respondendo
#   - exit 1: falha. Últimas 30 linhas de log do serviço afetado foram impressas.

set -euo pipefail

# PATH precisa incluir o bin do Docker Desktop — senão o credential helper
# `docker-credential-desktop` não é encontrado e `docker compose build`
# falha ao puxar metadata de imagens do Docker Hub.
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
COMPOSE_DIR="$REPO_ROOT/hospital-reunioes"
DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
[ -x "$DOCKER" ] || DOCKER="$(command -v docker)"

START_TS=$(date +%s)

log() { printf '[%3ss] %s\n' "$(( $(date +%s) - START_TS ))" "$1"; }
fail() {
  local svc="$1" msg="$2"
  printf '\n❌ %s\n' "$msg" >&2
  if [ -n "$svc" ]; then
    printf '\n── últimas 30 linhas de docker compose logs %s ──\n' "$svc" >&2
    (cd "$COMPOSE_DIR" && "$DOCKER" compose logs --tail=30 "$svc" 2>&1 | tail -30 >&2) || true
  fi
  exit 1
}

# ── 1. Mata processos não-Docker indicados ─────────────────────
if [ "$#" -gt 0 ]; then
  log "matando processos não-Docker: $*"
  for pid in "$@"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      # espera até 3s pelo término
      for _ in 1 2 3; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      # se ainda vivo, SIGKILL
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    fi
  done
fi

cd "$COMPOSE_DIR"

# ── 2. docker compose down ─────────────────────────────────────
log "docker compose down (removendo hr-frontend, hr-backend)"
"$DOCKER" compose down 2>&1 | sed 's/^/    /' || fail "" "falha no docker compose down"

# ── 3. docker compose up -d --build ────────────────────────────
log "docker compose up -d --build (cache de layers decide o que rebuilda)"
BUILD_START=$(date +%s)
if ! "$DOCKER" compose up -d --build 2>&1 | sed 's/^/    /'; then
  # tentar descobrir qual serviço falhou no build
  fail "frontend" "docker compose up --build falhou. Veja logs acima e do serviço abaixo."
fi
BUILD_TIME=$(( $(date +%s) - BUILD_START ))
log "build+up concluído em ${BUILD_TIME}s"

# ── 4. Aguarda healthcheck do backend ──────────────────────────
log "aguardando backend responder em http://localhost:8000/api/health (até 60s)"
BACKEND_OK=0
for i in $(seq 1 60); do
  if curl -sf -o /dev/null -m 2 http://localhost:8000/api/health 2>/dev/null; then
    BACKEND_OK=1
    log "backend respondeu 200 após ${i}s"
    break
  fi
  # checa se o container morreu no meio
  state="$("$DOCKER" inspect -f '{{.State.Status}}' hr-backend 2>/dev/null || echo absent)"
  if [ "$state" != "running" ]; then
    fail "backend" "container hr-backend não está rodando (estado: $state)"
  fi
  sleep 1
done
[ "$BACKEND_OK" = "1" ] || fail "backend" "backend não respondeu em 60s"

# ── 5. Aguarda frontend ─────────────────────────────────────────
log "aguardando frontend responder em http://localhost:3000 (até 60s)"
FRONTEND_OK=0
for i in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 2 http://localhost:3000 2>/dev/null || echo 000)"
  if [ "$code" = "200" ] || [ "$code" = "307" ] || [ "$code" = "308" ]; then
    FRONTEND_OK=1
    log "frontend respondeu $code após ${i}s"
    break
  fi
  state="$("$DOCKER" inspect -f '{{.State.Status}}' hr-frontend 2>/dev/null || echo absent)"
  if [ "$state" != "running" ]; then
    fail "frontend" "container hr-frontend não está rodando (estado: $state)"
  fi
  sleep 1
done
[ "$FRONTEND_OK" = "1" ] || fail "frontend" "frontend não respondeu em 60s"

# ── 6. Sucesso ──────────────────────────────────────────────────
TOTAL=$(( $(date +%s) - START_TS ))
cat <<EOF

✅ Stack no ar em ${TOTAL}s (build+up: ${BUILD_TIME}s)
   Frontend   http://localhost:3000
   Backend    http://localhost:8000/api
EOF
exit 0
