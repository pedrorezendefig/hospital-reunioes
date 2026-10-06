---
name: ship
description: Leva uma mudança até o PR verde (branch, commit, PR, 3 gates) e roda o rabo, o fechar_onda.py, sem parar. Sintaxe `/ship "<descrição>" [--issue N] [--type ...] [--skip-review]`.
---

# ship — orquestrar mudança end-to-end

Uma skill, um comando. Do plano ao PR verde, com PR + review automatizada + CI. Merge, bump, `APP_VERSION`, push, build, health e registro são do rabo único, o `fechar_onda.py` (ADR 0061): o `/ship` o roda sozinho com os gates verdes (ADR 0063). Usado por time de 3 pessoas (Pedro + 2 contratados), todos com Claude Code e permissão de write no repo.

## Sintaxe

```bash
/ship "<descrição curta da mudança>" [opções]
```

### Opções

| Flag | Default | Efeito |
|---|---|---|
| `--issue <N>` | nenhuma | Vincula GitHub Issue #N. Adiciona `Closes #N` no PR. |
| `--type <t>` | inferido | Tipo conventional. Um de: `fix`, `feature`, `chore`, `refactor`, `docs`, `test`, `spec`. Define prefixo de branch e commit. |
| `--skip-review` | false | Pula os Gates 1 e 2 e termina no PR aberto, sem rodar o rabo. É o modo do `hr-implementador` da onda. |
| `--draft` | false | Abre PR como draft (não fica passível de merge). |
| `--target <branch>` | `main` | Branch de destino do PR (default main). |
| `--from-diff` | false | Pula a pausa do Passo 4. Usado quando já há mudanças no working tree. Vai direto pro commit + push + PR (código já no working tree). |
| `--resume` | false | Retoma um ciclo interrompido a partir da Issue (`gh issue view`) e do estado do git. |

Não há mais opção de merge, deploy ou bump: o `/ship` nunca faz nenhum dos três (ADR 0061).

---

## Princípio arquitetural

**Esta skill é metodologia pura.** Lê config de `docs/spec/deploy/project.json` (compartilhada com `/deploy`). Não tem conhecimento hardcoded sobre projetos específicos.

Relação com outras skills:
- **`fechar_onda.py`** (`.claude/skills/onda-enxuta/scripts/`): o rabo único de merge, bump, `APP_VERSION`, push, build, health e registro, para um PR avulso ou para o lote de uma onda. O `/ship` o roda no Passo 10, com os gates verdes.
- **`/deploy`**: não é chamado. Fica para `status`, `rollback` e `setup`.
- **`hr-revisor`** (`.claude/agents/`): disparado no Passo 8 como Gate 1.
- **`hr-revisor-seguranca`** (`.claude/agents/`): disparado no Passo 8 como Gate 2, uma vez só, quando o `sensivel.py` acusa rota sem login ou migration.

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
   - Branch atual é `main` (o Passo 2 cria a branch) ou a branch de trabalho já criada, como a `<type>/<slug>-<N>` do `/pegar-issue` (o Passo 2 é pulado). Siga sem perguntar. Com `--issue N` e fora da `main`, a branch tem que terminar em `-<N>`: senão, reporte e pare, porque a árvore pode ser compartilhada e a branch, de outra sessão.

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
- Working tree limpa OU só com mudanças relacionadas ao trabalho (entram no commit; arquivo alheio fica de fora, sem perguntar).
- `main` atualizada com origin/main (sugerir `git pull --rebase origin main` se diff).

Se algum check falhar → ❌ reportar e PARAR.

---

## Passo 2 — Criar branch

```bash
BRANCH="$TYPE/$SLUG"
[ -n "$ISSUE_NUMBER" ] && BRANCH="$BRANCH-$ISSUE_NUMBER"

git checkout -b "$BRANCH"
```

