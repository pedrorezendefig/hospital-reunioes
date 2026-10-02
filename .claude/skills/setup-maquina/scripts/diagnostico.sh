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

# Windows (Git Bash): o venv põe o python em Scripts/, o Pango vem do MSYS2 e o conserto é winget.
WIN=0; case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac
VENV_PY="$APP/backend/.venv/bin/python"
[ "$WIN" -eq 1 ] && VENV_PY="$APP/backend/.venv/Scripts/python.exe"
MSYS_BIN="${WEASYPRINT_DLL_DIRECTORIES:-C:/msys64/mingw64/bin}"
PANGO_WIN="winget install MSYS2.MSYS2; C:/msys64/usr/bin/bash -lc 'pacman -S --noconfirm mingw-w64-x86_64-pango'; setx WEASYPRINT_DLL_DIRECTORIES C:\\msys64\\mingw64\\bin"
so() { [ "$WIN" -eq 1 ] && printf '%s' "$2" || printf '%s' "$1"; }   # conserto macOS | conserto Windows

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
versao_min() { # atual minima -> 0 se atual >= minima, comparando por número
  # `sort -V` e não ordem alfabética: 22.9 vem depois de 22.12 no alfabeto e
  # aprovaria um Node que não builda o site do Manual.
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}
# ---------------------------------------------------------------- Nível 1
titulo "Nível 1: pipeline (issues, tdd, PR)"
bin_ok git "xcode-select --install"
# Clone atrasado: compara a main local com a origin/main. Só avisa; quem puxa é a skill, com confirmação.
if ! git show-ref --verify --quiet refs/heads/main; then
  aviso "clone atualizado" "não existe branch main local; crie com git checkout -b main origin/main"
elif git fetch -q origin main 2>/dev/null; then
  atras="$(git rev-list --count main..origin/main)"
  [ "$atras" -eq 0 ] && ok "clone atualizado (main = origin/main)" \
    || falta "clone atualizado" "main está $atras commit(s) atrás: git checkout main && git pull --ff-only origin main"
else
  aviso "clone atualizado" "sem acesso ao origin agora; rode git pull --ff-only origin main quando tiver rede"
fi
bin_ok jq "brew install jq"
bin_ok claude "curl -fsSL https://claude.ai/install.sh | bash"

GH_OK=0
checa_gh() {
  no_path_do_shell gh || { bin_ok gh "brew install gh && gh auth login"; return; }
  ok "gh"
  gh auth status >/dev/null 2>&1 || { falta "gh autenticado" "gh auth login"; return; }
  ok "gh autenticado"
  GH_OK=1
  perm="$(gh repo view --json viewerPermission --jq .viewerPermission 2>/dev/null || echo "?")"
  case "$perm" in
    WRITE|ADMIN|MAINTAIN) ok "permissão no repo" "$perm" ;;
    *) falta "permissão no repo" "tem $perm; peça WRITE ao Pedro" ;;
  esac
}
checa_gh

# Cada sócio mergeia o próprio PR (ADR 0061): o user.email do git tem que ser um e-mail
# verificado da conta gh logada, senão o commit sai em nome de outra pessoa (setembro/2026).
# Só lê o perfil pela API; o token do gh nunca entra.
checa_email_git() { # email
  local alvo perfil login noreply conhecidos lista leu=0
  alvo="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  if ! perfil="$(gh api user 2>/dev/null)" || ! login="$(printf '%s' "$perfil" | jq -er .login 2>/dev/null)"; then
    aviso "git user.email é da conta gh" "não consegui ler a conta no gh agora; rode de novo com rede"
    return
  fi
  noreply="$(printf '%s' "$perfil" | jq -r '"\(.id)+\(.login)@users.noreply.github.com"')"
  conhecidos="$(printf '%s' "$perfil" | jq -r '.email // empty, "\(.login)@users.noreply.github.com"')
$noreply"
  if lista="$(gh api user/emails 2>/dev/null)"; then
    leu=1
    conhecidos="$conhecidos
$(printf '%s' "$lista" | jq -r '.[] | select(.verified == true) | .email' 2>/dev/null)"
  fi
  if printf '%s\n' "$conhecidos" | tr '[:upper:]' '[:lower:]' | grep -qxF "$alvo"; then
    ok "git user.email é da conta gh" "$login"
  elif [ "$leu" -eq 0 ]; then
    falta "git user.email é da conta gh" "não li os e-mails de $login: gh auth refresh -h github.com -s user:email e rode de novo"
  else
    falta "git user.email é da conta gh" "$1 não é e-mail verificado de $login: git config --global user.email \"<e-mail verificado da conta>\" (ou \"$noreply\")"
  fi
}

