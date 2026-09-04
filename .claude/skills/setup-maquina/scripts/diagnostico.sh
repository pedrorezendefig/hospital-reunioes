#!/usr/bin/env bash
# diagnostico.sh: confere o que a máquina tem para trabalhar no Hospital Reuniões.
#
# Uso:
#   bash .claude/skills/setup-maquina/scripts/diagnostico.sh [--nivel N]
#   N = 1 pipeline | 2 deploy (padrão) | 3 app local | 4 divulgar
#
# Saída: uma linha por checagem: OK, FALTA ou AVISO, com o conserto ao lado.
# Exit 1 se algo obrigatório (níveis 1 e 2) falta. NUNCA imprime valor de chave.

set -u
NIVEL=2
while [ $# -gt 0 ]; do
  case "$1" in
    --nivel) NIVEL="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
APP="$REPO_ROOT/hospital-reunioes"
FALHAS=0
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

ok()    { printf '  OK     %-34s %s\n' "$1" "${2:-}"; }
falta() { printf '  FALTA  %-34s %s\n' "$1" "${2:-}"; FALHAS=$((FALHAS+1)); }
aviso() { printf '  AVISO  %-34s %s\n' "$1" "${2:-}"; }
opc()   { printf '  FALTA  %-34s %s\n' "$1" "${2:-}"; }   # opcional: não conta como falha
titulo(){ printf '\n%s\n' "$1"; }

tem_bin() { command -v "$1" >/dev/null 2>&1; }
chave_preenchida() { # arquivo chave -> 0 se existe e não está vazia
  [ -f "$1" ] && grep -Eq "^$2=.+" "$1"
}
chaves_faltando() { # example real -> nomes que existem no example e não no real
  comm -23 <(grep -oE '^[A-Z_]+' "$1" | sort -u) <(grep -oE '^[A-Z_]+' "$2" | sort -u) | tr '\n' ' '
}

# ---------------------------------------------------------------- Nível 1
titulo "Nível 1: pipeline (issues, tdd, PR)"
tem_bin git && ok "git" || falta "git" "xcode-select --install"
tem_bin jq  && ok "jq"  || falta "jq" "brew install jq"
tem_bin claude && ok "claude (Claude Code)" || falta "claude (Claude Code)" "curl -fsSL https://claude.ai/install.sh | bash"

if tem_bin gh; then
  if gh auth status >/dev/null 2>&1; then
    ok "gh autenticado"
    perm="$(gh repo view --json viewerPermission --jq .viewerPermission 2>/dev/null || echo "?")"
    case "$perm" in
      WRITE|ADMIN|MAINTAIN) ok "permissão no repo" "$perm" ;;
      *) falta "permissão no repo" "tem $perm; peça WRITE ao Pedro" ;;
    esac
    login="$(gh api user --jq .login 2>/dev/null || echo "")"
    revs="$(gh variable get REVIEWER_LOGINS 2>/dev/null || echo "")"
    if [ -n "$login" ] && printf '%s' "$revs" | grep -q "$login"; then
      ok "login em REVIEWER_LOGINS" "$login"
    else
      aviso "login em REVIEWER_LOGINS" "gh variable set REVIEWER_LOGINS --body \"$revs,$login\""
    fi
  else
    falta "gh autenticado" "gh auth login"
  fi
else
  falta "gh" "brew install gh && gh auth login"
fi

[ -n "$(git -C "$REPO_ROOT" config user.name)" ] && [ -n "$(git -C "$REPO_ROOT" config user.email)" ] \
  && ok "git config user.name e user.email" || falta "git config user.name e user.email" "git config --global user.name \"Nome\"; git config --global user.email \"email\""

PLUG="$HOME/.claude/plugins/installed_plugins.json"
for p in code-review security-guidance context7 skill-creator; do
  if [ -f "$PLUG" ] && jq -e --arg p "$p@claude-plugins-official" '.plugins[$p]' "$PLUG" >/dev/null 2>&1; then
    ok "plugin $p"
  else
    falta "plugin $p" "claude plugin install $p@claude-plugins-official"
  fi
done

# ---------------------------------------------------------------- Nível 2
if [ "$NIVEL" -ge 2 ]; then
titulo "Nível 2: deploy (ship com merge, /deploy, /onda)"
if tem_bin coolify; then
  ok "coolify (CLI)"
  if coolify context list 2>/dev/null | grep -q ' hsm '; then
    ok "contexto hsm"
    if coolify context verify >/dev/null 2>&1; then ok "token do Coolify válido"; else falta "token do Coolify válido" "coolify context set-token hsm (gere em Coolify > Keys & Tokens)"; fi
  else
    falta "contexto hsm" "ver docs/onboarding/claude-setup.md seção 4.1"
  fi