Já na branch de trabalho (vinda do `/pegar-issue`): pule este passo.

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
- Sem versão no PR: `hospital-reunioes/frontend/package.json` fica congelado. A versão sobe no rabo, pelo tipo dos commits, na hora do merge, sem commit: vai no `APP_VERSION` do Coolify e na tag `vX.Y.Z` (ADR 0061, issue #967).

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
- `## Migration NNN (conferência por hash)` ← só com migration nova: o `sha256` do arquivo (`shasum -a 256 <arquivo>`) e o SQL completo. O rabo confere esse hash contra o arquivo do head e para se faltar ou divergir; mexeu na migration, atualize o hash e o SQL do corpo.

A seção "Mudanças" usa o output da skill `/snapshot --diff <base>..HEAD` (ver `.claude/skills/snapshot/SKILL.md`). Se a skill falhar ou o repo não tiver mudanças relevantes pra snapshot, a seção é omitida ou contém apenas "_(sem mudanças relevantes ao snapshot)_".

### Labels

- `type:fix|feature|chore|refactor|docs|test|spec` (1)
- `area:backend|frontend|infra|spec|docs|skills` (1+, derivada de `project.json` commit_inference.scope_map ↔ diff)

---

## Passo 8 — Gates automatizados (3 gates)

Cada camada faz veto independente. Roda em sequência (ou paralelo onde possível). Gate reprovado não para o `/ship`: chama o agente `hr-corretor` (prompt em `.claude/skills/onda-enxuta/references/prompts.md`) e roda o gate de novo, como diz cada gate. Os 3 gates verdes levam ao rabo (Passo 10), sem esperar mensagem (ADR 0063). Na `/onda-enxuta`, o `hr-implementador` roda `/ship --skip-review` e termina no PR aberto: quem espera o CI, revisa e chama o corretor é o orquestrador da onda (passo 4 dela).

**Baixa** (o fim de uma fatia que não fecha): `gh issue edit <issue> --remove-label in-progress --add-label ready-for-human`, um `gh issue comment` com `<!-- automacao -->` na primeira linha e o diagnóstico (gate ou linha do rabo, achado, o que o corretor tentou e a hipótese), e `PushNotification` de uma linha: "#<issue> foi para ready-for-human: <motivo>". O PR fica aberto e o rabo não roda.

### Passo 8.0 — Detecção de diff cosmético (Corte 2 do plano de enxugamento)

Antes de invocar gates, classificar o diff. Se for puramente cosmético, **pular o Gate 2** (o Gate 1 já cobre mudanças triviais). Exceção: com o `sensivel.py` em saída 0 (Gate 2), o Gate 2 roda mesmo em diff cosmético.

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

- ✅ Pular o Gate 2, salvo a exceção do `sensivel.py` acima.
- Gate 1 e CI **continuam rodando**: só o Gate 2 é pulado.
- Comentar no PR: `🤖 Diff cosmético: Gate 2 pulado; hr-revisor + CI ativos.`

**Se `COSMETIC_OK == false`:**

- Os 3 gates rodam normalmente (comportamento padrão).

**Override manual:** `/ship --skip-review` pula os Gates 1 e 2; `/ship --hotfix` mantém o Gate 2 e o CI. O CI nunca é pulado, e nos dois o `/ship` termina no PR, sem o Passo 10 (veja "Flags de override").

---

### Gate 1: `hr-revisor` (sempre)

Dispara o agente `hr-revisor` com o prompt de `.claude/skills/onda-enxuta/references/prompts.md` (rodada 1). Ele lê o diff pelo GitHub, não a árvore de trabalho, e comenta o veredito no PR; confira com `gh pr view "$PR_NUMBER" --json comments` que a última linha do comentário é `VEREDITO: LIMPO` ou `VEREDITO: MUST-FIX (n)`.

`MUST-FIX` → disparar o `hr-corretor` motivo `revisao` com o comentário inteiro, sem esperar o Gate 2; quando ele terminar, rodada 2 do `hr-revisor`. O veredito traz só must-fix, e há uma rodada de correção (ADR 0064): se a rodada 2 ainda tem must-fix, é baixa (Passo 8).

### Gate 1.5: Spec × diff (quando há issue vinculada)

Verifica se o diff cumpre o que a issue pediu **antes** do merge: é o que autoriza o Passo 9 a marcar os critérios de aceite (o contrato "verde ⟹ critérios cumpridos" do ADR 0020 passa a ser verificado, não assumido). Sem issue vinculada, pular com nota no PR. Não muda a contagem dos "3 gates" (`hr-revisor`, `hr-revisor-seguranca`, CI): este é condicional à existência de issue.

**Fail-fast antes de spawnar** (barato, evita queimar um subagent com ref quebrada):

```bash
git rev-parse "$TARGET_BRANCH" >/dev/null || { echo "ref inválida"; exit 1; }
[ -n "$(git diff "$TARGET_BRANCH...HEAD" --name-only)" ] || { echo "diff vazio"; exit 1; }
```

Dispara um subagent **independente** (Task/general-purpose) com:

- O ponto fixo, sem perguntar (não travar a `/onda-enxuta`): `git diff $TARGET_BRANCH...HEAD` (três pontos, merge-base) + `git log $TARGET_BRANCH..HEAD --oneline`.
- O corpo da issue já carregado no Passo 3 (O que construir + Critérios de aceite).
- O brief: "Reporte só o que impede o merge (ADR 0064), como must-fix: (a) requisitos que a issue pediu e estão **faltando ou parciais** no diff; (b) requisitos que parecem implementados mas cuja implementação **tem cara de errado**. Cite a linha da spec em cada achado. Menos de 400 palavras."

Achado → comentar no PR via `gh pr comment` como must-fix e disparar o `hr-corretor` motivo `revisao` na hora, com o mesmo tratamento do Gate 1 (uma rodada, depois baixa).

### Gate 2: `hr-revisor-seguranca` (rota sem login ou migration)

```bash
python3 .claude/skills/onda-enxuta/scripts/sensivel.py "$PR_NUMBER"
```

Saída `0` (o PR toca rota sem login ou migration, a lista de `.claude/skills/onda-enxuta/revisao-sensivel.txt`): dispare o agente `hr-revisor-seguranca` **uma vez só**, em paralelo com o Gate 1, com o prompt de `references/prompts.md` da onda (motivo: os arquivos impressos). Ele lê o diff pelo GitHub; o `/security-review` lia o diff da árvore principal quando o trabalho estava num worktree, por isso não é mais o gate. Saída `1`: o gate não se aplica; o resto da segurança é a lente do `hr-auditor-prd` (ADR 0064, decisão 4, parágrafo abaixo). Saída `2` (erro do `gh`): o gate não passa; rode de novo, e na segunda falha é baixa.

Ninguém espera por ele: o corretor do Gate 1 não aguarda este veredito. `VEREDITO SEGURANCA: MUST-FIX` → `hr-corretor` motivo `revisao` com o comentário de segurança, uma rodada de correção a mais (com um corretor já no PR, este vai quando ele terminar); o `hr-revisor-seguranca` não roda de novo, e quem confere é a rodada seguinte do Gate 1, com a linha `Veredito de segurança a conferir: <URL>` no prompt (cada must-fix dele vira spec da rodada), com a mesma regra da baixa. O gate passa com a última linha do comentário em `VEREDITO SEGURANCA: LIMPO`, ou com o must-fix dele corrigido e a rodada seguinte do Gate 1 em `VEREDITO: LIMPO`.

**Lente do `hr-auditor-prd` no `/ship` avulso** (na onda, quem a dispara é o fechamento): com o rabo verde (Passo 10), se a issue fechou a última fatia aberta do PRD (`gh api repos/{owner}/{repo}/issues/<PRD>/sub_issues --paginate --jq '.[] | select(.state == "open") | .number'` vazio), dispare o `hr-auditor-prd` com o prompt do PRD de `references/prompts.md`; issue sem PRD, ou PR sem issue, recebe a lente no próprio PR, com o prompt `PR #<N>` no lugar do PRD. Vale com ou sem Gate 2: é a única revisão de segurança do resto do diff. Detalhe de segurança que vier no relatório do auditor vai ao humano por `PushNotification`, nunca ao GitHub.

### (opcional) review rigorosa: só com `--rigoroso`

Com a flag, roda a review rigorosa e a verificação final com evidência (rodadas extras, checklist e critérios). Passo a passo em `references/rigoroso.md`.

### Gate 3 — CI (GitHub Actions, sempre)

Aguarda checks de CI:
```bash
gh pr checks "$PR_NUMBER" --watch
```

Jobs esperados (workflow `.github/workflows/ci.yml`):
- `Backend Lint, Format & Tests` (ruff + pytest)
- `Frontend Lint & Type Check` (pnpm lint + tsc)
- `Build` (docker build dos 2 services como sanity check)

Se algum check falhar, rode antes `python .claude/skills/onda-enxuta/scripts/ci_sem_runner.py "$PR_NUMBER"`. Saída 0 = o GitHub cancelou o job por falta de runner (incidente do Actions, issue #953), não é código: o script já pediu o rerun, volte ao `gh pr checks --watch` (até 3 vezes; depois, reporte "GitHub Actions sem runner, ver githubstatus.com" e pare sem mexer no código). Saída 1 = falha de verdade → `hr-corretor` motivo `ci` com as últimas 60 linhas de `gh run view <id> --log-failed`; a segunda falha de CI da fatia vai para o `hr-corretor-max`. Depois da correção, `gh pr checks --watch` de novo. Cada falha conta uma tentativa da fatia (ADR 0022); na terceira, baixa (Passo 8).

### (substituída pelo `/tdd`) verificação final com evidência: só com `--rigoroso`

Ver `references/rigoroso.md` (segunda parte).

### Flags de override

- `--skip-review`: pula os Gates 1 e 2, **NÃO pula** o CI, e o `/ship` termina no PR aberto, sem o Passo 10. É o modo do `hr-implementador` da onda, onde quem revisa e roda o rabo é o orquestrador; fora da onda, subir é `/ship --resume` sem a flag, que roda os gates que faltam.
- `--hotfix`: mantém o Gate 2 (`sensivel.py` e `hr-revisor-seguranca`) e o CI, pula o resto e termina no PR verde, sem o Passo 10 (ADR 0063, decisão 4: o rabo só roda com os gates verdes). Subir é `/ship --resume` sem a flag, que roda o Gate 1.
- Default: 3 gates (`hr-revisor` + `hr-revisor-seguranca` condicional + CI). Review rigorosa e verificação final ficam opcionais (`--rigoroso`).

---

## Passo 8.6: Gate de migrations (o rabo espera o recibo)

Se o diff do PR inclui migrations novas em `hospital-reunioes/supabase/migrations/**`, elas são aplicadas **antes do merge**. O merge dispara o auto-build no Coolify (webhook do GitHub App): o schema precisa existir **antes** do código novo subir, senão os endpoints que dependem das tabelas novas quebram (500) até a migration rodar.

Quem segura o merge é o próprio rabo (issue #969): toda migration termina gravando o próprio número em `migracoes_aplicadas` (o CI reprova a que não grava), o `/api/health` devolve o maior número gravado, e o `fechar_onda.py` imprime o caminho clicável `<arquivo>:1` de cada migration nova e só pega o semáforo e mergeia quando o health devolve o número da maior. Teto de 24 h; vencido, sai com `7` sem tocar na `main`. O rabo pode rodar já, sem esperar o humano colar.

> O Postgres do Supabase self-hosted **não é exposto** e o CLI/API do Coolify **não executa SQL**: a aplicação é **manual**, pelo humano, no SQL Editor do Supabase Studio de produção. Esta skill nunca aplica migration sozinha (nada de `docker exec`/`psql` por aqui).

```bash
NEW_MIGRATIONS=$(git diff --name-only --diff-filter=A "$TARGET_BRANCH..HEAD" -- 'hospital-reunioes/supabase/migrations/**')
```

Se houver migrations novas:
1. Conferir que o corpo do PR traz o `sha256` de cada uma (seção `## Migration NNN (conferência por hash)`, Passo 7). O rabo confere de novo nas pré-condições e para se faltar ou divergir.
2. Para cada uma (ordem cronológica), extrair o arquivo para o scratchpad por `git show` e entregar **primeiro o caminho absoluto clicável terminado em `:1`** (abre em aba do VS Code), junto do arquivo de verificação; o bloco ` ```sql ` no chat é reforço, não o caminho principal. Regra completa em `/deploy` SKILL.md, Passo 6.3. Marcar ⚠ as DESTRUCTIVE (regex de DDL destrutivo: ver `/deploy` SKILL.md, seção "Referência: regex de DDL destrutivo").
3. Entregar o passo a passo: **Supabase Studio de produção** (`studio.<domínio>`, ex.: `https://studio.hospitalsaomatheus.cloud`) → **SQL Editor → New query** → colar → **Run** → rodar a query de verificação e conferir a contagem de linhas esperada.
4. Dizer no resumo final que o rabo espera a migration aparecer no `/api/health` (até 24 h) e segue sozinho depois que o humano cola.

Pular se não há migration nova no diff.

---

## Passo 9: Marcar critérios de aceite na issue

> Contrato do ADR 0020 (decisão 1): os critérios **são** a lista de testes do `/tdd`, e os três gates verdes dizem "verde ⟹ critérios cumpridos". Não marcar só no PR: a issue é o que o revisor lê. Com o Gate 1.5 (spec × diff) verde, essa implicação é **verificada** contra o diff, não só assumida.

Com os gates verdes, se há issue vinculada (`$ISSUE_NUMBER`) **e o Gate 1.5 passou verde**, editar o corpo da **issue**:

- Critério **entregue** → `- [x] ...`
- Critério **descopado** durante o PR → **riscar**, nunca marcar: `- [ ] ~~...~~`

Caso comum (nenhum critério descopado, nenhum checkbox fora da seção de critérios):

```bash
gh issue view "$ISSUE_NUMBER" --json body --jq .body \
  | sed 's/^- \[ \] /- [x] /' > /tmp/issue-body-$ISSUE_NUMBER.md
gh issue edit "$ISSUE_NUMBER" --body-file /tmp/issue-body-$ISSUE_NUMBER.md
```

Se houve descope (ou o corpo tem checkboxes fora de `## Critérios de aceite`), **não** usar o sed cego: editar o corpo critério a critério, marcando os entregues e riscando os descopados. Resultado: issue fechada lê **N/N** quando tudo foi entregue; descopado fica visível riscado, não some.

No `--resume` com os gates verdes, verificar se os critérios da issue já estão marcados; se não, marcar antes de seguir ao Passo 10.

---

## Passo 10: Rodar o rabo

O `/ship` não faz bump, não mexe em `APP_VERSION`, não mergeia e não chama o `/deploy` (ADR 0061): tudo isso é do rabo, e o `/ship` o roda assim que o Passo 9 termina, sem esperar mensagem (ADR 0063). Builds levam minutos: rode via Bash em segundo plano e leia só as 10 linhas da saída.

Só roda com os três gates verdes nesta passada: o último comentário do Gate 1 termina em `VEREDITO: LIMPO`, o do Gate 2, quando ele se aplica, em `VEREDITO SEGURANCA: LIMPO` (ou com o must-fix dele corrigido antes da última rodada do Gate 1), e o CI está verde. Sem isso, o rabo não roda.

```bash
python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs "$PR_NUMBER"
```

Migration nova no PR para o rabo no humano (Passo 8.6): ele imprime `migration: cole no Studio <arquivo>:1` e espera; repasse a linha ao humano por `PushNotification` assim que ela aparecer. Com `--skip-review` ou `--hotfix`, o `/ship` termina no PR e não chega aqui (veja "Flags de override"); na `/onda-enxuta`, o `hr-implementador` roda com `--skip-review`, e quem roda o rabo, com o lote inteiro, é o fechamento da onda.

Fatia de manual (`docs: manual do PRD`, ADR 0057, decisões 4 e 8, que a ADR 0063 não emendou) também não chega aqui sozinha: o vídeo de tarefa pede o OK humano no draft. O `/ship` termina no PR verde, com o caminho do MP4 no corpo, e manda `PushNotification` de uma linha: "Draft do vídeo da #<issue> no PR #<PR>: <MP4>". Quem viu o vídeo sobe o PR com `fechar_onda.py --prs <PR>`.

Um PR só e sem `--sessao` é o modo PR avulso (chave do semáforo `pr-<N>`). O script faz, nesta ordem: pré-condições (PR verde e mergeável, número e `sha256` das migrations), espera da migration nova no `/api/health` (Passo 8.6), semáforo, versão nova pelo tipo dos commits, sem commit (issue #967), a `origin/main` trazida por merge se a branch ficou atrás (e o CI verde nesse head novo), `APP_VERSION` no backend e no frontend do Coolify antes do merge, merge pela API do GitHub (a `main` é protegida, ADR 0061), tag `vX.Y.Z` no squash, um build, health com conferência de versão, registro (`state.json` e `history.json`) num PR só de docs mergeado do mesmo jeito, e limpeza. Snapshot e draft do Manual não são do rabo: uma Action no push da `main` cuida deles depois do registro (ADR 0062). O registro nomeia o PR e a issue. Códigos de saída e o que fazer em cada um: docstring do script.

**Saída `2` (conflito):** com a linha `conflito no merge de #N em: <arquivos>` na saída do rabo, quem o rodou dispara o agente `hr-corretor` com motivo `conflito`, o PR e os arquivos da linha (prompt em `.claude/skills/onda-enxuta/references/prompts.md`): ele rebaseia o PR sobre a `origin/main` pela skill `resolver-conflitos` e dá push. Depois, `gh pr checks "$PR_NUMBER" --watch`, para o CI rodar sobre o código combinado (vermelho segue o Gate 3), e o rabo de novo. Cada conflito conta uma tentativa da fatia, escrita num `gh issue comment` com `<!-- automacao -->` na primeira linha (`tentativa k de 3`); na terceira, `gh issue edit <issue> --remove-label in-progress --add-label ready-for-human`, um comentário com o diagnóstico (a linha do rabo, os arquivos em conflito, o que o corretor tentou e a hipótese) e `PushNotification` de uma linha: "#<issue> foi para ready-for-human: conflito em <arquivos>". Saída `2` sem essa linha (push rejeitado, CI vermelho ou merge recusado): a linha do rabo diz a causa; CI vermelho segue o Gate 3, o resto roda o rabo de novo, e também conta tentativa.

**Saída `6` (rollback feito):** o health falhou e o rabo já voltou cada app do lote à imagem anterior no Coolify e ao `APP_VERSION` antigo, conferiu o health de novo e deixou o semáforo solto; produção está boa, mas o merge ruim segue na `main`. Quem rodou o rabo faz, nesta ordem: (1) abre o PR de revert do squash que a linha `rollback:` imprime (`git revert --no-edit <sha>` numa branch `revert/pr-<N>` a partir da `origin/main`, depois `gh pr create`), sem rebuild, porque a imagem no ar já é a anterior; ele vai na frente do próximo rabo, para o próximo deploy não carregar o defeito; (2) `gh issue reopen <issue>`, `gh issue edit <issue> --remove-label in-progress --add-label ready-for-agent` e um `gh issue comment` com `<!-- automacao -->` na primeira linha e a linha `health:` do rabo (o que o health respondeu); (3) conta uma tentativa da fatia e a escreve no comentário (`tentativa k de 3`; na terceira, `ready-for-human` no lugar de `ready-for-agent`); (4) notifica pela ferramenta `PushNotification`: "rollback disparado no PR #N, versão vX.Y.Z voltou", com a versão da linha `rollback:`.

Saída `4` (health) é o rollback automático que falhou: o semáforo fica preso e o caminho é o `/deploy rollback`.

**Saída `7` (migration vencida):** o `/api/health` não devolveu o número da migration do lote em 24 h; nada entrou na `main`, o semáforo nem foi pego e o PR segue aberto, sem nada a reverter. Quem rodou o rabo notifica pela ferramenta `PushNotification` com a linha `migration: vencida` e roda o rabo de novo depois que o humano colar o arquivo da linha `migration: cole no Studio`. Não conta tentativa: o código não falhou.

---

## Passo 10.5: Pendências humanas (fila `ready-for-human`)

Se o ciclo terminou deixando ações que **só o humano pode fazer** (import de dado na virada, rotação de credencial, ato em sistema externo, validação manual), registrá-las antes do resumo final:

- **1 issue por pendência** (ou 1 issue com checklist quando os passos são um fluxo único), com o label **`ready-for-human`**.
- Vincular ao PRD **pelo corpo** ("Pai: #N"), **nunca como sub-issue nativa**: a Action de higiene só auto-fecha o PRD quando todas as sub-issues fecham, e uma pendência humana aberta travaria esse fechamento (e a auditoria da `/onda-enxuta`, ADR 0029).
- Corpo em pt-BR com: o que fazer (comandos prontos quando houver), por que ficou pendente e links de rastreio (PR, deploy, ADR).
- Nunca duplicar: se a pendência já tem issue aberta, comentar nela em vez de criar outra.

Essas issues alimentam a aba **Pendências** do painel (`tools/workflow-dashboard`), que lê a fila `ready-for-human` direto do GitHub, sem nenhum arquivo de estado paralelo. Elas ficam fora do Plano por inteiro (ondas, entregues e medianas de lead time: fila humana, não de agente); ao concluir, o humano fecha a issue e a pendência some do painel.

Pular se o ciclo não deixou pendência nenhuma.

---

## Passo 11: Resumo final

Imprime ao usuário o estado final do ciclo, no formato da seção "Output final" abaixo: o PR verde, os gates, a issue e a linha final do rabo. Não cria commit. Não pushea. Não escreve em arquivo. É display puro.

O `history.json` e o `state.json` são escritos pelo rabo, no PR de registro depois do health; o `/ship` não toca em nenhum deles.

---

## Passo 12: Notificação (Discord opcional)

**Default do time Hospital: sem Discord.** Notificação é o GitHub Mobile. Só posta se achar uma webhook URL (`project.json`, `.env` ou `~/.config/hospital/discord-webhook.url`); sem URL, loga e segue, sem erro. Fontes, payload e o caso "deploy notable" em `references/discord.md`.

---

## Output final (Corte 4a, compacto)

Bloco único de 3 linhas, com referências essenciais. Sem ruído visual de listas extensas.

```
✅ ship PR #$PR_NUMBER verde · gates: $GATES_VERDES$([ -n "$ISSUE_NUMBER" ] && echo " · Issue #$ISSUE_NUMBER com critérios marcados")
   Rabo: python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs $PR_NUMBER → <a última linha da saída>
   $([ -n "$NEW_MIGRATIONS" ] && echo "Migration: o rabo espera $NEW_MIGRATIONS no /api/health antes do merge (Passo 8.6)")
```

**Exemplo concreto** (ciclo de mudança cosmética):

```
✅ ship PR #9 verde · gates: hr-revisor, spec×diff, CI · Issue #8 com critérios marcados
   Rabo: python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs 9 → <a última linha da saída>
```

Baixa (Passo 8): emoji muda pra ❌ e a linha 2 dá o gate e o motivo em vez da linha do rabo.

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
| Gates verdes | Passo 9 (critérios na issue) e Passo 10 (rabo) |
| PR mergeado | Nada: o rabo já rodou. Conferir no `history.json` |

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
- O gate que reprovou chama o `hr-corretor` (Passo 8); só a baixa devolve o PR ao humano.
- Depois da baixa, o humano corrige, commita, dá push e roda `/ship --resume` (recomeça do Passo 8).

### Falha no rabo

- Não é do `/ship`: o `fechar_onda.py` diz o que fazer pelo código de saída (1 pré-condição, 2 conflito ou push rejeitado, com o `hr-corretor` e uma tentativa contada por volta, como diz o Passo 10, 3 build, 4 health com o rollback automático que falhou; o 3 e o 4 deixam o semáforo preso para o `/deploy rollback`; 6 rollback feito, com semáforo solto: revert, issue reaberta e notificação, como diz o Passo 10; 7 migration vencida, sem semáforo nem merge: notificação e o rabo de novo depois da colagem).

### Falha em Passo 11 (Resumo final / Discord)

- Não bloqueia. Reportar warning.

---

## Regras

- ❌ **Nunca** `git push --force` à main. Apenas `--force-with-lease` na branch própria pra amend.
- ❌ **Nunca** mergear, fazer bump ou mexer em `APP_VERSION` pelo `/ship`: é tudo do rabo (`fechar_onda.py`).
- ❌ **Nunca** pular o Gate 2 (`hr-revisor-seguranca`) quando o `sensivel.py` acusa rota sem login ou migration (canal público da Ouvidoria, webhook, e-mail recebido, `supabase/migrations/`).
- ❌ **Nunca** rodar `/ship` em uma branch que já tem PR aberto sem `--resume` ou flag explícita.
- ❌ **Nunca** logar token/secret em qualquer output.
- ✅ Conventional commits sempre.
- ✅ Toda mudança nasce de uma Issue (ou, na falta, descreve a mudança no corpo do PR). Sem chronicle nem plano.
- ✅ Discord notificação SÓ no final, com resultado verdadeiro.

---

## Anti-padrões

- ❌ "Vou abrir o PR no browser pra editar a descrição mais bonita." — Não. Template + Issue dão estrutura suficiente. Edição livre depois do `/ship` se quiser.
- ❌ "Vou rodar `/code-review` separado depois do merge." — Não. Review é gate ANTES do merge.
- ❌ "Vou squash 3 commits em 1 antes de pushear.": sim, pode. Mas use `git rebase -i` cauteloso. O merge é do rabo, pela API do GitHub.
- ❌ "Vou commitar com `git commit -am` pra agilizar." — Não. Lista explícita de arquivos.

---

## Referências

- `.github/PULL_REQUEST_TEMPLATE.md`: template do PR.
- `references/discord.md`: Passo 12 completo (fontes da webhook URL e payload).
- `https://cli.github.com/manual/` — manual do gh CLI.
- `.claude/skills/onda-enxuta/scripts/fechar_onda.py`: o rabo que o Passo 10 roda.
