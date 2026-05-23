# Setup do Claude Code pra trabalhar no Hospital Reuniões

Guia único de setup. Roda do zero até ter `/start` funcionando completo no terminal — com plugins, hooks, MCP servers, e permissões alinhadas ao fluxo do time. Tempo estimado: **15–30 minutos**.

Depois de seguir este guia, leia [`dev.md`](./dev.md) pra entender o fluxo dia-a-dia (`/start` → `/ship` → `/deploy`).

---

## TLDR — checklist enxuto

Se você já conhece Claude Code, é só seguir esta lista. Detalhes nas seções abaixo.

- [ ] [1.](#1-pré-requisitos) Pré-requisitos instalados (Claude Code CLI, gh, jq, python3, docker, node)
- [ ] [2.](#2-clone-do-repo) Repo clonado + `gh auth login` feito
- [ ] [3.](#3-plugins-essenciais) 6 plugins habilitados (`superpowers`, `code-review`, `security-guidance`, `github`, `context7`, `skill-creator`)
- [ ] [4.](#4-mcp-servers) MCP Coolify configurado com `COOLIFY_ACCESS_TOKEN` + `COOLIFY_BASE_URL`
- [ ] [5.](#5-hook-postooluseexitplanmode) Hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json`
- [ ] [6.](#6-permissions-opcional-mas-recomendado) Permissions allow-list mínima (reduz prompts)
- [ ] [7.](#7-verificação-end-to-end) `/start`, `/planejamento status`, `/deploy status` funcionando

---

## 1. Pré-requisitos

Instale antes de tudo:

| Ferramenta | Comando (macOS) | Pra quê |
|---|---|---|
| **Claude Code CLI** | `npm install -g @anthropic-ai/claude-code` ou via [claude.ai/code](https://claude.ai/code) | O agente em si |
| **GitHub CLI** (`gh`) | `brew install gh` | PRs, Issues, reviews — usado por `/ship` e `/issue` |
| **`jq`** | `brew install jq` | Parser JSON em scripts (hooks, gates do `/deploy`) |
| **Python 3.10+** | já vem no macOS recente, ou `brew install python@3.12` | Parser de planos no `recalc_progress.sh` + scripts do `/snapshot` |
| **Docker Desktop** | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | Backend + frontend rodam em docker-compose pra dev local |
| **Node 20+** | `brew install node@20` | Frontend Next.js + scripts auxiliares |

**Validar:**
```bash
claude --version       # > 1.0
gh --version           # > 2.40
jq --version           # > 1.6
python3 --version      # > 3.10
docker --version       # > 24
node --version         # > v20
```

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

Você precisa ter sido adicionado como **collaborator** no repo (peça pro Pedro). Verifique:
```bash
gh repo view --json viewerPermission --jq .viewerPermission
# esperado: WRITE ou ADMIN
```

---

## 3. Plugins essenciais

Plugins do Claude Code são instalados via `/plugin` dentro de uma sessão do Claude Code. Eles vivem em `~/.claude/plugins/cache/` e são habilitados em `~/.claude/settings.json`.

**Plugins obrigatórios pro fluxo do time:**

| Plugin | Pra que serve | Quem usa |
|---|---|---|
| `superpowers@claude-plugins-official` | brainstorming, writing-plans, executing-plans, systematic-debugging, requesting-code-review, verification-before-completion | `/start` (Modo A invoca brainstorming + writing-plans), `/ship` (verification-before-completion + requesting-code-review), `/start debug` (systematic-debugging) |
| `code-review@claude-plugins-official` | `/code-review` — review automatizada do diff | `/ship` Camada 1 de gate |
| `security-guidance@claude-plugins-official` | `/security-review` — review focada em vulns | `/ship` Camada 2 de gate |
| `github@claude-plugins-official` | MCP do GitHub — PRs, Issues, search | `/ship`, `/issue` |
| `context7@claude-plugins-official` | Docs atualizadas de libs (React, Next.js, FastAPI, Supabase) | Claude busca antes de propor mudanças em libs |
| `skill-creator@claude-plugins-official` | Criar/editar skills do time | Quando alguém quiser estender `.claude/skills/` |

**Instalar:**

Dentro de uma sessão Claude Code (`claude` no terminal), digite:

```
/plugin install superpowers@claude-plugins-official
/plugin install code-review@claude-plugins-official
/plugin install security-guidance@claude-plugins-official
/plugin install github@claude-plugins-official
/plugin install context7@claude-plugins-official
/plugin install skill-creator@claude-plugins-official
```

(Você pode rodar todos em sequência, um por linha. Cada `/plugin install` adiciona a entrada em `~/.claude/settings.json` automaticamente.)

**Validar:**
```bash
jq -r '.enabledPlugins | keys[]' ~/.claude/settings.json
```

Você deve ver os 6 plugins listados.

**Opcionais (Pedro usa, time pode pular):**
- `frontend-design@claude-plugins-official` — se for trabalhar muito em UI/UX
- `vercel@claude-plugins-official` — só se for hospedar parte em Vercel
- `ui-ux-pro-max@ui-ux-pro-max-skill` — biblioteca grande de design tokens
- `claude-seo@agricidaniel-seo` — SEO audits (não aplicável ao Hospital, que é interno)

---

## 4. MCP servers

MCP (Model Context Protocol) é como Claude acessa serviços externos. Configuração em `~/.claude.json` (não `~/.claude/settings.json`).

### 4.1 Coolify (obrigatório — sem ele `/deploy` não funciona)

O `/deploy` usa o MCP `@masonator/coolify-mcp` pra falar com a VPS do Hospital.

**Passo 1 — Conseguir o token:**

Logue em [Coolify do Hospital](https://coolify.hospital.example) → Profile → API Tokens → "Create Token" → escopo `read+write` em todas as resources. Copie o token (formato `1|abc...`).

(O Pedro envia o URL real do Coolify + token pra você no setup individual.)

**Passo 2 — Exportar env vars (`.zprofile` ou `.bash_profile`):**

```bash
echo 'export COOLIFY_ACCESS_TOKEN="1|seu-token-aqui"' >> ~/.zprofile
echo 'export COOLIFY_BASE_URL="https://coolify.hospital.example"' >> ~/.zprofile
source ~/.zprofile
```

**Passo 3 — Registrar o MCP server em `~/.claude.json`:**

Abra `~/.claude.json` (cria se não existir) e adicione/mescle:

```json
{
  "mcpServers": {
    "coolify": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@masonator/coolify-mcp"],
      "env": {
        "COOLIFY_ACCESS_TOKEN": "${COOLIFY_ACCESS_TOKEN}",
        "COOLIFY_BASE_URL": "${COOLIFY_BASE_URL}"
      }
    }
  }
}
```

(Se já existir bloco `mcpServers` com outros servers, **mescle** — não substitua.)

**Validar (em sessão Claude Code nova):**
```
/mcp
```

Você deve ver `coolify` listado como conectado. Sem isso, `/deploy` falha.

### 4.2 GitHub e Context7 (já vêm com os plugins)

Os plugins `github@claude-plugins-official` e `context7@claude-plugins-official` registram automaticamente seus MCP servers. Sem configuração extra.

GitHub usa seu `gh auth login` já feito no passo 2 — sem token separado.

---

## 5. Hook PostToolUse:ExitPlanMode

Este hook é o que importa planos do plan mode (`Shift+Tab+Tab`) automaticamente pra `docs/planejamento/em-andamento/plan-mode/` quando você sai do plan mode.

**Editar `~/.claude/settings.json`** e adicionar (junto dos outros matchers se existirem):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "INPUT=$(cat); CWD=$(echo \"$INPUT\" | jq -r '.cwd // \"\"'); SCRIPT=\"$CWD/.claude/skills/planejamento/scripts/import_planmode.sh\"; if [ -d \"$CWD/docs/planejamento/em-andamento/plan-mode\" ] && [ -x \"$SCRIPT\" ]; then (cd \"$CWD\" && bash \"$SCRIPT\" \"$INPUT\") 2>&1; fi; true"
          }
        ]
      }
    ]
  }
}
```

**Validar JSON:**
```bash
python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))" && echo "✓ JSON válido"
```

**Reiniciar:** abra terminal novo (Claude lê `settings.json` ao iniciar sessão).

**Testar:**
1. `cd` no repo Hospital.
2. Abra Claude Code (`claude`).
3. `Shift+Tab+Tab` pra entrar em plan mode.
4. Digite "teste de plano".
5. Aprove o plano.
6. `ls docs/planejamento/em-andamento/plan-mode/` — deve aparecer arquivo novo com timestamp dos últimos 30s.

**Guard:** o hook só dispara em projetos que tem `docs/planejamento/em-andamento/plan-mode/`. Em qualquer outro projeto seu, ele é skip silencioso — não vaza.

---

## 6. Permissions (opcional mas recomendado)

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

Substitua `<seu-user>` pelo seu username (`whoami` mostra). `language: "pt-BR"` faz o Claude responder em português brasileiro (o CLAUDE.md também força isso, redundância intencional).

**`defaultMode: "auto"`** = Claude executa ações de baixo risco sem pedir confirmação a cada vez, mas ainda pausa em ações destrutivas (rm -rf, git push --force, etc.).

---

## 7. Verificação end-to-end

Abra sessão Claude Code nova **no diretório do repo** (`cd hospital-reunioes && claude`).

Rode estes comandos um por um e confirme o resultado esperado:

### 7.1 `/start` reconhecido
```
/start
```
Esperado: a skill responde com "Beleza, tá tudo limpo. O que vamos fazer agora?" (ou similar — depende do estado da branch). Se não responde / fala "comando não encontrado", a skill local não foi carregada — confirme que está no diretório correto.

### 7.2 `/planejamento status` lista planos
```
/planejamento status
```
Esperado: tabela markdown com os planos em `em-andamento/` (pode estar vazio se ninguém estiver trabalhando agora).

### 7.3 `/deploy status` mostra estado da produção
```
/deploy status
```
Esperado: tabela com nome dos containers + status + última implantação. Se falhar com "MCP coolify não conectado" → revisar passo 4.1.

### 7.4 Hook ExitPlanMode importa plano
- `Shift+Tab+Tab` → "plano de teste" → aprovar.
- `ls docs/planejamento/em-andamento/plan-mode/` → arquivo novo dos últimos 30s.

Se nada aparecer, conferir passo 5.

### 7.5 `/atualizar-app` sobe stack local
```
/atualizar-app
```
Esperado: docker-compose rebuilds + sobe backend (`:8000`) e frontend (`:3000`).

```bash
curl -sf http://localhost:8000/api/health  # esperado: {"status":"ok",...}
open http://localhost:3000                  # esperado: tela de login do app
```

---

## 8. Glossário rápido

### Skills locais (versionadas em `.claude/skills/`)

| Skill | Quando usar |
|---|---|
| `/start` | **Entry point único.** Decida só esta. Detecta contexto e roteia pra brainstorm/from-diff/retomar conforme estado da branch. |
| `/ship` | Orquestrador end-to-end (commit → PR → 5 camadas de gate → merge → deploy). Geralmente invocado automaticamente pelo `/start`. |
| `/deploy` | Deploy via Coolify. Subcomandos: `ship`, `status`, `rollback`, `setup`. Geralmente invocado pelo `/ship`. |
| `/issue` | GitHub Issues. Modos: `new` (cria), `listar`, `pegar <N>` (importa contexto). |
| `/planejamento` | Gerencia planos versionados em `docs/planejamento/`. Subcomandos: `progresso`, `importar`, `status`, `finalizar`. |
| `/snapshot` | Regenera `docs/spec/snapshots/` (5 arquivos auto + 2 curados). Invocado pós-deploy pelo `/deploy`. |
| `/atualizar-app` | Rebuild docker-compose local. **Não toca produção.** |

### Superpowers (vêm com o plugin `superpowers@claude-plugins-official`)

| Superpower | Quando dispara |
|---|---|
| `superpowers:brainstorming` | `/start` Modo A (working tree limpo) — dialoga abordagem antes de codar. |
| `superpowers:writing-plans` | Após brainstorming — gera plano com checkboxes. Configurada (via `CLAUDE.md`) pra salvar em `docs/planejamento/em-andamento/superpowers/`. |
| `superpowers:executing-plans` | `/start` Modo D (retomar) — executa plano existente passo a passo. |
| `superpowers:systematic-debugging` | `/start debug` — investigação raiz antes de propor fix. |
| `superpowers:requesting-code-review` | `/ship` Camada 3 de gate — subagent independente com critérios rígidos. |
| `superpowers:verification-before-completion` | `/ship` Camada 5 — roda comandos reais e confirma antes de mergear. |

### Helpers de planejamento

| Script | Pra que |
|---|---|
| `.claude/skills/planejamento/scripts/recalc_progress.sh <plano>` | Recalcula header de progresso + frontmatter. Chamado por `/planejamento progresso`, `/ship`, `/deploy`. Idempotente. |
| `.claude/skills/planejamento/scripts/import_planmode.sh [--source <path>]` | Importa plano do plan mode pra `em-andamento/plan-mode/`. Chamado pelo hook. |

---

## 9. Troubleshooting

| Problema | Diagnóstico | Fix |
|---|---|---|
| `/start` não responde | Não está no repo, ou `.claude/skills/start/` foi apagado | `cd /caminho/pra/hospital-reunioes && ls .claude/skills/start/SKILL.md` |
| `/deploy` falha "MCP coolify não conectado" | Token expirado, env var não exportada, ou MCP não registrado | `echo $COOLIFY_ACCESS_TOKEN` (deve aparecer); `/mcp` em sessão Claude (deve listar `coolify`) |
| Hook ExitPlanMode não importa nada | JSON do `~/.claude/settings.json` quebrado, ou hook não foi recarregado | `python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))"`; reiniciar sessão Claude |
| Plano não atualiza header automaticamente | Helper sem permissão de execução | `chmod +x .claude/skills/planejamento/scripts/*.sh` |
| `/ship` reprova num gate misterioso | CI, lint, ou review reprovou — output do `/ship` mostra qual | Olhar último comentário no PR (`gh pr view --comments`); corrigir; `/start` (retoma do passo certo) |
| `superpowers:brainstorming` não dispara | Plugin `superpowers` não habilitado | `jq '.enabledPlugins["superpowers@claude-plugins-official"]' ~/.claude/settings.json` (deve retornar `true`) |
| Permission prompts a cada comando | `defaultMode` está como `default` ou allow-list vazia | Passo 6 acima |
| Notificações não chegam no celular | GitHub Mobile sem watching no repo | App GitHub → repo → "Watching" → "All Activity" |

