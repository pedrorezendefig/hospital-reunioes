---
name: ship
description: Skill orquestradora de mudanças end-to-end, do plano ao deploy em produção. Cobre o ciclo completo (branch + plano 🟡 + commit + PR + review automatizada + approval + merge + /deploy ship) em um único comando. Use sempre que o usuário quiser "lançar uma mudança", "subir uma melhoria", "corrigir um bug e ir pra prod", "fazer um PR", "abrir pull request", "shippar", "ship". Sintaxe `/ship "<descrição>" [--issue <N>] [--type fix|feature|chore|refactor|docs] [--no-deploy] [--no-merge] [--skip-review]`. Usa gh CLI pra GitHub e MCP Coolify pro deploy. Roda /code-review e /security-review automaticamente como gate. Self-approval permitido (cada um aprova o próprio PR; o Claude fez review). Cria/finaliza chronicle 🟡/🟢/🔴 em docs/spec/chronicles/ e prepend em docs/spec/CHANGELOG.md. Posta resumo no Discord webhook ao final. Substitui o fluxo manual de "criar branch + commitar + push + abrir PR no browser + aprovar + mergeable + rodar /deploy".
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

---

## Princípio arquitetural

**Esta skill é metodologia pura.** Lê config de `docs/spec/deploy/project.json` (compartilhada com `/deploy` e `/spec`). Não tem conhecimento hardcoded sobre projetos específicos.

Relação com outras skills:
- **`/spec`**: chamada no Passo 3 pra criar o chronicle 🟡 e no Passo 11 (via `/deploy ship` Passo 9) pra rodar pipeline REVERSA.
- **`/deploy`**: chamada no Passo 11 pra subir pra produção. Inclui `/spec update` ao final.
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
   - `docs/spec/deploy/project.json` existe (use `/spec migrate-blueprint` se está vindo de blueprint legado).
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
- `/spec status` retorna "ATUAL" (se "STALE", avisar e seguir).

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
- `spec/<slug>[-<issue>]` (mudanças só em `docs/spec/` ou nas skills)

---

## Passo 3 — Criar chronicle 🟡

```bash
NOW="$(date +%Y-%m-%d-%H%M)"
CHRONICLE="$REPO_ROOT/docs/spec/chronicles/🟡-$NOW-$SLUG.md"

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
duration_spec_s: null
services_touched: []
migrations_applied: 0
---

## Plano

[descreva o que vai fazer, por quê, como, riscos]

### Por que (valor pro negócio)

[por que isso importa pro Hospital, pros usuários, pra operação]

### Como testar

[passos pra reproduzir o comportamento esperado]

### Riscos e rollback

[o que pode quebrar, como reverter]

## Execução / Resultados

_(preencher conforme avança no trabalho)_
EOF
```

**Mostrar caminho do chronicle ao usuário** e abrir em editor padrão (`$EDITOR` ou só listar):
```
Chronicle criado: docs/spec/chronicles/🟡-$NOW-$SLUG.md
Edite-o agora pra preencher Plano. Volte e digite "continuar" quando estiver pronto.
```

---

## Passo 4 — PAUSA pra trabalho humano

A skill ENTRA EM PAUSA. O dev:
1. Edita o chronicle 🟡 com plano detalhado.
2. Faz as mudanças no código.
3. Atualiza chronicle 🟡 conforme avança (`## Execução / Resultados`).
4. Quando terminar tudo, retoma com "continuar" / "pode seguir" / Enter.

Se passado mais de 24h sem retomar, o `/ship` "esquece" o contexto e o usuário precisa retomar manualmente (`/ship` reativa lendo o chronicle 🟡 mais recente da branch atual).

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

Lê `.github/PULL_REQUEST_TEMPLATE.md` e preenche:
- `## O que muda` ← descrição + diff stat resumido
- `## Por quê (valor pro negócio)` ← seção do chronicle
- `## Como testar` ← seção do chronicle
- `## Riscos e rollback` ← seção do chronicle
- `## Plano vinculado` ← link relativo pro chronicle 🟡
- `## Checklist automatizado` ← marcado conforme execução
- `## Closes` ← `Closes #$ISSUE_NUMBER` se houver

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

## Passo 8 — Gates automatizados

Roda em sequência (ou paralelo se possível):

### 8.1 /code-review

Invoca a skill `code-review:code-review` apontando pra branch atual ou PR.

Captura output. Se levantar issues `must-fix` ou similar → ❌ reportar, comentar no PR via `gh pr comment`, parar (sem aprovar/mergear).

### 8.2 /security-review

Invoca a skill `security-review` na branch.

Captura output. Se levantar vulnerabilidades críticas → ❌ reportar, comentar no PR, parar.

### 8.3 CI status (GitHub Actions, se configurado)

Aguarda checks de CI:
```bash
gh pr checks "$PR_NUMBER" --watch
```

Se algum check falhar → ❌ reportar logs (`gh run view <id> --log`), parar.

Se passar `--skip-review`, pula 8.1 e 8.2 mas SEMPRE espera CI (8.3) terminar.

---

## Passo 9 — Aprovar e mergear

