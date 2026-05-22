---
name: ship
description: Skill orquestradora de mudanças end-to-end, do plano ao deploy em produção. Cobre o ciclo completo (branch + plano 🟡 + commit + PR + review automatizada + approval + merge + /deploy ship) em um único comando. Use sempre que o usuário quiser "lançar uma mudança", "subir uma melhoria", "corrigir um bug e ir pra prod", "fazer um PR", "abrir pull request", "shippar", "ship". Sintaxe `/ship "<descrição>" [--issue <N>] [--type fix|feature|chore|refactor|docs] [--no-deploy] [--no-merge] [--skip-review]`. Usa gh CLI pra GitHub e MCP Coolify pro deploy. Roda /code-review e /security-review automaticamente como gate. Self-approval permitido (cada um aprova o próprio PR; o Claude fez review). Cria/finaliza chronicle 🟡/🟢/🔴 em docs/spec/chronicles/. CHANGELOG.md é prependado pelo /deploy ship (single source of truth — esta skill NÃO escreve no CHANGELOG). Notificação default via GitHub Mobile (push notifications nativas) — Discord webhook opcional (skipa silencioso se não configurado).
---

# ship — orquestrar mudança end-to-end

Uma skill, um comando. Do plano à produção, com PR + review automatizada + merge + deploy. Usado por time de 3 pessoas (Pedro + 2 contratados), todos com Claude Code e permissão de write no repo.

## Sintaxe

```bash
/ship "<descrição curta da mudança>" [opções]
```

### Opções

| Flag | Default | Efeito |
|---|---|---|
| `--issue <N>` | nenhuma | Vincula GitHub Issue #N. Adiciona `Closes #N` no PR. |
| `--type <t>` | inferido | Tipo conventional. Um de: `fix`, `feature`, `chore`, `refactor`, `docs`, `test`, `spec`. Define prefixo de branch e commit. |
| `--no-deploy` | false | Faz tudo menos o `/deploy ship`. Útil pra mudança que não vai pra prod (doc only). |
| `--no-merge` | false | Abre PR mas não aprova nem mergeia. Pra deixar review humana acontecer antes. |
| `--skip-review` | false | Pula `/code-review` e `/security-review`. Só pra emergência. |
| `--draft` | false | Abre PR como draft (não fica passível de merge). |
| `--target <branch>` | `main` | Branch de destino do PR (default main). |
| `--from-diff` | false | Pula a pausa do Passo 4. Usado quando `/start` invoca com working tree já com mudanças. Vai direto do chronicle 🟡 (pré-preenchido pelo diff) pro commit + push + PR. |
| `--resume` | false | Retoma um ciclo interrompido. Lê plano em `docs/planejamento/em-andamento/` da branch atual (campo `fase_atual` no frontmatter) e pula direto pro próximo passo necessário. Ver seção "Retomada via plano" abaixo. |
| `--no-bump` | false | Pula o bump automático de versão (Passo 5.5). Útil pra PRs meta (só skills/docs sem mudar app). |
| `--bump-manual <vX.Y.Z>` | nenhuma | Força versão específica em vez do bump automático. Skill valida semver e exige que seja maior que a atual. |

---

## Princípio arquitetural

**Esta skill é metodologia pura.** Lê config de `docs/spec/deploy/project.json` (compartilhada com `/deploy`). Não tem conhecimento hardcoded sobre projetos específicos.

Relação com outras skills:
- **`/deploy`**: chamada no Passo 11 pra subir pra produção.
- **`/code-review`**: chamada no Passo 8 como gate.
- **`/security-review`**: chamada no Passo 8 como gate.

---

## Bootstrap

1. **Descobrir raiz do repo:**
   ```bash
   REPO_ROOT=$(git -C "$PWD" rev-parse --show-toplevel)
   ```
   Se falhar → reportar e PARAR.

2. **Validar pré-condições**:
   - `gh --version` retorna OK (gh CLI instalado).
   - `gh auth status` autenticado.
   - `docs/spec/deploy/project.json` existe (use `/deploy migrate-blueprint` se está vindo de blueprint legado).
   - `git config user.name` e `user.email` setados (vai pro YAML frontmatter do chronicle).
   - Branch atual é `main` OU explicitamente especificada via `--from <branch>`. Se outra branch, pedir confirmação.

3. **Parsear args**:
   - Descrição obrigatória (primeiro argumento posicional, entre aspas).
   - Inferir `--type` se não passado:
     - Se descrição contém "bug", "corrigir", "fix" → `fix`.
     - Se contém "nova", "adicionar", "feature" → `feature`.
     - Se contém "refactor", "limpar", "simplificar" → `refactor`.
     - Se contém "doc", "readme", "comentário" → `docs`.
     - Default: `chore`.

4. **Gerar slug** a partir da descrição:
   - Lowercase, ASCII, sem acentos.
   - Replace ` ` → `-`.
   - Truncar em 50 chars.

