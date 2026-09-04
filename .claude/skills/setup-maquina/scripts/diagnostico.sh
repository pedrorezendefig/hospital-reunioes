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
    --nivel) NIVEL="${2:-}"; shift 2 ;;
    --nivel=*) NIVEL="${1#--nivel=}"; shift ;;
    --env) shift ;;   # modo em prosa do SKILL.md: o agente gera os .env; o script só diagnostica
    *) echo "argumento desconhecido: $1 (uso: --nivel 1..4)" >&2; exit 2 ;;
  esac
done
case "$NIVEL" in 1|2|3|4) ;; *) echo "uso: --nivel 1..4 (recebi '$NIVEL')" >&2; exit 2 ;; esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
APP="$REPO_ROOT/hospital-reunioes"
FALHAS=0
cd "$REPO_ROOT" || exit 1   # gh resolve o repositório pelo cwd
# O PATH do shell de quem roda é o que o /deploy e o /ship enxergam. Os prefixos extras
# servem só para achar o binário instalado fora do PATH e avisar, não para dar OK.
PATH_SHELL="$PATH"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

ok()    { printf '  OK     %-34s %s\n' "$1" "${2:-}"; }
falta() { printf '  FALTA  %-34s %s\n' "$1" "${2:-}"; FALHAS=$((FALHAS+1)); }
aviso() { printf '  AVISO  %-34s %s\n' "$1" "${2:-}"; }
opc()   { printf '  FALTA  %-34s %s\n' "$1" "${2:-}"; }   # opcional: não conta como falha
titulo(){ printf '\n%s\n' "$1"; }

tem_bin() { command -v "$1" >/dev/null 2>&1; }
no_path_do_shell() { PATH="$PATH_SHELL" command -v "$1" >/dev/null 2>&1; }
bin_ok() { # nome conserto -> OK se está no PATH do shell; AVISO se só existe fora dele; FALTA se não existe
  if no_path_do_shell "$1"; then ok "$1"
  elif tem_bin "$1"; then aviso "$1" "instalado em $(dirname "$(command -v "$1")"), mas fora do PATH do seu shell: adicione ao ~/.zshrc"; FALHAS=$((FALHAS+1))
  else falta "$1" "$2"; fi
}
chave_preenchida() { # arquivo chave -> 0 se existe e não está vazia
  [ -f "$1" ] && grep -Eq "^$2=.+" "$1"
}
chaves_faltando() { # example real -> nomes que existem no example e não no real
  comm -23 <(grep -oE '^[A-Z_]+' "$1" | sort -u) <(grep -oE '^[A-Z_]+' "$2" | sort -u) | tr '\n' ' '
}

# ---------------------------------------------------------------- Nível 1
titulo "Nível 1: pipeline (issues, tdd, PR)"
tem_bin git && ok "git" || falta "git" "xcode-select --install"
bin_ok jq "brew install jq"
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
    if revs="$(gh variable get REVIEWER_LOGINS 2>/dev/null)" && [ -n "$login" ]; then
      if printf '%s' "$revs" | tr ',' '\n' | grep -qx "$login"; then
        ok "login em REVIEWER_LOGINS" "$login"
      else
        aviso "login em REVIEWER_LOGINS" "peça ao Pedro: gh variable set REVIEWER_LOGINS --body \"${revs:+$revs,}$login\""
      fi
    else
      aviso "login em REVIEWER_LOGINS" "não deu para ler a variável (permissão?); peça ao Pedro para conferir"
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
SETT="$HOME/.claude/settings.json"
for p in code-review security-guidance context7 skill-creator; do
  id="$p@claude-plugins-official"
  if [ -f "$PLUG" ] && jq -e --arg p "$id" '.plugins[$p]' "$PLUG" >/dev/null 2>&1; then
    if [ -f "$SETT" ] && jq -e --arg p "$id" '.enabledPlugins[$p] == true' "$SETT" >/dev/null 2>&1; then
      ok "plugin $p"
    else
      falta "plugin $p" "instalado mas desabilitado: claude plugin enable $id"
    fi
  else
    falta "plugin $p" "claude plugin install $id"
  fi
done

# ---------------------------------------------------------------- Nível 2
if [ "$NIVEL" -ge 2 ]; then
titulo "Nível 2: deploy (ship com merge, /deploy, /onda)"
bin_ok coolify "ver docs/onboarding/claude-setup.md seção 4.1"
if tem_bin coolify; then
  ctx="$(coolify context list 2>/dev/null | grep ' hsm ' || true)"
  if [ -n "$ctx" ]; then
    ok "contexto hsm"
    printf '%s' "$ctx" | grep -q ' true ' && ok "hsm é o contexto padrão" || falta "hsm é o contexto padrão" "coolify context use hsm (o /deploy usa o contexto ativo)"
    if coolify context verify --context hsm >/dev/null 2>&1; then ok "token do Coolify válido"; else falta "token do Coolify válido" "coolify context set-token hsm (gere em Coolify > Keys & Tokens)"; fi
  else
    falta "contexto hsm" "ver docs/onboarding/claude-setup.md seção 4.1"
  fi
fi

TOK="$REPO_ROOT/tokens/.env"
if [ -f "$TOK" ]; then
  ok "tokens/.env existe"
  for k in COOLIFY_ACCESS_TOKEN COOLIFY_BASE_URL; do
    chave_preenchida "$TOK" "$k" && ok "tokens/.env: $k" "preenchida" || falta "tokens/.env: $k" "ver references/chaves.md"
  done
  chave_preenchida "$TOK" ANA_API_KEY && ok "tokens/.env: ANA_API_KEY" "preenchida" || aviso "tokens/.env: ANA_API_KEY" "só para smoke test contra prod; ver references/chaves.md"
else
  falta "tokens/.env existe" "cp tokens/.env.example tokens/.env e preencher (references/chaves.md)"
fi

bin_ok python3 "brew install python@3.12"
bin_ok uv "curl -LsSf https://astral.sh/uv/install.sh | sh"
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
    # Mesmo comando e mesmo ambiente do snapshot do /deploy ship (ele NÃO injeta DYLD_*).
    if (cd "$APP/backend" && .venv/bin/python -c "import app.main" >/dev/null 2>&1); then
      ok "app importa (snapshot vai funcionar)"
    elif (cd "$APP/backend" && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "import app.main" >/dev/null 2>&1); then
      falta "app importa" "só importa com DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib; exporte isso no ~/.zshrc, senão o snapshot cai em modo parcial"
    else
      falta "app importa" "rode: cd hospital-reunioes/backend && .venv/bin/python -c 'import app.main' e leia o erro"
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
