#!/usr/bin/env bash
# diagnostico.sh: confere o que a máquina tem para trabalhar no Hospital Reuniões.
#
# Uso:
#   bash .claude/skills/setup-maquina/scripts/diagnostico.sh [--nivel N]
#   N = 1 pipeline | 2 deploy (padrão) | 3 app local | 4 divulgar
#
# Saída: uma linha por checagem: OK, FALTA (conta, exit 1), AVISO (não conta) ou OPC
# (opcional ausente, não conta), com o conserto ao lado. Exit 2 = uso errado ou repo
# inacessível. NUNCA imprime valor de chave.

set -u
NIVEL=2
while [ $# -gt 0 ]; do
  case "$1" in
    --nivel) [ $# -ge 2 ] || { echo "uso: --nivel 1..4" >&2; exit 2; }; NIVEL="$2"; shift 2 ;;
    --nivel=*) NIVEL="${1#--nivel=}"; shift ;;
    --env|--mapa) shift ;;   # modos da skill (SKILL.md); o script só diagnostica
    *) echo "argumento desconhecido: $1 (uso: --nivel 1..4)" >&2; exit 2 ;;
  esac
done
case "$NIVEL" in 1|2|3|4) ;; *) echo "uso: --nivel 1..4 (recebi '$NIVEL')" >&2; exit 2 ;; esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
APP="$REPO_ROOT/hospital-reunioes"
FALHAS=0
cd "$REPO_ROOT" || exit 2   # gh resolve o repositório pelo cwd
# O PATH do shell de quem roda é o que o /deploy e o /ship enxergam. Os prefixos extras
# servem só para achar o binário instalado fora do PATH e avisar, não para dar OK.
PATH_SHELL="$PATH"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

ok()    { printf '  OK     %-34s %s\n' "$1" "${2:-}"; }
falta() { printf '  FALTA  %-34s %s\n' "$1" "${2:-}"; FALHAS=$((FALHAS+1)); }
aviso() { printf '  AVISO  %-34s %s\n' "$1" "${2:-}"; }
opc()   { printf '  OPC    %-34s %s\n' "$1" "${2:-}"; }   # opcional ausente: não conta como falha
titulo(){ printf '\n%s\n' "$1"; }

tem_bin() { command -v "$1" >/dev/null 2>&1; }
no_path_do_shell() { PATH="$PATH_SHELL" command -v "$1" >/dev/null 2>&1; }
bin_ok() { # nome conserto -> OK se está no PATH do shell; AVISO se só existe fora dele; FALTA se não existe
  if no_path_do_shell "$1"; then ok "$1"
  elif tem_bin "$1"; then falta "$1" "instalado em $(dirname "$(command -v "$1")"), mas fora do PATH do seu shell: adicione ao ~/.zshrc"
  else falta "$1" "$2"; fi
}
chave_preenchida() { # arquivo chave -> 0 se existe, não está vazia e não é o placeholder do exemplo
  [ -f "$1" ] && grep -Eq "^$2=[^[:space:]]" "$1" && ! grep -Eq "^$2=(<PREENCHER>|\"\"|'')[[:space:]]*$" "$1"
}
chaves_faltando() { # example real -> nomes que existem no example e não no real
  comm -23 <(grep -oE '^[A-Z_]+' "$1" | sort -u) <(grep -oE '^[A-Z_]+' "$2" | sort -u) | tr '\n' ' '
}

# ---------------------------------------------------------------- Nível 1
titulo "Nível 1: pipeline (issues, tdd, PR)"
bin_ok git "xcode-select --install"
bin_ok jq "brew install jq"
bin_ok claude "curl -fsSL https://claude.ai/install.sh | bash"

checa_gh() {
  no_path_do_shell gh || { bin_ok gh "brew install gh && gh auth login"; return; }
  ok "gh"
  gh auth status >/dev/null 2>&1 || { falta "gh autenticado" "gh auth login"; return; }
  ok "gh autenticado"
  perm="$(gh repo view --json viewerPermission --jq .viewerPermission 2>/dev/null || echo "?")"
  case "$perm" in
    WRITE|ADMIN|MAINTAIN) ok "permissão no repo" "$perm" ;;
    *) falta "permissão no repo" "tem $perm; peça WRITE ao Pedro" ;;
  esac
}
checa_gh

[ -n "$(git config user.name)" ] && [ -n "$(git config user.email)" ] \
  && ok "git config user.name e user.email" || falta "git config user.name e user.email" "git config --global user.name \"Nome\"; git config --global user.email \"email\""

PLUG="$HOME/.claude/plugins/installed_plugins.json"
LISTA="$REPO_ROOT/.claude/skills/setup-maquina/references/plugins.txt"   # fonte única (o onboarding aponta para cá)
plugin_habilitado() { # id -> 0 se enabledPlugins[id] == true em algum settings (usuário ou projeto)
  for f in "$HOME/.claude/settings.json" "$REPO_ROOT/.claude/settings.json" "$REPO_ROOT/.claude/settings.local.json"; do
    [ -f "$f" ] && jq -e --arg p "$1" '.enabledPlugins[$p] == true' "$f" >/dev/null 2>&1 && return 0
  done
  return 1
}
while read -r id; do
  [ -n "$id" ] || continue
  nome="${id%%@*}"
  if [ -f "$PLUG" ] && jq -e --arg p "$id" '(.plugins[$p] // []) | length > 0' "$PLUG" >/dev/null 2>&1; then
    plugin_habilitado "$id" && ok "plugin $nome" || falta "plugin $nome" "instalado mas desabilitado: claude plugin enable $id"
  else
    falta "plugin $nome" "claude plugin install $id"
  fi
done < "$LISTA"