---

## Passo 1 — Pre-flight

Antes de criar branch:

```bash
cd "$REPO_ROOT"
git fetch origin
git status --short
```

Validar:
- Working tree limpa OU só com mudanças relacionadas ao trabalho (perguntar se incluir).
- `main` atualizada com origin/main (sugerir `git pull --rebase origin main` se diff).

Se algum check falhar → ❌ reportar e PARAR.

---

## Passo 2 — Criar branch

```bash
BRANCH="$TYPE/$SLUG"
[ -n "$ISSUE_NUMBER" ] && BRANCH="$BRANCH-$ISSUE_NUMBER"

git checkout -b "$BRANCH"
```

Convenções:
- `fix/<slug>[-<issue>]`
- `feature/<slug>[-<issue>]`
- `chore/<slug>[-<issue>]`
- `refactor/<slug>[-<issue>]`
- `docs/<slug>[-<issue>]`

---

## Passo 3 — Criar chronicle 🟡 (referenciando plano em `docs/planejamento/`)

> **Plano detalhado vive em `docs/planejamento/em-andamento/<slug>.md`** (criado pelo `/start` no Modo A ou B). Chronicle 🟡 aqui é índice enxuto que **referencia** o plano via campo `planejamento:` no frontmatter. Esquema completo: `docs/planejamento/README.md`.

```bash
NOW="$(date +%Y-%m-%d-%H%M)"
CHRONICLE="$REPO_ROOT/docs/spec/chronicles/🟡-$NOW-$SLUG.md"

# Detectar plano associado à branch (criado pelo /start)
PLAN_PATH=""
for f in "$REPO_ROOT/docs/planejamento/em-andamento/"*.md; do
  [ -f "$f" ] || continue
  if grep -qE "^branch:\s*$BRANCH$" "$f"; then
    PLAN_PATH="${f#$REPO_ROOT/}"
    break
  fi
done

cat > "$CHRONICLE" << EOF
---
title: $TYPE($SCOPE): $DESCRIPTION
author: $(git config user.name) <$(git config user.email)>
type: $TYPE
issue: ${ISSUE_NUMBER:-null}
pr: null
date_planned: $(date -Iseconds)
date_deployed: null
sha: null
branch: $BRANCH
result: pending
duration_deploy_s: null
services_touched: []
migrations_applied: 0
planejamento: ${PLAN_PATH:-null}
---

## Plano

> Plano detalhado vive em [\`$PLAN_PATH\`](../../$PLAN_PATH).
> Esta seção do chronicle é o resumo curto pro CHANGELOG e índice.

[1 parágrafo resumindo: o que vai fazer, por quê, qual o impacto. Versão enxuta do §1 do plano.]

## Execução / Resultados

_(preencher conforme avança no trabalho — mas o snapshot vivo do estado fica no §5 do plano, não aqui)_
EOF

# Atualizar plano de volta com referência ao chronicle
if [ -n "$PLAN_PATH" ]; then
  python3 - << PY
import re
p = "$REPO_ROOT/$PLAN_PATH"
content = open(p).read()
content = re.sub(r"^chronicle:.*$", "chronicle: docs/spec/chronicles/🟡-$NOW-$SLUG.md", content, count=1, flags=re.MULTILINE)
open(p, "w").write(content)
PY
fi
```

**Mostrar caminho do chronicle ao usuário**:
```
Chronicle criado: docs/spec/chronicles/🟡-$NOW-$SLUG.md
Plano detalhado: $PLAN_PATH (já criado pelo /start)
Edite o plano se precisar ajustar §1 ou §4, depois digite "continuar".
```

### Fallback: branch sem plano em `docs/planejamento/em-andamento/`

Se `PLAN_PATH == ""` (branch criada fora do `/start` ou plano deletado), aborta com erro educativo:

```
❌ Branch $BRANCH não tem plano correspondente em docs/planejamento/em-andamento/.
Rode `/start --rapido` na branch atual pra criar plano mínimo (3 frases), depois `/ship` de novo.
```

(Tentar continuar sem plano violaria o Corte 3 do plano de enxugamento — exige plano antes de código.)

---

## Passo 4 — PAUSA pra trabalho humano

> **Se invocado com `--from-diff` (típico quando `/start` chama com código pronto no working tree): PULAR este passo.** O chronicle 🟡 já vem pré-preenchido com plano inferido do diff, e o código já existe. Vai direto pro Passo 5 (commit).

A skill ENTRA EM PAUSA. O dev:
1. Edita o chronicle 🟡 com plano detalhado.
2. Faz as mudanças no código.
3. Atualiza chronicle 🟡 conforme avança (`## Execução / Resultados`).
4. Quando terminar tudo, retoma com "continuar" / "pode seguir" / Enter.