EMAIL_GIT="$(git config user.email)"
[ -n "$(git config user.name)" ] && [ -n "$EMAIL_GIT" ] \
  && ok "git config user.name e user.email" || falta "git config user.name e user.email" "git config --global user.name \"Nome\"; git config --global user.email \"email\""
[ -n "$EMAIL_GIT" ] && [ "$GH_OK" -eq 1 ] && checa_email_git "$EMAIL_GIT"

PLUG="$HOME/.claude/plugins/installed_plugins.json"
LISTA="$REPO_ROOT/.claude/skills/setup-maquina/references/plugins.txt"   # fonte única (o onboarding aponta para cá)
plugin_habilitado() { # id -> 0 se enabledPlugins[id] == true em algum settings (usuário ou projeto)
  for f in "$HOME/.claude/settings.json" "$REPO_ROOT/.claude/settings.json" "$REPO_ROOT/.claude/settings.local.json"; do
    [ -f "$f" ] && jq -e --arg p "$1" '.enabledPlugins[$p] == true' "$f" >/dev/null 2>&1 && return 0
  done
  return 1
}
while read -r id; do
  id="${id%$'\r'}"   # core.autocrlf no Windows grava a lista em CRLF
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
titulo "Nível 2: deploy (ship com merge, /deploy, /onda-enxuta)"
bin_ok coolify "ver docs/onboarding/claude-setup.md seção 4.1"
# A CLI responde e tem o contexto do hospital (hsm). Lê a lista e o verify sem nunca
# imprimir o que eles devolvem: a saída do CLI pode trazer o token.
checa_coolify() {
  local lista ctx resposta
  if ! lista="$(coolify context list 2>/dev/null)"; then
    falta "CLI do Coolify roda" "coolify context list falhou; reinstale pela docs/onboarding/claude-setup.md seção 4.1"
    return
  fi
  ctx="$(printf '%s\n' "$lista" | grep ' hsm ' || true)"
  if [ -z "$ctx" ]; then
    falta "contexto hsm" "a conta no Coolify quem cria é o Pedro; o token você gera em Keys & Tokens (claude-setup.md seção 4.1)"
    return
  fi
  ok "contexto hsm"
  printf '%s' "$ctx" | grep -q ' true ' && ok "hsm é o contexto padrão" || falta "hsm é o contexto padrão" "coolify context use hsm (o /deploy usa o contexto ativo)"
  if resposta="$(coolify context verify --context hsm 2>&1)"; then
    ok "servidor do Coolify responde"
  elif printf '%s' "$resposta" | grep -qE '401|Unauthenticated|Unauthorized'; then
    falta "token do Coolify válido" "gere outro em Keys & Tokens e grave em tokens/.env; depois set -a; source tokens/.env; set +a && coolify context set-token hsm \"\$COOLIFY_ACCESS_TOKEN\" (nunca imprima)"
  else
    falta "servidor do Coolify responde" "sem resposta do servidor: confira a rede; bloqueio do fail2ban passa sozinho em alguns minutos; persistindo, avise o Pedro"
  fi
}
tem_bin coolify && checa_coolify

# Quem mergeia aplica a migration no Studio de produção (ADR 0061). Só bate na porta, sem
# credencial: 401 é o login do Studio pedindo usuário, ou seja, alcançável.
checa_studio() { # url
  local codigo
  codigo="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$1" 2>/dev/null)"
  case "$codigo" in
    2??|3??|401) ok "Studio de produção alcançável" "o login do Studio vem do Pedro" ;;
    *) falta "Studio de produção alcançável" "$1 não respondeu (HTTP ${codigo:-000}); peça o acesso ao Pedro" ;;
  esac
}
STUDIO_URL="$(jq -r '.services[] | select(.type == "supabase") | .deploy.fqdn // empty' "$REPO_ROOT/docs/spec/deploy/project.json" 2>/dev/null)"
if [ -n "$STUDIO_URL" ]; then
  checa_studio "$STUDIO_URL"
