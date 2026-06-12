---
name: ship
description: Skill orquestradora de mudanças end-to-end, do plano ao deploy em produção. Cobre o ciclo completo (branch + commit + PR + 3 gates + approval + merge + /deploy ship) em um único comando. Use sempre que o usuário quiser "lançar uma mudança", "subir uma melhoria", "corrigir um bug e ir pra prod", "fazer um PR", "abrir pull request", "shippar", "ship". Sintaxe `/ship "<descrição>" [--issue <N>] [--type fix|feature|chore|refactor|docs] [--no-deploy] [--no-merge] [--skip-review]`. Usa gh CLI pra GitHub e MCP Coolify pro deploy. Roda /code-review e /security-review automaticamente como gate. Self-approval permitido (cada um aprova o próprio PR; o Claude fez review). Trabalho ancorado na GitHub Issue (Closes #N fecha no merge). Não cria chronicles nem planejamento (modelo Pocock). CHANGELOG.md é prependado pelo /deploy ship (single source of truth — esta skill NÃO escreve no CHANGELOG). Notificação default via GitHub Mobile (push notifications nativas) — Discord webhook opcional (skipa silencioso se não configurado).
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
| `--from-diff` | false | Pula a pausa do Passo 4. Usado quando já há mudanças no working tree. Vai direto pro commit + push + PR (código já no working tree). |
| `--resume` | false | Retoma um ciclo interrompido a partir da Issue (`gh issue view`) e do estado do git. |
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
   - `git config user.name` e `user.email` setados (autor do commit/PR).
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

## Passo 3 — Carregar a Issue

> No modelo Pocock o contexto do trabalho vive na **GitHub Issue**, não em chronicle/plano. Não criar arquivos em `docs/spec/chronicles/` nem `docs/planejamento/`.

Se `--issue <N>` foi passado (ou a branch veio do `/pegar-issue`), carregue a issue:

```bash
gh issue view "$ISSUE" --json title,body,labels,comments --jq "{title, body, labels: [.labels[].name]}"
```

Use o corpo da issue como fonte do PR: o **O que construir** vira o contexto e os **Critérios de aceite** viram o checklist do PR + a base dos testes do `/tdd`. Sem issue associada, descreva a mudança a partir do diff — a issue é a fonte preferida, não obrigatória.

## Passo 4 — Código (via `/tdd`)

> O código nasce no `/tdd` (red → green → refactor) a partir dos critérios de aceite. Com os testes verdes, `/ship` segue para o commit. Com `--from-diff`, o working tree já tem as mudanças → segue direto pro Passo 5.

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
- Body inclui resumo da Issue e `Closes #N` se houver.

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

### PR body (a partir do template e da Issue)

Lê `.github/PULL_REQUEST_TEMPLATE.md` e preenche 5 seções principais + closes:

- `## 🎯 Contexto` ← contexto da Issue (por quê / valor pro negócio)
- `## ✅ Critérios de aceite` ← critérios da Issue (checkboxes `[x]`/`[ ]`)
- `## 📊 Mudanças` ← gerada por `/snapshot --diff <base>..HEAD` (rotas novas/modificadas, tabelas afetadas, migrations, integrações)
- `## 🔗 Links` ← issue (`Closes #N`), snapshot links relativos
- `## 🤖 Gates (3)` ← checkboxes dos 3 gates, marcadas conforme execução
- `## Closes` ← `Closes #$ISSUE_NUMBER` se houver

A seção "Mudanças" usa o output da skill `/snapshot --diff <base>..HEAD` (ver `.claude/skills/snapshot/SKILL.md`). Se a skill falhar ou o repo não tiver mudanças relevantes pra snapshot, a seção é omitida ou contém apenas "_(sem mudanças relevantes ao snapshot)_".

### Labels

- `type:fix|feature|chore|refactor|docs|test|spec` (1)
- `area:backend|frontend|infra|spec|docs|skills` (1+, derivada de `project.json` commit_inference.scope_map ↔ diff)

---

## Passo 8 — Gates automatizados (3 gates)

Self-approval pelo próprio autor é permitido **só** se as camadas obrigatórias passam. Cada camada faz veto independente. Roda em sequência (ou paralelo onde possível).

### Passo 8.0 — Detecção de diff cosmético (Corte 2 do plano de enxugamento)

Antes de invocar gates, classificar o diff. Se for puramente cosmético, **pular o security-review** (o code-review já cobre mudanças triviais).

**Critério de "diff cosmético"** (todos têm que bater):

```bash
DIFF_FILES=$(git diff --name-only "$TARGET_BRANCH..HEAD")

# 1. Todo arquivo casa padrão permitido
COSMETIC_OK=true
for f in $DIFF_FILES; do
  case "$f" in
    *.tsx|*.jsx|*.css|*.scss|*.md) ;;
    public/*) ;;
    docs/adr/*|docs/agents/*|docs/spec/snapshots/*) ;;
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

- ✅ Pular o gate de security-review.
- code-review e CI **continuam rodando** — só o security-review é pulado.
- Comentar no PR: `🤖 Diff cosmético: security-review pulado; code-review + CI ativos.`

**Se `COSMETIC_OK == false`:**

- Os 3 gates rodam normalmente (comportamento padrão).

**Override manual:** `/ship --skip-review` pula code-review e security (emergência); o CI nunca é pulado. `/ship --hotfix` mantém security-review + CI.

---

### Gate 1 — `/code-review` (sempre)

Invoca a skill `code-review:code-review` apontando pra branch atual ou PR.

Captura output. Se levantar issues `must-fix` ou similar → ❌ reportar, comentar no PR via `gh pr comment`, parar (sem aprovar/mergear).

### Gate 2 — `/security-review` (condicional — área sensível)

Invoca a skill `security-review` na branch.

Captura output. Se levantar vulnerabilidades críticas → ❌ reportar, comentar no PR, parar.

### (opcional) review rigorosa — só com `--rigoroso`

Dispara um subagent **independente** (Task/general-purpose) que relê o diff inteiro com critérios mais rígidos que o Gate 1: cobertura de testes (edge cases incluídos), doc strings, naming, e se a implementação cumpre o **propósito** declarado na Issue (não só se o código funciona). Reforça o self-approval com uma terceira leitura de outra perspectiva.

Captura output. Issues `must-fix` → ❌ reportar, comentar no PR, parar.

### Gate 3 — CI (GitHub Actions, sempre)

Aguarda checks de CI:
```bash
gh pr checks "$PR_NUMBER" --watch
```

Jobs esperados (workflow `.github/workflows/ci.yml`):
- `Backend Lint, Format & Tests` (ruff + pytest)
- `Frontend Lint & Type Check` (pnpm lint + tsc)
- `Build` (docker build dos 2 services como sanity check)

Se algum check falhar → ❌ reportar logs (`gh run view <id> --log`), parar.

### (substituída pelo `/tdd`) verificação final com evidência — só com `--rigoroso`

**Imediatamente antes do merge**, verificação com evidência real:
- Roda comando real de teste/build local (não confia em "deve funcionar").
- Lê output literal.
- Só então confirma sucesso — evidência antes de qualquer afirmação de êxito.

Se a verificação falhar → ❌ reportar, parar. Self-approval **não acontece** sem essa camada verde.

### Flags de override

- `--skip-review`: pula code-review e security-review. **NÃO pula** o CI. Só pra emergência.
- `--hotfix`: mantém security-review + CI (pula o resto). Exige aprovação explícita do dono do repo.
- Default: 3 gates (code-review + security-review condicional + CI). Review rigorosa e verificação final ficam opcionais (`--rigoroso`).

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

## Passo 8.6 — Gate de migrations (pré-merge)

Se o diff do PR inclui migrations novas em `hospital-reunioes/supabase/migrations/**`, **PARAR antes do merge** e aplicá-las primeiro. O merge dispara o auto-build no Coolify (webhook do GitHub App) — o schema precisa existir **antes** do código novo subir, senão os endpoints que dependem das tabelas novas quebram (500) até a migration rodar.

> O Postgres do Supabase self-hosted **não é exposto** e o MCP Coolify **não executa SQL** — a aplicação é **manual**, pelo humano, no SQL Editor do Supabase Studio de produção. Esta skill nunca aplica migration sozinha (nada de `docker exec`/`psql` por aqui).

```bash
NEW_MIGRATIONS=$(git diff --name-only --diff-filter=A "$TARGET_BRANCH..HEAD" -- 'hospital-reunioes/supabase/migrations/**')
```

Se houver migrations novas:
1. Para cada uma (ordem cronológica), entregar o **SQL completo** num bloco ` ```sql ` copiável; marcar ⚠ as DESTRUCTIVE (regex de DDL destrutivo — ver `/deploy` SKILL.md "Referência — regex de DDL destrutivo").
2. Entregar o passo a passo: **Supabase Studio de produção** (`studio.<domínio>`, ex.: `https://studio.hospitalsaomatheus.cloud`) → **SQL Editor → New query** → colar → **Run** → confirmar no **Table Editor** ou via `select 1 from <tabela> limit 1;`.
3. **Aguardar a confirmação explícita** do humano ("apliquei") antes de seguir para o merge.

É o mesmo gate do `/deploy` Passo 6, antecipado para antes do merge. Pular se não há migration nova no diff.

---

## Passo 9 — Aprovar e mergear

```bash
# Aprovar (self-approval permitido após os 3 gates)
gh pr review "$PR_NUMBER" --approve --body "Aprovado pelo /ship — gates verdes: /code-review · /security-review (se sensível) · CI Actions"

# Aguardar todos os checks verdes
gh pr checks "$PR_NUMBER" --watch

# Merge (squash, linear history)
gh pr merge "$PR_NUMBER" --squash --delete-branch
```

Se `--no-merge`: pular este passo.

### Passo 9.1 — Marcar critérios de aceite na issue

> Contrato do ADR 0007 (decisão 1): o merge só passa com os três gates verdes e os critérios **são** a lista de testes do `/tdd`, logo "verde ⟹ critérios cumpridos". "Marcado" sempre significa "entregue". Não marcar só no PR — a issue é o que o revisor lê.

Imediatamente após o merge, se há issue vinculada (`$ISSUE_NUMBER`), editar o corpo da **issue**:

- Critério **entregue** → `- [x] ...`
- Critério **descopado** durante o PR → **riscar**, nunca marcar: `- [ ] ~~...~~`

Caso comum (nenhum critério descopado, nenhum checkbox fora da seção de critérios):

```bash
gh issue view "$ISSUE_NUMBER" --json body --jq .body \
  | sed 's/^- \[ \] /- [x] /' > /tmp/issue-body-$ISSUE_NUMBER.md
gh issue edit "$ISSUE_NUMBER" --body-file /tmp/issue-body-$ISSUE_NUMBER.md
```

Se houve descope (ou o corpo tem checkboxes fora de `## Critérios de aceite`), **não** usar o sed cego: editar o corpo critério a critério, marcando os entregues e riscando os descopados. Resultado: issue fechada lê **N/N** quando tudo foi entregue; descopado fica visível riscado, não some.

Este passo é automático — faz parte do merge, sem passo manual. No `--resume` em estado "mergeado", verificar se os critérios da issue já estão marcados; se não, marcar antes de seguir ao Passo 10.

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
- Prepend em `docs/spec/CHANGELOG.md` (link do commit) + regenerar o snapshot/ARQUITETURA da app.
- Issue fechada automaticamente pelo `Closes #N` no merge.

---

## Passo 11 — Resumo final

> **Single source of truth do CHANGELOG = `/deploy ship` Passo 9.5.** Esta skill NÃO prependa o CHANGELOG.md. O passo abaixo só consolida e mostra o resumo do ciclo todo (já feito por `/deploy ship` no Passo 10) numa única tela.

Imprime ao usuário o estado final do ciclo. Lê valores pós-deploy do `docs/spec/deploy/state.json` (recém-escrito pelo `/deploy ship` Passo 9.1).

Não cria commit. Não pushea. Não escreve em arquivo. É display puro.

Ver seção `## Output final` mais abaixo pro formato do bloco impresso.

### Por que não duplica com `/deploy`

A skill `/deploy ship` Passo 9.5 prependa o CHANGELOG porque é o único momento em que existem **simultaneamente** os dados necessários: `result`, `duration_deploy_s` e o `sha7` final pós-rollback (se houve). Tentar duplicar aqui no `/ship` Passo 11 levaria a race condition ou inconsistência.

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
      {"name": "Commit", "value": "[ver](https://github.com/$REPO/commit/$SHA)", "inline": true}
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
# Variação simples: comentar na Issue + linkar do CHANGELOG.
# Ou: criar Issue tipo "release-notes" com label release.
```

Não automatizado por enquanto — fica como ação manual de quem rodou o ship, se o ship for "notable".

---

## Output final (Corte 4a — compacto)

Bloco único de 4 linhas, com referências essenciais. Sem ruído visual de listas extensas.

```
$RESULT_EMOJI ship $SHA · v$VERSION_PREV → v$VERSION_NEW · ${DURATION_DEPLOY_s}s · $(IFS=,; echo "${SERVICES_TOUCHED[*]}")
   PR #$PR_NUMBER
   CHANGELOG v$VERSION_NEW prepended · Snapshot $(test -n "$SNAPSHOT_OK" && echo OK || echo skip)$([ -n "$ISSUE_NUMBER" ] && echo " · Issue #$ISSUE_NUMBER fechada" || echo "")
```

**Exemplo concreto** (ciclo de mudança cosmética):

```
✅ ship d3cc4a1 · v0.2.0 → v0.2.1 · 169s · frontend
   PR #9
   CHANGELOG v0.2.1 prepended · Snapshot OK
```

Se rollback aconteceu: emoji muda pra 🔴, linha 1 termina com `(rolled back to <sha>)`. Cronologia da falha sobrevive em `history.json`.

Notificações (Discord, etc.) reportadas separadamente como linha solta se houver, ou silenciosamente puladas.

---

## Retomada (`--resume`)

`/ship --resume` retoma um ciclo interrompido lendo o **estado do git + a Issue** — não um plano em arquivo.

```bash
BRANCH=$(git branch --show-current)
PR=$(gh pr list --head "$BRANCH" --json number --jq ".[0].number // empty")
```

Mapeia o ponto de retomada pelo estado real:

| Estado do git/PR | `--resume` vai pro |
|---|---|
| Sem commit | Passo 5 (commit) |
| Commit feito, sem push | Passo 6 (push) |
| Pushado, sem PR | Passo 7 (PR) |
| PR aberto, gates pendentes | Passo 8 (gates) |
| Gates verdes, sem merge | Passo 9 (merge) |
| Mergeado, sem deploy | Passo 10 (`/deploy ship`, idempotente) — antes, conferir Passo 9.1 (critérios marcados na issue) |

A Issue (`gh issue view $ISSUE`) traz o contexto; o git traz o progresso. Sem dependência de `docs/planejamento/`.

## Tratamento de falhas

### Falha em qualquer Passo ≤ 7

- Branch local fica. A Issue continua `in-progress`.
- Mudanças não pushed → `git stash` ou commit local.
- Reportar passo onde falhou + mensagem específica.
- Usuário retoma com `/ship --resume` (lê o estado do git e pula pro próximo passo).

### Falha em Passo 8 (review)

- PR fica aberto, com comentários da skill review.
- Branch fica.
- O gate que reprovou é reportado no PR; corrigir e re-shippar.
- Usuário corrige, commita, push, e roda `/ship --resume` (recomeça do Passo 8).

### Falha em Passo 9 (merge)

- PR aberto, approved.
- Rodar `/ship --resume` repete o merge.

### Falha em Passo 10 (/deploy)

- A `/deploy` tem rollback automático.
- CHANGELOG ganha entrada com resultado `rolled-back`/`failed`.
- Discord notificado da falha (se configurado).
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
- ✅ Toda mudança nasce de uma Issue (ou, na falta, descreve a mudança no corpo do PR). Sem chronicle nem plano.
- ✅ Self-approval permitido (filosofia: Claude já fez review, humano só registra).
- ✅ Discord notificação SÓ no final, com resultado verdadeiro.

---

## Anti-padrões

- ❌ "Vou abrir o PR no browser pra editar a descrição mais bonita." — Não. Template + Issue dão estrutura suficiente. Edição livre depois do `/ship` se quiser.
- ❌ "Vou rodar `/code-review` separado depois do merge." — Não. Review é gate ANTES do merge.
- ❌ "Vou squash 3 commits em 1 antes de pushear." — Sim, pode. Mas use `git rebase -i` cauteloso. O merge final é sempre squash via gh.
- ❌ "Vou commitar com `git commit -am` pra agilizar." — Não. Lista explícita de arquivos.

---

## Referências

- `references/pr-template.md` — template do PR (vai pra `.github/PULL_REQUEST_TEMPLATE.md` na configuração do GitHub).
- `references/discord-payload.md` — formato do payload pro webhook Discord.
- `https://cli.github.com/manual/` — manual do gh CLI.
- `.claude/skills/deploy/SKILL.md` — skill `/deploy ship` chamada no Passo 10.