---

## 10. Quando estiver tudo OK

Vai pra [`dev.md`](./dev.md) e leia o fluxo dia-a-dia. A regra de ouro é:

```
/start
```

Pronto.

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
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "INPUT=$(cat); CWD=$(echo \"$INPUT\" | jq -r '.cwd // \"\"'); SCRIPT=\"$CWD/.claude/skills/planejamento/scripts/import_planmode.sh\"; if [ -d \"$CWD/docs/planejamento/em-andamento/plan-mode\" ] && [ -x \"$SCRIPT\" ]; then (cd \"$CWD\" && bash \"$SCRIPT\" \"$INPUT\") 2>&1; fi; true"
          }
        ]
      }
    ]
  },
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "github@claude-plugins-official": true,
    "context7@claude-plugins-official": true,
    "skill-creator@claude-plugins-official": true
  },
  "language": "pt-BR"
}
```

E `~/.claude.json` (separado — é onde vão os MCP servers):

```json
{
  "mcpServers": {
    "coolify": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@masonator/coolify-mcp"],
      "env": {
        "COOLIFY_ACCESS_TOKEN": "${COOLIFY_ACCESS_TOKEN}",
        "COOLIFY_BASE_URL": "${COOLIFY_BASE_URL}"
      }
    }
  }
}
```

Os MCP servers `github` e `context7` são registrados automaticamente pelos plugins — não precisa adicionar aqui.