Se passado mais de 24h sem retomar, o `/ship` "esquece" o contexto e o usuário precisa retomar manualmente (`/ship` reativa lendo o chronicle 🟡 mais recente da branch atual).

---

## Atualização contínua do plano (transversal ao ciclo)

> Aplica em vários passos abaixo. Cada vez que o estado do trabalho avança (commit feito, PR aberto, gates verdes, mergeado, deploy ok), reescrever §5 (Estado de execução) do plano em `docs/planejamento/em-andamento/<slug>.md` e atualizar campos do frontmatter (`sha_atual`, `fase_atual`, `tarefas_concluidas`).

**§5 do plano é SEMPRE snapshot** — nunca append. Reflete só o agora. Comportamento esperado:

```bash
# Helper conceitual (na prática roda inline em cada passo):
update_plan_state() {
  local plan="$1"          # path do plano em docs/planejamento/em-andamento/
  local phase="$2"         # ex: "PR #42 aberto, aguardando gates"
  local sha=$(git rev-parse --short HEAD)
  local done_count=$(grep -cE "^- \[x\]" "$plan")
  local total=$(grep -cE "^- \[[ x]\]" "$plan")

  python3 - << PY
import re
from datetime import datetime, timezone

p = "$plan"
content = open(p).read()

# Atualiza frontmatter (sha_atual, fase_atual, tarefas_concluidas, date_last_touched)
content = re.sub(r"^sha_atual:.*$", "sha_atual: $sha", content, count=1, flags=re.MULTILINE)
content = re.sub(r"^fase_atual:.*$", 'fase_atual: "$phase"', content, count=1, flags=re.MULTILINE)
content = re.sub(r"^tarefas_concluidas:.*$", "tarefas_concluidas: $done_count", content, count=1, flags=re.MULTILINE)
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
content = re.sub(r"^date_last_touched:.*$", f"date_last_touched: {now_iso}", content, count=1, flags=re.MULTILINE)

# §5 é reescrito inteiro — caller passa o conteúdo bruto da seção
# (já feito no passo específico antes de chamar este helper)

open(p, "w").write(content)
PY
}
```

Quando rodar:
| Passo do ciclo | Atualização do §5 |
|---|---|
| 5 (commit feito) | "Commit `<sha>` feito, branch atualizada localmente" |
| 6 (push) | "Branch pushada pra origin" |
| 7 (PR aberto) | "PR #N aberto, aguardando gates" |
| 8.0 detecção cosmético | "Diff cosmético → gates 2,3 auto-pulados" (se aplicável) |
| 8.5 sync APP_VERSION | "APP_VERSION sincronizada no Coolify backend" |
| 9 (merge) | "PR #N mergeado, esperando webhook do Coolify" |
| 10 ([/deploy ship](.claude/skills/deploy/SKILL.md)) | "/deploy invocado, fase: monitor Coolify" |
| Pós-health verde | (responsabilidade do `/deploy` Passo 9.3.5 — move plano pra `finalizado/`. Em falha sem recovery, deleta o arquivo) |

Falha em qualquer passo é registrada em §5 também (campo "Bloqueios atuais"), pra próxima sessão entender o que travou.

---

## Passo 5 — Commit (conventional commits)