else
  falta "Studio de produção alcançável" "docs/spec/deploy/project.json sem o serviço supabase com deploy.fqdn"
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

PY_INST="$(so "brew install python@3.12" "winget install Python.Python.3.12")"
if no_path_do_shell python3; then
  py="$(PATH="$PATH_SHELL" command -v python3)"
  pyv="$("$py" -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo 0)"
  if [ "$pyv" = 0 ] && case "$py" in *WindowsApps*) true ;; *) false ;; esac; then
    # O python.org não instala python3.exe; sobra o atalho da Microsoft Store, que não roda nada.
    falta "python3" "é o atalho da Microsoft Store; copie python.exe como python3.exe na pasta do Python (ou $PY_INST)"
  elif [ "${pyv%%.*}" -lt 3 ] || [ "${pyv#*.}" -lt 9 ]; then
    falta "python3" "tem $pyv; o snapshot precisa de 3.9+: $PY_INST"
  else
    ok "python3" "$pyv em $py"
  fi
else
  bin_ok python3 "$PY_INST"
fi
bin_ok uv "$(so "curl -LsSf https://astral.sh/uv/install.sh | sh" "winget install astral-sh.uv")"
[ -x "$VENV_PY" ] && ok "backend/.venv" || falta "backend/.venv" "(cd hospital-reunioes/backend && uv sync)"
if [ "$WIN" -eq 1 ]; then
  [ -f "$MSYS_BIN/libpango-1.0-0.dll" ] && ok "pango (WeasyPrint)" "$MSYS_BIN" || falta "pango (WeasyPrint)" "$PANGO_WIN"
else
  [ -f /opt/homebrew/lib/libpango-1.0.dylib ] || [ -f /usr/local/lib/libpango-1.0.dylib ] \
    && ok "pango (WeasyPrint)" || falta "pango (WeasyPrint)" "brew install pango cairo gdk-pixbuf libffi"
fi

# Só três valores, todos fictícios (os mesmos do CI): bastam para o snapshot importar o app.
ENVF="$APP/.env"
ENV_MIN="ENVIRONMENT=development SUPABASE_URL=http://127.0.0.1:54351 SUPABASE_SERVICE_ROLE_KEY=dummy-local"
if [ -f "$ENVF" ]; then
  ok "hospital-reunioes/.env existe"
  for par in $ENV_MIN; do
    k="${par%%=*}"
    chave_preenchida "$ENVF" "$k" && ok ".env: $k" "preenchida" \
      || falta ".env: $k" "valor fictício basta: echo '$par' >> hospital-reunioes/.env"
  done
  if [ -x "$VENV_PY" ]; then
    # Mesmo comando e mesmo ambiente do snapshot do /deploy ship (ele injeta no filho o DYLD
    # no macOS e o WEASYPRINT_DLL_DIRECTORIES no Windows).
    if erro="$(cd "$APP/backend" && DYLD_FALLBACK_LIBRARY_PATH="${DYLD_FALLBACK_LIBRARY_PATH:-/opt/homebrew/lib}" WEASYPRINT_DLL_DIRECTORIES="$MSYS_BIN" "$VENV_PY" -c "import app.main" 2>&1 >/dev/null)"; then
      ok "app importa (snapshot vai funcionar)"
    elif printf '%s' "$erro" | grep -qiE 'libgobject|libpango|cairo|gdk'; then
      falta "app importa" "o WeasyPrint não acha o Pango: $(so "brew install pango cairo gdk-pixbuf libffi" "$PANGO_WIN")"
    else
      falta "app importa" "$(printf '%s' "$erro" | tail -1 | cut -c1-120)"
    fi
  fi
else
  falta "hospital-reunioes/.env existe" "printf '%s\\n' $ENV_MIN > hospital-reunioes/.env (três valores fictícios; nada real)"
fi