```bash
# Aprovar (self-approval permitido)
gh pr review "$PR_NUMBER" --approve --body "Aprovado pelo /ship (/code-review e /security-review passaram, CI verde)"

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
# Invoca a skill /deploy ship (que inclui /spec update no Passo 9)
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
- Rodar `/spec update` (pipeline fullstack do REVERSA, ~12 min).
- Commit separado: `docs(spec): regenerar via REVERSA pos <sha7>`.

Resultado: chronicle agora é `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` ou `🔴-...md`.

---

## Passo 11 — Prepend em CHANGELOG.md

```bash
CHANGELOG="$REPO_ROOT/docs/spec/CHANGELOG.md"
ENTRY=$(cat <<EOF
## $(date '+%Y-%m-%d %H:%M') - $SUBJECT
- Autor: $(git config user.name) <$(git config user.email)>
- SHA: $SHA
- PR: #$PR_NUMBER · Issue: #${ISSUE_NUMBER:-—}
- Resultado: $RESULT_EMOJI $RESULT ($DURATION_DEPLOY_s + $DURATION_SPEC_s spec)
- Detalhe: [chronicles/$CHRONICLE_FINAL_NAME](chronicles/$CHRONICLE_FINAL_NAME)

EOF
)

# Prepend depois do header "# Changelog ..."
python3 - << PY
from pathlib import Path
cl = Path("$CHANGELOG")
lines = cl.read_text().split("\n")
# Encontra primeira linha vazia depois do header (após "# Changelog ...")
insert_at = 0
for i, ln in enumerate(lines):
    if i > 0 and ln.strip() == "" and lines[i-1].startswith("# "):
        insert_at = i + 1
        break
new_entry = """$ENTRY"""
lines.insert(insert_at, new_entry)
cl.write_text("\n".join(lines))
PY
```

Commit do CHANGELOG e push (separado, já na main):
```bash
git add docs/spec/CHANGELOG.md docs/spec/chronicles/
git commit -m "docs(changelog): registrar deploy $SHA"
git push origin "$TARGET_BRANCH"
```

---

## Passo 12 — Notificar Discord

Lê webhook URL de:
1. `docs/spec/deploy/project.json` → `project.integrations[].discord_webhook` (se houver).
2. `$REPO_ROOT/.env` → `DISCORD_WEBHOOK_URL` (não versionado).
3. `~/.config/hospital/discord-webhook.url`.

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
      {"name": "Duração", "value": "${DURATION_DEPLOY_s}s deploy + ${DURATION_SPEC_s}s spec", "inline": true},
      {"name": "PR", "value": "[#$PR_NUMBER]($PR_URL)", "inline": true},
      {"name": "Chronicle", "value": "[ver](https://github.com/$REPO/blob/main/docs/spec/chronicles/$CHRONICLE_FINAL_NAME)", "inline": true}
    ],
    "timestamp": "$(date -Iseconds)"
  }]
}
EOF
)"
```

Se webhook URL não configurada → reportar warning e seguir (não bloqueia).

---

## Output final

```
═══ ship completo ═══

Mudança: $SUBJECT
Autor: $(git config user.name)
Branch: $BRANCH (deletada após merge)
PR: #$PR_NUMBER ($PR_URL)
SHA: $SHA
Resultado: $RESULT_EMOJI $RESULT

Chronicle: docs/spec/chronicles/$CHRONICLE_FINAL_NAME
CHANGELOG.md: atualizado

Discord: ✅ notificado
GitHub Issue: $([ -n "$ISSUE_NUMBER" ] && echo "#$ISSUE_NUMBER fechada automaticamente" || echo "—")

Próximas ações: revisar gaps em docs/spec/gaps.md (se /spec update detectou).
```

---

## Tratamento de falhas

### Falha em qualquer Passo ≤ 7

- Branch local fica. Chronicle 🟡 fica.
- Mudanças não pushed → `git stash` ou commit local.
- Reportar passo onde falhou + mensagem específica.
- Usuário pode retomar com `/ship --continue` (futuro) ou manual.

### Falha em Passo 8 (review)

- PR fica aberto, com comentários da skill review.
- Branch fica.
- Usuário pode corrigir, commitar, push, e rodar `/ship --resume` (recomeça do Passo 8).

### Falha em Passo 9 (merge)

- PR aberto, approved.
- Rodar `/ship --resume` repete o merge.

### Falha em Passo 10 (/deploy)

- A `/deploy` tem rollback automático.
- Chronicle vira 🔴-<sha>-<slug>.md.
- CHANGELOG ganha entrada 🔴.
- Discord notificado da falha.
- `/deploy rollback` pode ser chamado manualmente depois pra reverter.

### Falha em Passo 11-12 (CHANGELOG/Discord)

- Não bloqueia. Reportar warning.
- Estado de produção continua healthy.
- Próximo `/ship` atualiza CHANGELOG normalmente.

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
- `~/.claude/skills/deploy/SKILL.md` — skill `/deploy ship` chamada no Passo 10.
- `Hospital/.claude/skills/spec/SKILL.md` — skill `/spec` chamada no Passo 3 e no Passo 10 (via `/deploy`).