```bash
cd "$REPO_ROOT"
git add <arquivos modificados, exceto hard_excluded>
SUBJECT="$TYPE($SCOPE): $(echo "$DESCRIPTION" | head -c 60)"
git commit -m "$SUBJECT" -m "$(cat <<EOF
$BODY_DO_CHRONICLE_PLANO_RESUMIDO

Closes #$ISSUE_NUMBER  # se setado

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Regras:
- **Nunca** `git add -A` ou `git add .`. Sempre lista explícita.
- Hard-excluded da `/deploy` (project.json `hard_excluded`) NUNCA entram.
- Mensagem do commit segue Conventional Commits (`fix(scope): ...`, `feat(scope): ...`).
- Body inclui resumo do chronicle e referência à issue se houver.

---

## Passo 5.5 — Bump de versão (semver)

A skill aplica bump automático de versão semântica a partir do tipo dominante dos commits do PR. Esquema completo em [docs/spec/VERSIONING.md](../../docs/spec/VERSIONING.md).

### Algoritmo

1. **Ler versão atual** de `hospital-reunioes/frontend/package.json` (campo `version`).

2. **Inspecionar commits do PR** desde a branch base:
   ```bash
   COMMITS=$(git log "$TARGET_BRANCH"..HEAD --format="%s%n%b%n---" --reverse)
   ```

3. **Decidir tipo de bump** (maior precedência ganha — BREAKING > feat > resto):
   - Algum commit tem `BREAKING CHANGE:` no body OU subject termina com `!:` → **major**
   - Algum commit começa com `feat:` ou `feat(<scope>):` → **minor**
   - Caso contrário (`fix:`, `chore:`, `refactor:`, `docs:`, `perf:`, `test:`, `style:`, `build:`, `ci:`) → **patch**

4. **Computar nova versão**:
   - patch: `0.1.0 → 0.1.1`
   - minor: `0.1.0 → 0.2.0` (zera patch)
   - major: `0.1.0 → 1.0.0` (zera minor e patch)

5. **Aplicar bump** (preservando indentação do JSON):
   ```bash
   python3 - << PY
   import json
   p = "hospital-reunioes/frontend/package.json"
   pkg = json.loads(open(p).read())
   pkg["version"] = "$NEW_VERSION"
   open(p, "w").write(json.dumps(pkg, indent=2) + "\n")
   PY

   git add hospital-reunioes/frontend/package.json
   git commit -m "chore(release): bump v$NEW_VERSION"
   ```

6. **Reportar pro usuário** o bump aplicado:
   ```
   [ship] Bump de versão: v0.1.0 → v0.2.0 (tipo dominante: feat)
   ```

### Flags de override

- `--no-bump`: pula o bump. `package.json` fica com a versão atual. Use pra PRs meta (só `.claude/skills/`, `docs/`, etc.).
- `--bump-manual <vX.Y.Z>`: força versão específica em vez do algoritmo. Útil pra marcos (ex: `--bump-manual v1.0.0`). Skill valida semver e que é maior que a atual.

### Fonte da verdade

`hospital-reunioes/frontend/package.json` é a única fonte. O backend lê `APP_VERSION` de env (injetada pelo `/ship` Passo 8.5 pré-merge, ou pelo `/deploy ship` Passo 3.5 quando standalone — ver `.claude/skills/deploy/SKILL.md`). Não há sync manual entre backend e frontend.

---

## Passo 6 — Push da branch

```bash
git push -u origin "$BRANCH"
```

Se falhar (auth, divergência): reportar erro bruto, sugerir correção, PARAR.

---

## Passo 7 — Abrir PR via gh CLI

```bash
PR_URL=$(gh pr create \
  --base "$TARGET_BRANCH" \
  --head "$BRANCH" \
  --title "$SUBJECT" \
  --body "$PR_BODY" \
  --label "type:$TYPE" \
  $(echo "$AREAS" | tr ' ' '\n' | sed 's/^/--label area:/' | tr '\n' ' ') \
  $([ "$DRAFT" = "true" ] && echo "--draft") \
  )
PR_NUMBER=$(echo "$PR_URL" | grep -oE '[0-9]+$')
```

### PR body (a partir do template e do chronicle 🟡)

Lê `.github/PULL_REQUEST_TEMPLATE.md` e preenche 5 seções principais + closes:

- `## 🎯 Contexto` ← seção "Contexto" do chronicle (por quê / valor pro negócio)
- `## ✅ Plano executado` ← seção "Plano" do chronicle (checkboxes copiadas: `[x]` / `[ ]`)
- `## 📊 Mudanças` ← gerada por `/snapshot --diff <base>..HEAD` (rotas novas/modificadas, tabelas afetadas, migrations, integrações)
- `## 🔗 Links` ← issue, chronicle, snapshot links relativos
- `## 🤖 Gates (5 camadas)` ← checkboxes das 5 camadas, marcadas conforme execução
- `## Closes` ← `Closes #$ISSUE_NUMBER` se houver

A seção "Mudanças" usa o output da skill `/snapshot --diff <base>..HEAD` (ver `.claude/skills/snapshot/SKILL.md`). Se a skill falhar ou o repo não tiver mudanças relevantes pra snapshot, a seção é omitida ou contém apenas "_(sem mudanças relevantes ao snapshot)_".

### Labels

- `type:fix|feature|chore|refactor|docs|test|spec` (1)
- `area:backend|frontend|infra|spec|docs|skills` (1+, derivada de `project.json` commit_inference.scope_map ↔ diff)

### Atualizar chronicle com PR number

```bash
sed -i "" "s/^pr: null/pr: $PR_NUMBER/" "$CHRONICLE"
git add "$CHRONICLE" && git commit --amend --no-edit
git push --force-with-lease
```

---

## Passo 8 — Gates automatizados (5 camadas independentes)

Self-approval pelo próprio autor é permitido **só** se as camadas obrigatórias passam. Cada camada faz veto independente. Roda em sequência (ou paralelo onde possível).

### Passo 8.0 — Detecção de diff cosmético (Corte 2 do plano de enxugamento)

Antes de invocar gates, classificar o diff. Se for puramente cosmético, **pular automaticamente Camadas 2 e 3** (sobreposição com Camada 1 não compensa pra mudanças triviais).

**Critério de "diff cosmético"** (todos têm que bater):