# O /deploy ship publica o Manual quando o deploy tira alguma página do draft
# (Passo 9.6): o site é Starlight, buildado por `corepack pnpm@9` com Node >=
# 22.12, e a publicação reencoda cada vídeo com ffmpeg. Por isso os três são
# nível 2, o mesmo do deploy, e não opcionais.
NODE_MIN=22.12
if no_path_do_shell node; then
  nodev="$(PATH="$PATH_SHELL" node -v 2>/dev/null)"; nodev="${nodev#v}"
  if versao_min "$nodev" "$NODE_MIN"; then
    ok "node >= $NODE_MIN (manual)" "v$nodev"
  else
    falta "node >= $NODE_MIN (manual)" "tem v$nodev; o site do Manual não builda: brew install node@22 e ponha no PATH do ~/.zshrc"
  fi
else
  falta "node >= $NODE_MIN (manual)" "brew install node@22 (o /deploy ship publica o Manual e o site exige $NODE_MIN)"
fi
bin_ok corepack "npm i -g corepack (o site do Manual builda com corepack pnpm@9)"
bin_ok ffmpeg "brew install ffmpeg (a publicação do Manual reencoda os vídeos)"

fi

# ---------------------------------------------------------------- Nível 3
if [ "$NIVEL" -ge 3 ]; then
titulo "Nível 3: app local (opcional, hoje ninguém usa)"
if tem_bin docker && docker ps >/dev/null 2>&1; then ok "docker no ar"; else opc "docker no ar" "instale o Docker Desktop e abra"; fi
no_path_do_shell supabase && ok "supabase" || opc "supabase" "brew install supabase/tap/supabase (se já instalou, adicione ao PATH do ~/.zshrc)"
# node e corepack são conferidos no nível 2: o deploy publica o Manual.
[ -f "$APP/frontend/.env.local" ] && ok "frontend/.env.local" || opc "frontend/.env.local" "cp hospital-reunioes/frontend/.env.example hospital-reunioes/frontend/.env.local"
fi

# ---------------------------------------------------------------- Nível 4
if [ "$NIVEL" -ge 4 ]; then
titulo "Nível 4: produzir vídeo e print (opcional)"
[ -d "/Applications/Google Chrome.app" ] && ok "Google Chrome" || opc "Google Chrome" "brew install --cask google-chrome"
[ -d "$HOME/.claude/skills/hyperframes" ] && ok "skills globais hyperframes" || opc "skills globais hyperframes" "npx skills add heygen-com/hyperframes --all (skills globais, fora do repo; ver /divulgar)"
# Roteiro de prints do manual: Playwright em Python, com o Chromium baixado.
if PATH="$PATH_SHELL" python3 -c "import playwright" >/dev/null 2>&1; then
  ok "playwright (roteiro de prints)"
else
  opc "playwright (roteiro de prints)" "pip install playwright && python3 -m playwright install chromium"
fi
fi

# ---------------------------------------------------------------- Mapa do repo
titulo "Mapa do repositório (README.md)"
MAPA="$REPO_ROOT/README.md"
desconhecidas=""
# Pastas de nível 1 e 2 que o git conhece (honra o .gitignore: sem node_modules, caches, local/, worktrees)
# contra a lista de cobertura do mapa, por caminho exato.
cobertas="$(sed -n '/cobertura:start/,/cobertura:end/p' "$MAPA" 2>/dev/null | grep -E '^[a-zA-Z.]')"
for d in $(git ls-files -co --exclude-standard | awk -F/ 'NF>1{print $1} NF>2{print $1"/"$2}' | sort -u | grep -vE '^(\.claude/skills|docs/adr|docs/comunicacao|docs/manual)/'); do
  printf '%s\n' "$cobertas" | grep -qxF "$d" || desconhecidas="$desconhecidas $d"
done
[ -z "$desconhecidas" ] && ok "toda pasta de nível 1 e 2 está no mapa" || aviso "pastas fora do mapa" "atualize README.md:$desconhecidas"

printf '\n'
if [ "$FALHAS" -eq 0 ]; then
  echo "Tudo obrigatório está OK."
  exit 0
else
  echo "$FALHAS item(ns) obrigatório(s) faltando. Conserte um por vez, com confirmação."
  exit 1
fi
