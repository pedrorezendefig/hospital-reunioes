# Setup do Claude Code pra trabalhar no Hospital Reuniões

Guia único de setup. Roda do zero até ter o fluxo do time funcionando no terminal — com plugins, CLI do Coolify, MCP servers e permissões alinhadas. Tempo estimado: **15–30 minutos**.

Depois de seguir este guia, leia [`dev.md`](./dev.md) pra entender o fluxo dia-a-dia (`/grill-with-docs` → `/pegar-issue` → `/tdd` → `/ship` → `/deploy`).

---

## TLDR — checklist enxuto

Se você já conhece Claude Code, é só seguir esta lista. Detalhes nas seções abaixo.

> Atalho: depois do clone, rode `/setup-maquina` no Claude Code. Ele confere tudo desta lista e diz o que falta e onde pegar cada chave (`.claude/skills/setup-maquina/references/chaves.md`). O app não precisa rodar na sua máquina: sobe para produção e se testa lá.

- [ ] [1.](#1-pré-requisitos) Pré-requisitos instalados (Claude Code CLI, gh, jq, python3, uv, Pango)
- [ ] [2.](#2-clone-do-repo) Repo clonado + `gh auth login` feito
- [ ] [3.](#3-plugins-essenciais) 4 plugins habilitados (`code-review`, `security-guidance`, `context7`, `skill-creator`)
- [ ] [4.](#4-acessos-externos-coolify-e-mcp) CLI do Coolify instalado e contexto `hsm` criado com `COOLIFY_ACCESS_TOKEN` + `COOLIFY_BASE_URL`
- [ ] [5.](#5-permissions-opcional-mas-recomendado) Permissions allow-list mínima (reduz prompts)
- [ ] [6.](#6-verificação-end-to-end) `/pegar-issue` e `/deploy status` funcionando

> Todas as skills do time **já vêm versionadas no repo** em `.claude/skills/` (lista e roteamento: `/ask-pedro`). Nada a instalar por máquina. Pra atualizar as do Pocock: é manual, porque o upstream renomeou pastas e as nossas são adaptadas em pt-BR (ADR 0049).

---

## 1. Pré-requisitos

Instale antes de tudo:

| Ferramenta | Comando (macOS) | Pra quê |
|---|---|---|
| **Claude Code CLI** | `npm install -g @anthropic-ai/claude-code` ou via [claude.ai/code](https://claude.ai/code) | O agente em si |
| **GitHub CLI** (`gh`) | `brew install gh` | PRs, Issues, reviews. Usado por `/pegar-issue`, `/to-prd`, `/to-issues` e `/ship` |
| **`jq`** | `brew install jq` | Parser JSON em scripts (gates do `/deploy`) |
| **Python 3.9+** | já vem no macOS recente, ou `brew install python@3.12` | Scripts do `/snapshot` + gates do `/deploy`. O 3.12 do backend quem provê é o `uv sync` |
| **`uv`** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` e depois `cd hospital-reunioes/backend && uv sync` | Cria o `.venv` do backend. O `/deploy ship` importa o app para gerar o snapshot |
| **Pango** (WeasyPrint) | `brew install pango cairo gdk-pixbuf libffi` | O app importa o WeasyPrint no boot; sem Pango o snapshot do `/deploy` cai em modo parcial (o snapshot já aponta o Pango do Homebrew sozinho) |
| **Docker Desktop** (opcional) | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | Só para rodar o app local com `/atualizar-app`. Hoje ninguém usa: o app sobe para produção e se testa lá |
| **Node 20+** (opcional) | `brew install node@22` | Só para rodar o frontend local ou `/divulgar` |

**Validar:**
```bash
claude --version       # > 1.0
gh --version           # > 2.40
jq --version           # > 1.6
python3 --version      # > 3.9
uv --version           # qualquer
ls /opt/homebrew/lib/libpango-1.0.dylib   # existe
```

Ou, numa sessão Claude Code dentro do repo, `/setup-maquina`: confere tudo isto e o resto do guia de uma vez.

**Autenticar:**
```bash
gh auth login          # OAuth web — escolha "GitHub.com" + "HTTPS" + "Login with browser"
git config --global user.name "Seu Nome"
git config --global user.email "seu@email"
```

---

## 2. Clone do repo

```bash
gh repo clone pedrorezendefig/hospital-reunioes   # ou: git clone https://github.com/pedrorezendefig/hospital-reunioes.git
cd hospital-reunioes
```

Já tinha o clone? Traga a `main` para o dia: `git checkout main && git pull --ff-only origin main`. O `/setup-maquina` acusa quando a `main` local está atrás da `origin/main`. O mapa de cada pasta do repo é o `README.md` da raiz.

Você precisa ter sido adicionado como **collaborator** no repo (peça pro Pedro). Verifique:
```bash
gh repo view --json viewerPermission --jq .viewerPermission
# esperado: WRITE ou ADMIN
```

---

## 3. Plugins essenciais

Plugins do Claude Code são instalados via `/plugin` dentro de uma sessão. Eles vivem em `~/.claude/plugins/cache/` e são habilitados em `~/.claude/settings.json`.

**Plugins obrigatórios pro fluxo do time** (fonte única: `.claude/skills/setup-maquina/references/plugins.txt`, que o `/setup-maquina` lê):

| Plugin | Pra que serve | Quem usa |
|---|---|---|
| `code-review@claude-plugins-official` | `/code-review` — review automatizada do diff | `/ship` Gate 1 (sempre) |
| `security-guidance@claude-plugins-official` | `/security-review` — review focada em vulns | `/ship` Gate 2 (condicional: auth/RLS/migrations/env/webhook) |
| `context7@claude-plugins-official` | Docs atualizadas de libs (React, Next.js, FastAPI, Supabase) | Claude busca antes de propor mudanças em libs |
| `skill-creator@claude-plugins-official` | Criar/editar skills do time | Quando alguém quiser estender `.claude/skills/` |

**Instalar:**

Dentro de uma sessão Claude Code (`claude` no terminal), digite:

```
/plugin install code-review@claude-plugins-official
/plugin install security-guidance@claude-plugins-official
/plugin install context7@claude-plugins-official
/plugin install skill-creator@claude-plugins-official
```

(Você pode rodar todos em sequência, um por linha. Cada `/plugin install` adiciona a entrada em `~/.claude/settings.json` automaticamente.)

**Validar:**
```bash
jq -r '.enabledPlugins | keys[]' ~/.claude/settings.json
```

Você deve ver os 4 plugins listados com valor `true`. (As skills falam com o GitHub pelo `gh`, não por plugin.)

**Opcional (time pode pular):**
- `frontend-design@claude-plugins-official` — se for trabalhar muito em UI/UX

---

## 4. Acessos externos (Coolify e MCP)

Duas coisas diferentes moram aqui: o **CLI do Coolify** (um binário no seu PATH, usado pelo `/deploy`) e os **MCP servers** (como Claude acessa GitHub e Context7, configurados em `~/.claude.json`, não em `~/.claude/settings.json`).

### 4.1 CLI do Coolify (obrigatório: sem ele `/deploy` não funciona)

O `/deploy` usa o **CLI oficial** (`coollabsio/coolify-cli`) pra falar com a VPS do Hospital. É o único caminho: o Coolify não entra pelo `~/.claude.json`, e nada precisa ser registrado lá pra ele.

**Passo 1: conseguir o token**

Logue no Coolify do Hospital → Profile → API Tokens → "Create Token" → escopo `read+write` em todas as resources. Copie o token (formato `12|abc...`).

(O Pedro envia o URL real do Coolify + token pra você no setup individual.)

**Passo 2: instalar o CLI**

```bash
curl -fsSL https://raw.githubusercontent.com/coollabsio/coolify-cli/main/scripts/install.sh | bash
```

Instala em `/usr/local/bin/coolify`. Alternativas: `brew install coollabsio/coolify-cli/coolify-cli`, ou o binário pronto da release:

```bash
VER=$(curl -s https://api.github.com/repos/coollabsio/coolify-cli/releases/latest | jq -r .tag_name | tr -d v)
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
curl -sL "https://github.com/coollabsio/coolify-cli/releases/download/v${VER}/coolify-cli_${VER}_darwin_${ARCH}.tar.gz" | tar xz -C /tmp coolify
mkdir -p ~/.local/bin && install -m 755 /tmp/coolify ~/.local/bin/coolify
```

Se usar `~/.local/bin`, garanta `export PATH="$HOME/.local/bin:$PATH"` no `~/.zshrc`.

**Passo 3: criar o contexto `hsm`**

O token canônico vive em `<repo>/tokens/.env` (pasta git-ignored), nas chaves `COOLIFY_ACCESS_TOKEN` e `COOLIFY_BASE_URL`.

```bash
set -a; source tokens/.env; set +a
coolify context add hsm "$COOLIFY_BASE_URL" "$COOLIFY_ACCESS_TOKEN" --default
```

O contexto fica em `~/.config/coolify/config.json`.

**Validar:**
```bash
coolify context verify
coolify app list
```

Esperado: conexão e autenticação ok, e a tabela com os apps. Sem isso, `/deploy` falha.

**Rotação de token:** edite `tokens/.env` e rode `coolify context set-token hsm "$COOLIFY_ACCESS_TOKEN"`. Não precisa reabrir a sessão do Claude.

**Três coisas que economizam tempo:**
- `coolify app env update <uuid> <KEY> --value "<valor>"`: a chave é **posicional**, e mande só `--value`. A flag `--key` é o rename, e acrescentar `--runtime`/`--build-time` faz a API devolver `422`.
- `coolify app env list <uuid>` esconde os valores (`********`). Para ver de verdade: `coolify app env list <uuid> -s`.
- `coolify deploy uuid <uuid>` (o que dispara build) pode ser **negado** dentro da sessão do Claude, mesmo com `Bash(coolify:*)` na allow-list. Se for, rode você mesmo, no prompt do Claude Code, com o prefixo `!`: `! coolify deploy uuid <uuid>`.
- `--format json` imprime um aviso de versão nova antes do JSON. Filtre antes do `jq`: `... --format json | sed -n '/^[[{]/,$p' | jq`.

### 4.2 GitHub e Context7

O plugin `context7@claude-plugins-official` registra sozinho seu MCP server. Sem configuração extra.

GitHub não precisa de plugin: as skills usam o `gh` autenticado no passo 2, sem token separado.

---

## 5. Permissions (opcional mas recomendado)

O Claude Code pede confirmação pra cada comando Bash novo. Pra reduzir prompts repetitivos sem afrouxar segurança, configure um allow-list.

**Editar `~/.claude/settings.json`:**

```json
{
  "permissions": {
    "defaultMode": "auto",
    "allow": [
      "Bash(git:*)",
      "Bash(gh:*)",
      "Bash(jq:*)",
      "Bash(uv:*)",
      "Bash(coolify:*)",
      "Bash(python3:*)",
      "Bash(pnpm:*)",
      "Bash(npm:*)",
      "Bash(npx:*)",
      "Bash(docker:*)",
      "Bash(docker-compose:*)",
      "Bash(curl -sf http://localhost:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(grep:*)",
      "Bash(find:*)",
      "Bash(date:*)",
      "Read(/Users/<seu-user>/PedroDev/Hospital/**)",
      "Edit(/Users/<seu-user>/PedroDev/Hospital/**)",
      "Write(/Users/<seu-user>/PedroDev/Hospital/**)"
    ]
  },
  "language": "pt-BR"
}
```

Substitua `<seu-user>` pelo seu username (`whoami` mostra). `language: "pt-BR"` faz o Claude responder em português brasileiro (o `CLAUDE.md` também força isso, redundância intencional).

**`defaultMode: "auto"`** = Claude executa ações de baixo risco sem pedir confirmação a cada vez, mas ainda pausa em ações destrutivas (rm -rf, git push --force, etc.).

---

## 6. Verificação end-to-end

Abra sessão Claude Code nova **no diretório do repo** (`cd hospital-reunioes && claude`).

Rode estes comandos um por um e confirme o resultado esperado:

### 6.1 `/pegar-issue` lista a fila
```
/pegar-issue
```
Esperado: tabela com as issues `ready-for-agent` sem dono (pode estar vazia se ninguém criou issues ainda). Se responde "comando não encontrado", a skill local não foi carregada — confirme que está no diretório do repo.

### 6.2 `/deploy status` mostra estado da produção
```
/deploy status
```
Esperado: tabela com nome dos containers + status + última implantação. Se falhar com erro de autenticação do Coolify → revisar passo 4.1.

### 6.3 (opcional) `/atualizar-app` sobe stack local
Só se você instalou Docker e Supabase CLI e quer o app na sua máquina. O fluxo normal do time não passa por aqui.
```
/atualizar-app
```
Esperado: docker-compose rebuilds + sobe backend (`:8000`) e frontend (`:3000`).

```bash
curl -sf http://localhost:8000/api/health  # esperado: {"status":"ok",...}
open http://localhost:3000                  # esperado: tela de login do app
```

---

## 7. Glossário rápido

### Skills do time (versionadas em `.claude/skills/` — já vêm no clone)

| Skill | Quando usar |
|---|---|
| `/grill-with-docs` | **Ideação.** Desafia uma ideia nova contra o domínio (CONTEXT.md + ADRs) e atualiza os docs inline. |
| `/to-prd` | Vira a conversa num PRD = 1 Issue `ready-for-agent`. |
| `/to-issues` | Quebra o PRD em fatias verticais independentes (1 issue cada). |
| `/pegar-issue` | **Sem arg:** lista a fila. **Com `<N>`:** claim atômico + branch + carrega a spec. |
| `/tdd` | Red → green → refactor. Critérios de aceite da Issue viram testes. |
| `/ship` | Orquestrador end-to-end (commit → PR → 3 gates → merge → deploy). |
| `/deploy` | Deploy via Coolify. Subcomandos: `ship`, `status`, `rollback`, `setup`. |
| `/diagnose` | Investigação raiz de bug (reproduz → minimiza → corrige → regressão). |
| `/snapshot` | Regenera `docs/spec/snapshots/` + `ARQUITETURA.md`. Invocado pós-deploy pelo `/deploy`. |
| `/atualizar-app` | Rebuild docker-compose local (opcional). **Não toca produção.** |
| `/ask-pedro` | Router: responde "qual skill eu uso agora?". |
| `/setup-maquina` | Confere a máquina (binários, acessos, chaves) e diz o que falta e onde pegar. |
| as demais | `/ask-pedro` lista e roteia todas (triage, research, resolver-conflitos, montar-ondas, onda, divulgar). |

---

## 8. Troubleshooting

| Problema | Diagnóstico | Fix |
|---|---|---|
| `/pegar-issue` não responde | Não está no repo, ou `.claude/skills/pegar-issue/` foi apagado | `cd /caminho/pra/hospital-reunioes && ls .claude/skills/pegar-issue/SKILL.md` |
| `/deploy` falha com 401 do Coolify | Token expirado ou contexto do CLI desatualizado | `coolify context verify`; se falhar: `set -a; source tokens/.env; set +a && coolify context set-token hsm "$COOLIFY_ACCESS_TOKEN"` |
| `/ship` reprova num gate misterioso | CI, lint, ou review reprovou — output do `/ship` mostra qual | Olhar último comentário no PR (`gh pr view --comments`); corrigir; `/ship` (retoma do passo certo) |
| `/tdd` não roda os testes do backend | `.venv` ausente ou Pango faltando | `cd hospital-reunioes/backend && uv sync`, depois `/setup-maquina` para conferir o import do app |
| Issue não aparece na fila do `/pegar-issue` | Sem label `ready-for-agent`, já tem dono, ou tem "Bloqueada por: #X" aberta | `gh issue view <N>` confere labels/assignee/bloqueio |
| Permission prompts a cada comando | `defaultMode` está como `default` ou allow-list vazia | Passo 5 acima |
| Notificações não chegam no celular | GitHub Mobile sem watching no repo | App GitHub → repo → "Watching" → "All Activity" |

---

## 9. Quando estiver tudo OK

Vai pra [`dev.md`](./dev.md) e leia o fluxo dia-a-dia. As duas entradas são:

```
/grill-with-docs     # ideia nova
/pegar-issue         # trabalho já na fila
```

Pronto.

---

## 10. Lições de campo

O que a memória do Claude Code do Pedro aprendeu em produção e que nenhuma skill diz por inteiro. Cada linha custou pelo menos um round-trip real. Leia uma vez; volte aqui quando o sintoma da primeira coluna aparecer.

| Sintoma ou situação | O que está acontecendo | O que fazer |
|---|---|---|
| PR mergeado, prod com código novo e versão velha no `/api/health` | Bump fantasma: o rebase descartou o commit do bump (`patch contents already upstream`) e o PR entrou sem mexer na versão | Antes de todo merge: `gh pr diff <N> \| grep '"version"'`; a linha `-` tem que ser a versão que está hoje em `origin/main`. Corrigir com re-bump em commit novo |
| Duas migrations com o mesmo número mergeiam limpo | Sessões paralelas numeraram igual; o git não vê | Antes do push final: `git ls-tree origin/main:hospital-reunioes/supabase/migrations/ \| tail`; renumerar com `git mv` + cabeçalho + corpo do PR |
| PR com `no checks reported` | Ou está `CONFLICTING` (o GitHub não roda CI sem merge ref) ou é PR empilhado (o `ci.yml` só roda em `main`) | Rebase + `push --force-with-lease`; commit vazio e close/reopen não resolvem. Pilha: rodar os 3 jobs à mão e esperar o PR de baixo mergear |
| Mergear pilha de PRs após squash | Cada squash cria SHA novo; `git rebase <base>` puro reaplica os commits de baixo | `git rebase --onto origin/main <sha-do-topo-antigo-da-base> <branch-de-cima>` a cada merge. `git rebase --skip` é negado: resolva à mão e `--continue` |
| `pnpm-lock.yaml` ou `uv.lock` em conflito | As duas branches adicionaram dependência | `git checkout --ours` no lockfile e regenerar (`uv lock`; `echo y \| corepack pnpm@9 install --no-frozen-lockfile`). `CI=true` força frozen e quebra |
| Versão oscila no `/api/health` entre duas chamadas seguidas | Container órfão: ao trocar o toggle Consistent Container Names o Coolify subiu o novo e não matou o antigo; o Traefik alterna | Terminal do Coolify: `docker ps \| grep jo6zt` e `docker rm -f <container-com-sufixo-numérico>`. `coolify app restart` não resolve. O toggle e a marcação Build Variable só existem na tela (a API devolve 422) |
| SQL Editor do Studio crasha com `reading 'includes'` em query trivial | Bug de UI do Studio self-hosted (localStorage), o SQL nem chegou ao banco | Janela anônima. Antes de reaplicar: `select to_regclass('public.<tabela>');`. Fallback: Coolify, serviço Supabase, container `supabase-db`, Terminal, `psql -U postgres`. Erro 42701 é paste duplicado |
| Teste passa isolado e dá 429 na suíte inteira | O `limiter` (slowapi) acumula o contador por IP entre arquivos | Fixture autouse que faz `limiter._storage.reset()` (modelo em `tests/test_ata_guiada.py`) |
| `uv run pytest` dá `ModuleNotFoundError: app` num worktree novo | Projeto é `virtual` no lock e o worktree nasce sem `.env` nem `.venv` | Copiar `hospital-reunioes/.env` da árvore principal; `cd backend && uv run --extra dev python -m pytest`. Frontend é `corepack pnpm@9` |
| Teste toca a ClickSign de verdade, ou "verificação em prod" que na real olhou o banco local | O `.env` local tem a chave real da ClickSign e o `SUPABASE_URL` de `127.0.0.1` | Sempre mockar `clicksign_service` ou `httpx.Client` (padrão em `tests/test_signatarios_status.py`). Schema de prod só pelo Studio ou por smoke na API pública |
| Tabela nova acessível pela anon key do frontend | Migration saiu sem RLS | Toda migration com `CREATE TABLE` leva `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` (default-deny; o backend usa service_role). `CREATE POLICY` não tem `IF NOT EXISTS`: use `DROP POLICY IF EXISTS` antes |
| Precisa provar uma tela sem subir Playwright | Chrome headless executa o JS e despeja o DOM | `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --virtual-time-budget=20000 --dump-dom <url>` ou `--screenshot=<png> --window-size=1440,1900`. Achatar com `tr '\n' ' '` antes de grepar |
| Playwright acusa erro em todo `<video>` MP4 | O Chromium do Playwright não tem H.264 | `p.chromium.launch(channel="chrome")` e servir por HTTP (`python3 -m http.server`); confirmar por `readyState >= 1` e `duration > 0` |
| Dois ADRs com o mesmo número em sessões paralelas | O lint indexa por número e um sobrescreve o outro em silêncio | Antes de numerar: `git log origin/main --oneline -5` e `git worktree list`. Quem chega depois renumera e vira emenda em prosa (citação abaixo do frontmatter) |
| Entrada nova do `CHANGELOG.md` sai com travessão e sem versão | `changelog_prepend.py` monta o título no formato errado | Depois do Passo 9.5 do `/deploy ship`, reescrever a entrada à mão no formato das anteriores (`## vX.Y.Z - DATA - assunto`) |
| Classifier nega remoção em massa (worktrees, branches, arquivos) | Loops de remoção são barrados comando a comando | Calcular as listas em arquivo, gravar um script idempotente que só lê as listas, mostrar o resumo e pedir `! bash <script>` |
| Pasta nova nasceu no caminho aposentado | A árvore principal fica atrás de `origin/main`; o `.gitignore` só cobre o layout novo | `git ls-tree -d --name-only origin/main docs/` antes de criar; `git check-ignore -v` no primeiro arquivo gerado (MP4, render, build) |
| Comando devolvido ao humano com `! ...` deu 404 | O UUID ou SHA veio "de cabeça" | Valor lido no mesmo turno: `jq -r '.services[] \| select(.id=="backend") \| .uuid' docs/spec/deploy/project.json` |
| Env var secreta no Coolify | `! coolify app env create ... --value <token>` grava o valor no transcript da sessão | Segredo entra pela tela do Coolify (Environment Variables). Por CLI só valor não secreto (`APP_VERSION`, nome de repo) |
| Senha inicial de usuário do seed | O repo é público; a fórmula antiga da senha vazou no histórico (limpo no PR #589) | Rotação é por aviso do diretor pedindo troca, não por script. Conferir `updated_at` em Studio, Authentication, Users |
| `LLM_MODEL` de produção | Desde 21/08/2026 é `google/gemini-3.7-flash` (env no Coolify; o default do `config.py` continua o modelo antigo) | Preço promocional até 31/12/2026, dobra em 01/01/2027: reavaliar custo em janeiro |

---

## Apêndice — Template completo do `~/.claude/settings.json`

Pra quem quer copiar e ajustar de uma vez. Substitua `<seu-user>` por `whoami`.

```json
{
  "permissions": {
    "defaultMode": "auto",
    "allow": [
      "Bash(git:*)",
      "Bash(gh:*)",
      "Bash(jq:*)",
      "Bash(uv:*)",
      "Bash(coolify:*)",
      "Bash(python3:*)",
      "Bash(pnpm:*)",
      "Bash(npm:*)",
      "Bash(npx:*)",
      "Bash(docker:*)",
      "Bash(docker-compose:*)",
      "Bash(curl -sf http://localhost:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(grep:*)",
      "Bash(find:*)",
      "Bash(date:*)",
      "Read(/Users/<seu-user>/PedroDev/Hospital/**)",
      "Edit(/Users/<seu-user>/PedroDev/Hospital/**)",
      "Write(/Users/<seu-user>/PedroDev/Hospital/**)"
    ]
  },
  "enabledPlugins": {
    "code-review@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "context7@claude-plugins-official": true,
    "skill-creator@claude-plugins-official": true
  },
  "language": "pt-BR"
}
```

E `~/.config/coolify/config.json` (gerado pelo `coolify context add`, não edite à mão):

```json
{
  "instances": [
    { "name": "hsm", "fqdn": "https://<coolify-do-hospital>", "token": "12|...", "default": true }
  ],
  "lastupdatechecktime": "..."
}
```

Os MCP servers `github` e `context7` são registrados automaticamente pelos plugins — não precisa adicionar nada no `~/.claude.json`.