```bash
DIFF_FILES=$(git diff --name-only "$TARGET_BRANCH..HEAD")

# 1. Todo arquivo casa padrão permitido
COSMETIC_OK=true
for f in $DIFF_FILES; do
  case "$f" in
    *.tsx|*.jsx|*.css|*.scss|*.md) ;;
    public/*) ;;
    docs/planejamento/*|docs/spec/chronicles/*) ;;
    hospital-reunioes/frontend/package.json)
      # Aceita só se único campo alterado é "version"
      if ! git diff "$TARGET_BRANCH..HEAD" -- "$f" | grep -E "^[+-]\s*\"" | grep -qvE "^[+-]\s*\"version\""; then
        :  # OK, só version
      else
        COSMETIC_OK=false
      fi
      ;;
    *) COSMETIC_OK=false; break ;;
  esac
done

# 2. Nenhum arquivo proibido
for f in $DIFF_FILES; do
  case "$f" in
    *routers/*|*migrations/*|*config.py|*middleware/*|*auth/*|*.env*|*Dockerfile*)
      COSMETIC_OK=false; break ;;
  esac
done

# 3. Nenhum import added/removed
if git diff "$TARGET_BRANCH..HEAD" | grep -qE "^[+-]\s*(import |from .* import)"; then
  COSMETIC_OK=false
fi
```

**Se `COSMETIC_OK == true`:**

- ✅ Pular Camadas 2 e 3 (security-review, requesting-code-review).
- Camadas 1 (code-review), 4 (CI) e 5 (verification) **continuam rodando** — não confiar 100% no critério automático pra mudança trivial sem nenhum gate.
- Comentar no PR: `🤖 Detecção: diff puramente cosmético. Camadas 2 e 3 auto-puladas (critério em ship/SKILL.md#passo-80). Camadas 1, 4, 5 ativas.`
- Registrar em §5 do plano: "Gates 2 e 3 auto-pulados (cosmético)".

**Se `COSMETIC_OK == false`:**

- Todas as 5 camadas rodam normalmente (comportamento padrão).

**Override manual:** `/ship --skip-review` força pular Camadas 1, 2, 3 (emergência). `/ship --hotfix` mantém apenas Camadas 2, 4, 5.

---

### Camada 1 — `/code-review`

Invoca a skill `code-review:code-review` apontando pra branch atual ou PR.

Captura output. Se levantar issues `must-fix` ou similar → ❌ reportar, comentar no PR via `gh pr comment`, parar (sem aprovar/mergear).

### Camada 2 — `/security-review`

Invoca a skill `security-review` na branch.

Captura output. Se levantar vulnerabilidades críticas → ❌ reportar, comentar no PR, parar.

### Camada 3 — `requesting-code-review` (Superpowers)

Invoca a skill `superpowers:requesting-code-review` — dispara subagent **independente** com critérios mais rígidos (tests, edge cases, doc strings, naming, propósito vs implementação). Reforça o self-approval com uma terceira leitura de outra perspectiva.

Captura output. Issues `must-fix` → ❌ reportar, comentar no PR, parar.

### Camada 4 — CI status (GitHub Actions)

Aguarda checks de CI:
```bash
gh pr checks "$PR_NUMBER" --watch
```

Jobs esperados (workflow `.github/workflows/ci.yml`):
- `Backend Lint, Format & Tests` (ruff + pytest)
- `Frontend Lint & Type Check` (pnpm lint + tsc)
- `Build` (docker build dos 2 services como sanity check)

Se algum check falhar → ❌ reportar logs (`gh run view <id> --log`), parar.

### Camada 5 — `verification-before-completion` (Superpowers)

**Imediatamente antes do merge.** Invoca a skill `superpowers:verification-before-completion`:
- Roda comando real de teste/build local (não confia em "deve funcionar").
- Lê output literal.
- Só então confirma sucesso.

Se a verificação falhar → ❌ reportar, parar. Self-approval **não acontece** sem essa camada verde.

### Flags de override

- `--skip-review`: pula Camadas 1, 2 e 3 (review automatizada). **NÃO pula** Camadas 4 (CI) nem 5 (verification). Só pra emergência.
- `--hotfix`: pula Camadas 1 e 3 (mantém 2, 4, 5). Exige aprovação explícita do dono do repo via input.
- Default: todas as 5 camadas rodam.

---

## Passo 8.5 — Sync `APP_VERSION` no Coolify (pré-merge)

Imediatamente antes do `gh pr merge` (que dispara o webhook de auto-build no Coolify), garantir que `APP_VERSION` no service backend reflete a versão atual de `hospital-reunioes/frontend/package.json`. Evita race condition entre o webhook de merge e o `mcp__coolify__bulk_env_update` do `/deploy ship` Passo 3.5 (que rodaria depois e chegaria tarde demais).

