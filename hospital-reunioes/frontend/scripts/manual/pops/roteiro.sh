#!/usr/bin/env bash
# Roteiro dos prints da página de POPs do manual (issue #1722, ADR 0094, decisão 5).
#
# Semeia os dados de exemplo no Supabase local e refaz todos os PNGs de
# public/manual/pops/ com o playwright-cli, contra o app local. Quando a tela
# muda, é este arquivo que roda de novo.
#
# Precisa de:
#   1. Supabase local no ar (supabase start em hospital-reunioes/).
#   2. O app local respondendo em $BASE (padrão http://localhost:3000), com o
#      código que o print vai mostrar.
#   3. hospital-reunioes/.env com SUPABASE_URL local e SUPABASE_SERVICE_ROLE_KEY.
#
# Uso: bash hospital-reunioes/frontend/scripts/manual/pops/roteiro.sh
#      [--so-semear]
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/pops"
ENV_LOCAL="${ENV_LOCAL:-$FRONTEND/../.env}"
BASE="${BASE:-http://localhost:3000}"
BANCO="${BANCO:-supabase_db_hospital-reunioes}"
SESSAO="manual-pops"

# A pessoa que entra nos prints e as outras duas do fluxo. Senha só do banco local.
SENHA="ManualPops2026!"
EMAILS=(carla.mendes@exemplo.local fabio.rangel@exemplo.local lucia.moraes@exemplo.local)

export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"

ler_env() { { grep -E "^$1=" "$ENV_LOCAL" || true; } | head -1 | cut -d= -f2- | tr -d '"'; }

SUPABASE_URL="$(ler_env SUPABASE_URL)"
CHAVE="$(ler_env SUPABASE_SERVICE_ROLE_KEY)"

local_ou_recusa() {
  case "$1" in
    http://127.0.0.1:*|http://localhost:*) ;;
    *) echo "recusado: '$1' não é local. O roteiro só roda contra o app e o banco da máquina." >&2; exit 1 ;;
  esac
}
local_ou_recusa "$SUPABASE_URL"
local_ou_recusa "$BASE"

# 1. Os logins de exemplo (criar de novo devolve "already registered", e tudo bem).
for email in "${EMAILS[@]}"; do
  resposta="$(curl -s -X POST "$SUPABASE_URL/auth/v1/admin/users" \
    -H "apikey: $CHAVE" -H "Authorization: Bearer $CHAVE" -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$SENHA\",\"email_confirm\":true}")"
  case "$resposta" in
    *'"id"'*|*already*) ;;
    *) echo "login $email: $resposta" >&2; exit 1 ;;
  esac
done

# 2. Pessoas, setores e um POP em cada etapa do caminho.
docker exec -i "$BANCO" psql -q -U postgres -v ON_ERROR_STOP=1 < "$AQUI/semear.sql"
echo "dados de exemplo da página de POPs prontos."
[ "${1:-}" = "--so-semear" ] && exit 0

# 3. Os prints, todos de uma vez, pela mesma sessão do navegador.
mkdir -p "$SAIDA"
playwright-cli -s="$SESSAO" open "$BASE/login" >/dev/null
trap 'playwright-cli -s="$SESSAO" close >/dev/null 2>&1 || true' EXIT
playwright-cli -s="$SESSAO" resize 1440 900 >/dev/null
CODIGO="$(sed -e "s#__BASE__#$BASE#g" -e "s#__SAIDA__#$SAIDA#g" \
  -e "s#__EMAIL__#${EMAILS[0]}#g" -e "s#__SENHA__#$SENHA#g" "$AQUI/prints.js")"
playwright-cli -s="$SESSAO" run-code "$CODIGO"
ls -1 "$SAIDA"/*.png