# ---------------------------------------------------------------- Nível 2
if [ "$NIVEL" -ge 2 ]; then
titulo "Nível 2: deploy (ship com merge, /deploy, /onda)"
bin_ok coolify "ver docs/onboarding/claude-setup.md seção 4.1"
if tem_bin coolify; then
  ctx="$(coolify context list 2>/dev/null | grep ' hsm ' || true)"
  if [ -n "$ctx" ]; then
    ok "contexto hsm"
    printf '%s' "$ctx" | grep -q ' true ' && ok "hsm é o contexto padrão" || falta "hsm é o contexto padrão" "coolify context use hsm (o /deploy usa o contexto ativo)"
    if coolify context verify --context hsm >/dev/null 2>&1; then ok "token do Coolify válido"; else falta "token do Coolify válido" "set -a; source tokens/.env; set +a && coolify context set-token hsm \"\$COOLIFY_ACCESS_TOKEN\" (o token vem de tokens/.env; nunca imprima)"; fi
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

if no_path_do_shell python3; then
  py="$(PATH="$PATH_SHELL" command -v python3)"
  pyv="$("$py" -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo 0)"
  if [ "${pyv%%.*}" -lt 3 ] || [ "${pyv#*.}" -lt 9 ]; then
    falta "python3" "tem $pyv; o snapshot precisa de 3.9+: brew install python@3.12"
  else
    ok "python3" "$pyv em $py"
  fi
else
  bin_ok python3 "brew install python@3.12"
fi
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
    # Mesmo comando e mesmo ambiente do snapshot do /deploy ship (no macOS ele injeta este DYLD no filho).
    if erro="$(cd "$APP/backend" && DYLD_FALLBACK_LIBRARY_PATH="${DYLD_FALLBACK_LIBRARY_PATH:-/opt/homebrew/lib}" .venv/bin/python -c "import app.main" 2>&1 >/dev/null)"; then
      ok "app importa (snapshot vai funcionar)"
    elif printf '%s' "$erro" | grep -qiE 'libgobject|libpango|cairo|gdk'; then
      falta "app importa" "o WeasyPrint não acha o Pango: brew install pango cairo gdk-pixbuf libffi"
    else
      falta "app importa" "$(printf '%s' "$erro" | tail -1 | cut -c1-120)"
    fi
  fi
else
  falta "hospital-reunioes/.env existe" "cp hospital-reunioes/.env.example hospital-reunioes/.env (mínimo em references/chaves.md)"
fi

fi

# ---------------------------------------------------------------- Nível 3
if [ "$NIVEL" -ge 3 ]; then
titulo "Nível 3: app local (opcional, hoje ninguém usa)"
if tem_bin docker && docker ps >/dev/null 2>&1; then ok "docker no ar"; else opc "docker no ar" "instale o Docker Desktop e abra"; fi
no_path_do_shell supabase && ok "supabase" || opc "supabase" "brew install supabase/tap/supabase (se já instalou, adicione ao PATH do ~/.zshrc)"
no_path_do_shell node && ok "node" "$(node -v)" || opc "node 20+" "brew install node@22 (se já instalou, adicione ao PATH do ~/.zshrc)"
no_path_do_shell corepack && ok "corepack" || opc "corepack" "npm i -g corepack (se já instalou, adicione ao PATH do ~/.zshrc)"
[ -f "$APP/frontend/.env.local" ] && ok "frontend/.env.local" || opc "frontend/.env.local" "cp hospital-reunioes/frontend/.env.example hospital-reunioes/frontend/.env.local"
fi

# ---------------------------------------------------------------- Nível 4
if [ "$NIVEL" -ge 4 ]; then
titulo "Nível 4: divulgar (opcional)"
no_path_do_shell ffmpeg && ok "ffmpeg" || opc "ffmpeg" "brew install ffmpeg (se já instalou, adicione ao PATH do ~/.zshrc)"
[ -d "/Applications/Google Chrome.app" ] && ok "Google Chrome" || opc "Google Chrome" "brew install --cask google-chrome"
[ -d "$HOME/.claude/skills/hyperframes" ] && ok "skills globais hyperframes" || opc "skills globais hyperframes" "npx skills add heygen-com/hyperframes --all (skills globais, fora do repo; ver /divulgar)"
fi

# ---------------------------------------------------------------- Mapa do repo
titulo "Mapa do repositório (references/mapa-do-repo.md)"
MAPA="$REPO_ROOT/.claude/skills/setup-maquina/references/mapa-do-repo.md"
desconhecidas=""
# Pastas de nível 1 e 2 que o git conhece (honra o .gitignore: sem node_modules, caches, local/, worktrees)
# contra a lista de cobertura do mapa, por caminho exato.
cobertas="$(sed -n '/cobertura:start/,/cobertura:end/p' "$MAPA" 2>/dev/null | grep -E '^[a-zA-Z.]')"
for d in $(git ls-files -co --exclude-standard | awk -F/ 'NF>1{print $1} NF>2{print $1"/"$2}' | sort -u | grep -vE '^(\.claude/skills|docs/adr|docs/comunicacao|docs/manual)/'); do
  printf '%s\n' "$cobertas" | grep -qxF "$d" || desconhecidas="$desconhecidas $d"
done
[ -z "$desconhecidas" ] && ok "toda pasta de nível 1 e 2 está no mapa" || aviso "pastas fora do mapa" "atualize references/mapa-do-repo.md:$desconhecidas"

printf '\n'
if [ "$FALHAS" -eq 0 ]; then
  echo "Tudo obrigatório está OK."
  exit 0
else
  echo "$FALHAS item(ns) obrigatório(s) faltando. Conserte um por vez, com confirmação."
  exit 1
fi