```bash
APP_VERSION=$(python3 -c "import json; print(json.load(open('hospital-reunioes/frontend/package.json'))['version'])")
BACKEND_UUID=$(jq -r '.services[] | select(.id == "backend") | .uuid' docs/spec/deploy/project.json)

# Idempotente: se a key já existe com mesmo valor, no-op.
mcp__coolify__env_vars resource=application action=update uuid="$BACKEND_UUID" key=APP_VERSION value="$APP_VERSION" is_runtime=true is_buildtime=false 2>/dev/null \
  || mcp__coolify__env_vars resource=application action=create uuid="$BACKEND_UUID" key=APP_VERSION value="$APP_VERSION" is_runtime=true is_buildtime=false
```

Após esse passo, o squash merge (Passo 9) dispara o webhook do Coolify com `APP_VERSION` já correto no env do container. O `/deploy ship` Passo 3.5 vira **idempotente puro** — só valida que está setado, sem mexer.

Pular se: `--no-deploy` (não vai rodar /deploy ship mesmo), `--no-merge` (nada será mergeado, push manual depois resolve), ou se `frontend/package.json` não existe (projeto sem semver — comum em libs).

---

## Passo 9 — Aprovar e mergear

```bash
# Aprovar (self-approval permitido após as 5 camadas)
gh pr review "$PR_NUMBER" --approve --body "Aprovado pelo /ship — 5 camadas de gate verdes: /code-review · /security-review · requesting-code-review · CI Actions · verification-before-completion"

# Aguardar todos os checks verdes
gh pr checks "$PR_NUMBER" --watch

# Merge (squash, linear history)
gh pr merge "$PR_NUMBER" --squash --delete-branch
```

Se `--no-merge`: pular este passo.

Após merge, voltar pra main local:
```bash
git checkout "$TARGET_BRANCH"
git pull origin "$TARGET_BRANCH"
```

---

## Passo 10 — Deploy

```bash
# Invoca a skill /deploy ship
/deploy ship
```

Se `--no-deploy`: pular este passo.

A `/deploy ship` é responsável por:
- Pre-flight gates.
- Deploy no Coolify via MCP.
- Monitor + health check.
- Rollback se falhar.
- Atualizar `docs/spec/deploy/state.json` e `history.json`.
- Aplicar 🟡🟢🔴 no chronicle (procura por slug similar).
- Atualizar YAML frontmatter do chronicle (autor já estava, agora popula `date_deployed`, `sha`, `result`, `duration_*`).
- Anexar seção `## Implementação / Deploy` no chronicle.

Resultado: chronicle agora é `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` ou `🔴-...md`.

---

## Passo 11 — Resumo final

> **Single source of truth do CHANGELOG = `/deploy ship` Passo 9.5.** Esta skill NÃO prependa o CHANGELOG.md. O passo abaixo só consolida e mostra o resumo do ciclo todo (já feito por `/deploy ship` no Passo 10) numa única tela.

Imprime ao usuário o estado final do ciclo. Lê valores pós-deploy do `docs/spec/deploy/state.json` (recém-escrito pelo `/deploy ship` Passo 9.1) + chronicle 🟢/🔴 já existente.

Não cria commit. Não pushea. Não escreve em arquivo. É display puro.

Ver seção `## Output final` mais abaixo pro formato do bloco impresso.

### Por que não duplica com `/deploy`

A skill `/deploy ship` Passo 9.5 prependa o CHANGELOG porque é o único momento em que existem **simultaneamente** os 4 dados necessários: `result`, `duration_deploy_s`, `sha7` final pós-rollback (se houve), e `chronicle_final_name` (após renomeação 🟡 → 🟢/🔴). Tentar duplicar aqui no `/ship` Passo 11 levaria a race condition ou inconsistência.

---

## Passo 12 — Notificação (Discord opcional)

**Default do time Hospital: sem Discord.** Notificações são nativas via GitHub Mobile (push notifications de PR aberto/mergeado, CI passou/falhou, review request, comentários). Cada membro instala o app e marca o repo como Watching.

A skill **procura** webhook URL nessa ordem e **só posta se achar**:
1. `docs/spec/deploy/project.json` → `project.integrations[].discord_webhook` (se houver).
2. `$REPO_ROOT/.env` → `DISCORD_WEBHOOK_URL` (não versionado).
3. `~/.config/hospital/discord-webhook.url`.

Se **nenhuma das 3 fontes** retornar URL válida:
- Log: `[ship] Discord webhook não configurado, pulando notificação (default do time é GitHub Mobile + Discussions).`
- Continue sem erro. **Não bloqueia o ship.**

Se uma das fontes retornar URL válida, postar:

```bash
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "$(cat <<EOF
{
  "username": "ship-bot",
  "embeds": [{
    "title": "$RESULT_EMOJI $SUBJECT",
    "description": "Mergeado e em produção.",
    "color": $COLOR_DEC,
    "fields": [
      {"name": "Autor", "value": "$(git config user.name)", "inline": true},
      {"name": "SHA", "value": "\`$SHA\`", "inline": true},
      {"name": "Duração", "value": "${DURATION_DEPLOY_s}s deploy", "inline": true},
      {"name": "PR", "value": "[#$PR_NUMBER]($PR_URL)", "inline": true},
      {"name": "Chronicle", "value": "[ver](https://github.com/$REPO/blob/main/docs/spec/chronicles/$CHRONICLE_FINAL_NAME)", "inline": true}
    ],
    "timestamp": "$(date -Iseconds)"
  }]
}
EOF
)"
```

**Decisão importante grande?** Pra "deploy notable" (ex: mudança de arquitetura, breaking change, primeiro release de uma feature), criar uma thread em **GitHub Discussions** categoria "Decisões" via:

```bash
# Discussions API só permite criar discussion via GraphQL, não REST.
# Variação simples: comentar no chronicle 🟢 final + linkar do CHANGELOG.
# Ou: criar Issue tipo "release-notes" com label release.
```

Não automatizado por enquanto — fica como ação manual de quem rodou o ship, se o ship for "notable".

---

## Output final (Corte 4a — compacto)

Bloco único de 4 linhas, com referências essenciais. Sem ruído visual de listas extensas.

```
$RESULT_EMOJI ship $SHA · v$VERSION_PREV → v$VERSION_NEW · ${DURATION_DEPLOY_s}s · $(IFS=,; echo "${SERVICES_TOUCHED[*]}")
   PR #$PR_NUMBER · Chronicle: chronicles/$CHRONICLE_FINAL_NAME
   Plano: planejamento/finalizado/$PLAN_FILENAME (status: finalizado)
   CHANGELOG v$VERSION_NEW prepended · Snapshot $(test -n "$SNAPSHOT_OK" && echo OK || echo skip)$([ -n "$ISSUE_NUMBER" ] && echo " · Issue #$ISSUE_NUMBER fechada" || echo "")
```

**Exemplo concreto** (ciclo de mudança cosmética):

```
✅ ship d3cc4a1 · v0.2.0 → v0.2.1 · 169s · frontend
   PR #9 · Chronicle: chronicles/🟢-2026-05-22-1305-d3cc4a1-versao-footer-sem-link-direita.md
   Plano: planejamento/finalizado/2026-05-22-1241-versao-footer-sem-link-direita.md (status: finalizado)
   CHANGELOG v0.2.1 prepended · Snapshot OK
```

Se rollback aconteceu: emoji muda pra 🔴, linha 1 termina com `(rolled back to <sha>)`, plano é deletado (sem entrada de linha "Plano:" no output). Cronologia da falha sobrevive no chronicle 🔴 + `history.json`.

Notificações (Discord, etc.) reportadas separadamente como linha solta se houver, ou silenciosamente puladas.

---

## Retomada via plano (Corte 4b do plano de enxugamento)

`/ship --resume` substitui o esquema antigo de `progress_step` (nunca implementado). Fonte única da verdade: campo `fase_atual` no frontmatter do plano em `docs/planejamento/em-andamento/<slug>.md`, atualizado continuamente pela seção "Atualização contínua do plano" acima.

### Algoritmo do `--resume`

```bash
# 1. Achar plano da branch atual
BRANCH=$(git branch --show-current)
PLAN=""
for f in docs/planejamento/em-andamento/*.md; do
  [ -f "$f" ] || continue
  grep -qE "^branch:\s*$BRANCH$" "$f" && PLAN="$f" && break
done

[ -z "$PLAN" ] && { echo "❌ Nenhum plano em em-andamento/ pra branch $BRANCH. Não dá pra retomar."; exit 1; }

# 2. Ler frontmatter
FASE=$(grep "^fase_atual:" "$PLAN" | sed 's/^fase_atual:\s*//' | tr -d '"')
SHA_ATUAL=$(grep "^sha_atual:" "$PLAN" | sed 's/^sha_atual:\s*//')
CHRONICLE=$(grep "^chronicle:" "$PLAN" | sed 's/^chronicle:\s*//')
PR=$(grep "^pr:" "$PLAN" | sed 's/^pr:\s*//')

# 3. Mapear fase pra próximo passo do /ship
case "$FASE" in
  *"Commit"*"feito"*)   START_FROM=6 ;;  # push
  *"pushada"*)          START_FROM=7 ;;  # PR
  *"PR"*"aberto"*)      START_FROM=8 ;;  # gates
  *"gates"*"verdes"*)   START_FROM=8.5 ;;  # sync APP_VERSION
  *"APP_VERSION"*)      START_FROM=9 ;;  # merge
  *"mergeado"*)         START_FROM=10 ;;  # /deploy ship
  *"deploy"*"invocado"*) START_FROM=10 ;;  # idem (idempotente, /deploy se recupera)
  *)                    START_FROM=5 ;;  # commit (default, do início)
esac

# 4. Pular pro passo certo
echo "[ship --resume] retomando do passo $START_FROM (fase: $FASE)"
# (executa Passo N em diante)
```