else
  falta "coolify (CLI)" "ver docs/onboarding/claude-setup.md seção 4.1"
fi

TOK="$REPO_ROOT/tokens/.env"
if [ -f "$TOK" ]; then
  ok "tokens/.env existe"
  for k in COOLIFY_ACCESS_TOKEN COOLIFY_BASE_URL ANA_API_KEY; do
    chave_preenchida "$TOK" "$k" && ok "tokens/.env: $k" "preenchida" || falta "tokens/.env: $k" "ver references/chaves.md"
  done
else
  falta "tokens/.env existe" "cp tokens/.env.example tokens/.env e preencher (references/chaves.md)"
fi

if tem_bin python3; then
  pv="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  ok "python3" "$pv"
else
  falta "python3" "brew install python@3.12"
fi
tem_bin uv && ok "uv" || falta "uv" "curl -LsSf https://astral.sh/uv/install.sh | sh"
[ -x "$APP/backend/.venv/bin/python" ] && ok "backend/.venv" || falta "backend/.venv" "(cd hospital-reunioes/backend && uv sync)"
[ -f /opt/homebrew/lib/libpango-1.0.dylib ] || [ -f /usr/local/lib/libpango-1.0.dylib ] \
  && ok "pango (WeasyPrint)" || falta "pango (WeasyPrint)" "brew install pango cairo gdk-pixbuf libffi"

ENVF="$APP/.env"
if [ -f "$ENVF" ]; then
  ok "hospital-reunioes/.env existe"
  for k in ENVIRONMENT SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY; do
    chave_preenchida "$ENVF" "$k" && ok ".env: $k" "preenchida" || falta ".env: $k" "valor fictício basta (references/chaves.md)"
  done
  f="$(chaves_faltando "$APP/.env.example" "$ENVF")"
  [ -z "$f" ] && ok ".env: chaves do .env.example" "todas presentes" || aviso ".env: chaves ausentes" "$f"
  if [ -x "$APP/backend/.venv/bin/python" ]; then
    if (cd "$APP/backend" && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "import app.main" >/dev/null 2>&1); then
      ok "app importa (snapshot vai funcionar)"
    else
      falta "app importa" "rode: cd hospital-reunioes/backend && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c 'import app.main'"
    fi
  fi
else
  falta "hospital-reunioes/.env existe" "cp hospital-reunioes/.env.example hospital-reunioes/.env (mínimo em references/chaves.md)"
fi

fi

# ---------------------------------------------------------------- Nível 3
if [ "$NIVEL" -ge 3 ]; then
titulo "Nível 3: app local (opcional, hoje ninguém usa)"
tem_bin docker && docker ps >/dev/null 2>&1 && ok "docker no ar" || opc "docker no ar" "instale o Docker Desktop e abra"
tem_bin supabase && ok "supabase (CLI)" || opc "supabase (CLI)" "brew install supabase/tap/supabase"
tem_bin node && ok "node" "$(node -v)" || opc "node 20+" "brew install node@22"
tem_bin corepack && ok "corepack" || opc "corepack" "npm i -g corepack"
[ -f "$APP/frontend/.env.local" ] && ok "frontend/.env.local" || opc "frontend/.env.local" "cp hospital-reunioes/frontend/.env.example hospital-reunioes/frontend/.env.local"
fi

# ---------------------------------------------------------------- Nível 4
if [ "$NIVEL" -ge 4 ]; then
titulo "Nível 4: divulgar (opcional)"
tem_bin ffmpeg && ok "ffmpeg" || opc "ffmpeg" "brew install ffmpeg"
[ -d "/Applications/Google Chrome.app" ] && ok "Google Chrome" || opc "Google Chrome" "brew install --cask google-chrome"
[ -d "$HOME/.claude/skills/hyperframes" ] && ok "skills globais hyperframes" || opc "skills globais hyperframes" "npx skills add hyperframes (fora do repo, ver /divulgar)"
fi

printf '\n'
if [ "$FALHAS" -eq 0 ]; then
  echo "Tudo obrigatório está OK."
  exit 0
else
  echo "$FALHAS item(ns) obrigatório(s) faltando. Conserte um por vez, com confirmação."
  exit 1
fi