### Pontos de retomada por passo

| Passo onde parou | `--resume` faz |
|---|---|
| Antes do Passo 5 (sem commit) | Vai do Passo 5 (commit) |
| Pós Passo 5 (commit feito, sem push) | Pula pro Passo 6 (push) |
| Pós Passo 6 (push feito, sem PR) | Pula pro Passo 7 (PR aberto) |
| Pós Passo 7 (PR aberto, gates pendentes) | Pula pro Passo 8 (re-rodar gates) |
| Pós Passo 8 (gates verdes, não mergeou) | Pula pro Passo 9 (merge) |
| Pós Passo 9 (mergeado, /deploy não chamado) | Pula pro Passo 10 (/deploy ship) |
| /deploy travado/falhou | `/deploy rollback` ou retry manual; `/ship --resume` re-invoca `/deploy ship` (idempotente) |

Se `--resume` é invocado mas plano não tem `fase_atual` atualizada (cenário raro): aborta com mensagem pedindo verificação manual.

---

## Tratamento de falhas

### Falha em qualquer Passo ≤ 7

- Branch local fica. Plano em `em-andamento/` fica.
- Mudanças não pushed → `git stash` ou commit local.
- Reportar passo onde falhou + mensagem específica.
- §5 do plano atualizada com "Bloqueio: <descrição>".
- Usuário retoma com `/ship --resume` (lê `fase_atual` e pula pro próximo passo).

### Falha em Passo 8 (review)

- PR fica aberto, com comentários da skill review.
- Branch fica.
- §5 do plano: "Bloqueio: Camada N reprovou — corrigir e re-shippar".
- Usuário corrige, commita, push, e roda `/ship --resume` (recomeça do Passo 8).

### Falha em Passo 9 (merge)

- PR aberto, approved.
- §5 do plano: "Bloqueio: merge falhou — <motivo>".
- Rodar `/ship --resume` repete o merge.

### Falha em Passo 10 (/deploy)

- A `/deploy` tem rollback automático.
- Chronicle vira 🔴-<sha>-<slug>.md.
- CHANGELOG ganha entrada 🔴.
- Discord notificado da falha.
- `/deploy rollback` pode ser chamado manualmente depois pra reverter.

### Falha em Passo 11 (Resumo final / Discord)

- Não bloqueia. Reportar warning.
- Estado de produção continua healthy (CHANGELOG já foi prependado por `/deploy ship` Passo 9.5 antes daqui).
- Display final pode ser regerado manualmente via `cat docs/spec/deploy/state.json | jq .last_run`.

---

## Regras

- ❌ **Nunca** `git push --force` à main. Apenas `--force-with-lease` na branch própria pra amend.
- ❌ **Nunca** mergear sem approval (mesmo self).
- ❌ **Nunca** pular `/security-review` em mudanças que tocam `auth/`, `permissions/`, schema DB ou env vars.
- ❌ **Nunca** rodar `/ship` em uma branch que já tem PR aberto sem `--resume` ou flag explícita.
- ❌ **Nunca** logar token/secret em qualquer output.
- ✅ Conventional commits sempre.
- ✅ Chronicle 🟡 obrigatório em todo `/ship` (exceto `--type chore` muito pequeno: dá pra usar `--no-chronicle`, mas default cria).
- ✅ Self-approval permitido (filosofia: Claude já fez review, humano só registra).
- ✅ Discord notificação SÓ no final, com resultado verdadeiro.

---

## Anti-padrões

- ❌ "Vou abrir o PR no browser pra editar a descrição mais bonita." — Não. Template + chronicle dão estrutura suficiente. Edição livre depois do `/ship` se quiser.
- ❌ "Vou pular o chronicle 🟡, é uma mudança pequena." — Não. Chronicle é o lastro do histórico. Mesmo pra typo, deixa 1 linha em `## Plano` e segue.
- ❌ "Vou rodar `/code-review` separado depois do merge." — Não. Review é gate ANTES do merge.
- ❌ "Vou squash 3 commits em 1 antes de pushear." — Sim, pode. Mas use `git rebase -i` cauteloso. O merge final é sempre squash via gh.
- ❌ "Vou commitar com `git commit -am` pra agilizar." — Não. Lista explícita de arquivos.

---

## Referências

- `references/pr-template.md` — template do PR (vai pra `.github/PULL_REQUEST_TEMPLATE.md` na configuração do GitHub).
- `references/chronicle-frontmatter.md` — schema do YAML frontmatter dos chronicles.
- `references/discord-payload.md` — formato do payload pro webhook Discord.
- `https://cli.github.com/manual/` — manual do gh CLI.
- `.claude/skills/deploy/SKILL.md` — skill `/deploy ship` chamada no Passo 10.
