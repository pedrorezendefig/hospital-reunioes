---
name: start
description: Skill de entrada única do time. Detecta o contexto atual (working tree, branch, mudanças staged ou unstaged) e inicia o ciclo "branch → chronicle 🟡 → commit → PR → review → merge → deploy" de forma inteligente. Substitui `/issue trabalhar` e a invocação manual de `/ship`. Use SEMPRE que o usuário disser "start", "/start", "começa", "vamos subir isso", "tô pronto pra mergear", "encerra esse trabalho", "shippa", "manda pra prod", "encerra a sessão de código", "fecha esse loop", ou descrever que tem mudanças prontas em working tree pra virar PR. Se o usuário ainda NÃO codou nada (working tree limpo), a skill abre um diálogo curto sobre o que vai mudar e recomenda usar o **modo plano nativo do Claude Code** (Shift+Tab+Tab ou `claude --plan`) pra refinar a abordagem antes de invocar /start de novo. Se o usuário JÁ codou (diff existe), a skill pula a fase de planejamento, infere tipo/área/escopo a partir do diff, propõe branch + chronicle + commit message, e encadeia /ship --from-diff pra automatizar o resto. Pensada como entry point único que o time iniciante decora — em vez de lembrar /issue + /ship + /deploy, só lembra /start.
---

# start — entry point único do workflow

Uma skill, uma palavra, todo o ciclo. O time (Pedro + 2 contratados) usa essa skill quando quer transformar **qualquer estado atual do projeto** numa entrega em produção.

## Princípio

`/start` não tenta substituir o planejamento — ele entra **depois** que você já sabe o que vai fazer (ou já fez). O planejamento mora em **dois lugares**:

1. **Modo plano nativo do Claude Code** (Shift+Tab+Tab no Claude Code, ou `claude --plan` no terminal) — pra discutir abordagem com o assistant, ler código relevante, refinar a ideia.
2. **Chronicle 🟡** em `docs/spec/chronicles/` — registro persistente do plano que sobrevive a branch, fica versionado em git.

`/start` ponteia entre os dois e leva a mudança até produção.

---

## Sintaxe

```bash
/start                        # detecta contexto automaticamente
/start "descrição curta"      # passa hint da intenção (vira título do PR)
/start --issue <N>            # liga a uma Issue existente (closes #N no PR)
/start --type <t>             # força tipo: fix | feature | chore | refactor | docs | spec
/start --no-deploy            # tudo menos /deploy ship (PR aberto, mergeado, mas sem subir)
/start --no-merge             # abre PR mas não mergeia (deixa review humana acontecer)
/start --draft                # PR como draft (não mergeable até promover)
```

Mais flags são herdadas de `/ship` (essa skill encadeia /ship). Ver `.claude/skills/ship/SKILL.md` se precisar.

---

## Bootstrap (toda invocação)

1. **Detectar repo**: `git -C "$PWD" rev-parse --show-toplevel`. Se não em repo → erro educativo.
2. **Validar `gh` CLI**: `gh auth status`. Se não autenticado → instruir `gh auth login`.
3. **Capturar contexto**:
   ```bash
   BRANCH=$(git branch --show-current)
   DIFF_SUMMARY=$(git diff --stat HEAD)          # tudo (staged + unstaged)
   UNTRACKED=$(git ls-files --others --exclude-standard)
   STAGED_COUNT=$(git diff --cached --stat | tail -1)
   ```
4. **Classificar o estado**:
   - **A. Working tree limpo** (sem diff, sem untracked) → modo `dialogo`.
   - **B. Mudanças no working tree** → modo `from-diff`.
   - **C. Branch já é uma feature branch** (`fix/...`, `feature/...` etc., não `main`) → modo `continuar`.

---

## Modo A — Diálogo (working tree limpo)

Você abriu o Claude Code, nada modificado, digitou `/start`. A skill assume que você quer começar do zero.

### Fluxo

1. **Pergunta aberta**:
   > "Beleza, tá tudo limpo. O que vamos fazer agora?"

2. **Recomendar plan mode (se a tarefa parece complexa)**:
   - Se o usuário descreve algo vago ou tem 3+ subitens → sugerir:
     > "Isso parece que merece um plano detalhado antes. Recomendo usar o **modo plano do Claude Code** primeiro — você sai do /start, faz `Shift+Tab+Tab` (ou abre `claude --plan`), conversa comigo sobre a abordagem (eu leio o código, proponho passos), aprovamos o plano juntos. Depois volta aqui e digita `/start` que eu pego daqui."
   - Se a tarefa é objetiva (1 arquivo, 1 mudança óbvia) → segue sem plan mode.

3. **Categorizar** (uma pergunta):
   > "É (a) bug · (b) feature · (c) refactor · (d) docs · (e) chore?"

4. **Issue?** (uma pergunta):
   > "Já tem Issue pra essa mudança? Manda o número, ou diz 'criar' que eu abro uma agora, ou 'sem issue' pra seguir sem."
   - Se "criar" → invocar skill `/issue` em modo `new` e voltar.
   - Se número → validar com `gh issue view <N>` e seguir.
   - Se "sem issue" → seguir.

5. **Branch + chronicle 🟡**:
   - Gerar slug do título.
   - Criar branch `<type>/<slug>[-<issue>]`.
   - Criar chronicle 🟡 com plano detalhado.
   - **PAUSAR** pro usuário editar plano + escrever código.

6. **Quando usuário retoma**:
   - Detectar que código foi escrito (diff aparece).
   - Encadear `/ship --from-diff` com tipo + issue + descrição inferidos.

---

## Modo B — From Diff (working tree com mudanças)

Você já escreveu código (talvez via plan mode). Digitou `/start`. A skill pega o diff e leva direto pra produção, sem nova pausa.

### Fluxo

1. **Mostrar resumo do diff**:
   ```
   ═══ Contexto detectado ═══
   Branch atual:    main
   Arquivos:        4 modificados, 1 novo
     M  hospital-reunioes/backend/app/routers/health.py
     M  hospital-reunioes/backend/app/main.py
     M  hospital-reunioes/backend/app/config.py
     M  hospital-reunioes/backend/app/dependencies.py
     A  hospital-reunioes/supabase/migrations/038_fk_indexes.sql

   Linhas:          +127 / -34
   ```

2. **Inferir tipo e área** (via `commit_inference.scope_map` em `docs/spec/deploy/project.json`):
   - `hospital-reunioes/backend/**` → `area:backend`
   - `hospital-reunioes/supabase/migrations/**` → `area:supabase`
   - Tipo inferido pela natureza do diff (linhas removidas + adicionadas ≈ refactor; só adicionadas ≈ feature; comentários "fix"/"bug" → fix). Se ambíguo, perguntar.

3. **Gerar título sugerido**:
   - Se `/start "..."` passou descrição → usa como título.
   - Senão, infere do diff: olha primeiro arquivo modificado e função/componente.
   - Truncar em 60 chars.

4. **Sugerir branch nome**:
   ```
   Branch: fix/pre-deploy-checklist-cors-fk-indexes
   ```

5. **Confirmar com usuário** (uma pergunta):
   > "Vou criar branch `<nome>`, mover essas mudanças pra lá, criar chronicle 🟡 com plano inferido, e encadear /ship pra ir até produção. Tipo: **<type>**. Issue: <#N ou nenhuma>. Confirma? (a) Sim · (b) Ajustar tipo/título · (c) Cancelar"

6. **Quando confirma**:
   ```bash
   # Se na main: criar branch nova
   if [ "$BRANCH" = "main" ]; then
     git checkout -b "$NEW_BRANCH"
   fi
   # Se já em feature branch: usar a atual

   # Gerar chronicle 🟡 inferido do diff
   /spec  # cria chronicle com plano pré-preenchido pelo diff

   # Encadear /ship com flag --from-diff
   /ship "$TITLE" --type "$TYPE" $ISSUE_FLAG --from-diff
   ```

7. `--from-diff` faz com que `/ship` **pule a pausa** dos Passos 3-4 (criar chronicle + esperar código). Vai direto pra Passo 5 (commit + push + PR + review + merge + deploy).

---

## Modo C — Continuar (feature branch existente)

Você tá no meio de uma mudança, branch criada (`fix/...`), commits parciais, novos diffs. Digitou `/start`.

### Fluxo

1. **Detectar estado**:
   ```bash
   git log main..HEAD --oneline  # commits da branch
   git diff --stat               # mudanças pendentes
   gh pr view --json url,state 2>/dev/null  # PR já aberto?
   ```

2. **Cenário 1: branch sem PR**:
   > "Branch `<nome>` tem N commits + M mudanças pendentes. Quer (a) commitar o resto e abrir PR agora · (b) continuar codando · (c) abandonar (voltar pra main, sem perder o trabalho)?"

3. **Cenário 2: PR aberto, mas mais código novo**:
   > "PR #<N> já aberto. Quer (a) commitar essas novas mudanças e push (atualiza PR) · (b) abandonar mudanças novas?"

4. Encadeia `/ship --resume` ou `/ship --from-diff` conforme escolha.

---

## Inferência de chronicle 🟡 a partir do diff

Quando entra no modo B (from-diff), a skill gera um chronicle 🟡 **pré-preenchido** com:

```markdown
---
title: <type>(<scope>): <título inferido ou passado>
author: <git config user.name> <email>
type: <type>
issue: <issue ou null>
pr: null
date_planned: <ISO-8601>
date_deployed: null
sha: null
branch: <branch>
result: pending
---

## Plano

### Escopo (inferido do diff)

Arquivos alterados:
- `caminho/arquivo1.py` (+N -M)
- `caminho/arquivo2.tsx` (+N -M)
- `caminho/migrations/038_xxx.sql` (novo)

Áreas tocadas: <area1>, <area2>

### Por que (a preencher)

[seção a editar manualmente — porque o diff não diz a motivação]

### Como testar

[seção a editar manualmente]

### Riscos e rollback

[seção a editar manualmente]

## Execução / Resultados

_(preenchido automaticamente pelo /ship + /deploy)_
```

A skill **mostra o chronicle gerado** e pergunta:
> "Chronicle 🟡 criado em `docs/spec/chronicles/🟡-...md`. Faltam 3 seções pra você preencher (Por quê / Como testar / Riscos). Edita agora? (a) Sim, espero · (b) Pula, vamos direto pro commit (não recomendado pra produção)."

---

## Anti-padrões

- ❌ "Vou inferir o 'por quê' do diff." — Não. Por quê exige contexto humano. Sempre peça.
- ❌ "Vou commitar tudo do working tree sem perguntar." — Não. Mostre o diff e confirme.
- ❌ "Plan mode é overkill, pula." — Não. Pra mudanças complexas (3+ arquivos, lógica nova), plan mode reduz retrabalho dramaticamente.
- ❌ "Vou abrir o PR no browser pra editar título." — Não. `/start` faz tudo via gh CLI.

---

## Relação com outras skills

| Skill | Quando entra |
|---|---|
| **plan mode (nativo)** | Antes de `/start`, pra discutir abordagem. Não é skill, é feature do Claude Code. |
| **`/issue`** | Sub-componente: criar Issue conversacional. Chamada por `/start` se "sem issue" e usuário escolhe criar. |
| **`/ship`** | Subskill principal. `/start` encadeia `/ship --from-diff` (modo B) ou `/ship` clássico (modo A após pausa). |
| **`/deploy ship`** | Chamada por `/ship`, não diretamente por `/start`. |
| **`/spec`** | Chamada por `/ship`/`/deploy` ao final, não diretamente. |

A árvore de aninhamento fica:

```
/start
└─ /ship (+--from-diff)
   ├─ /code-review
   ├─ /security-review
   └─ /deploy ship
      ├─ MCP Coolify
      └─ /spec update
         └─ 9 agents REVERSA (scout, archaeologist, detective, ...)
```

---

## Exemplos

### Exemplo 1 — From diff (caso comum no dia-a-dia)

```
[Pedro acabou de codar em plan mode, ajustou CORS + adicionou índices FK]

› /start

Skill: ═══ Contexto detectado ═══
       Branch: main
       Arquivos: 5 modificados, 1 novo
       Áreas: area:backend, area:supabase
       Tipo inferido: chore (manutenção pre-deploy)

       Vou criar branch fix/pre-deploy-checklist-cors-fk-indexes
       e mover essas mudanças pra lá. Encadear /ship pra ir até prod.
       Confirma? (a) Sim (b) Ajustar (c) Cancelar

› a

Skill: ✓ Branch criada
       ✓ Chronicle 🟡 gerado com plano inferido
       → Faltam 3 seções pra editar (Por quê / Como testar / Riscos).
       Edita agora? (a) Sim, espero (b) Pula

› a

[Pedro edita o chronicle no VS Code, volta]

› continuar

Skill: → Encadeando /ship --from-diff
       [/ship roda: commit + push + PR + review + merge + deploy]
       ✓ Deploy 890b149 saudável em 4m07s
```

### Exemplo 2 — Diálogo (working tree limpo)

```
› /start

Skill: Beleza, tá tudo limpo. O que vamos fazer agora?

› quero corrigir um bug no webhook clicksign

Skill: Isso parece objetivo. Vou seguir direto. Tipo: bug (fix). Tem Issue?

› não, cria

Skill: → Encadeando /issue new pra criar Issue ...
       [diálogo do /issue acontece, Issue #68 criada]
       Voltando pro /start.

       ✓ Issue #68 criada
       ✓ Branch fix/webhook-clicksign-error-68 criada
       ✓ Chronicle 🟡 criado em docs/spec/chronicles/...
       Edita o plano + escreve o código. Quando terminar, digita "continuar".

[Pedro codifica + edita chronicle]

› continuar

Skill: → Encadeando /ship --from-diff
       [resto do ciclo]
```

### Exemplo 3 — Continuar (feature branch com PR já aberto)

```
[Pedro tá na branch fix/webhook-X-67, PR já aberto, escreveu mais código]

› /start

Skill: PR #42 já aberto pra essa branch. Tem 18 novas linhas no working tree
       que ainda não commitei. Quer:
       (a) Commitar e fazer push (atualiza PR)
       (b) Descartar essas novas mudanças

› a

Skill: → Encadeando /ship --resume
       [commit + push, PR atualizado]
       ✓ PR #42 atualizado. CI rodando...
```

---

## Falhas e recuperação

| Cenário | Ação |
|---|---|
| `gh` não autenticado | Erro educativo, sugere `gh auth login`, para. |
| Working tree com mudanças mas branch errada (ex: `pedroribbe-experimental`) | Pergunta se deseja mover mudanças pra branch nova de feature. |
| Diff toca arquivos `hard_excluded` (`.env`, `*.key`) | Aborta com erro claro. Esses arquivos nunca vão pra git. |
| /ship falha em algum passo | A skill /start não tenta retomar. Reporta erro e instrui rodar `/ship --resume` manualmente. |
| Mid-flow Ctrl+C do usuário | Estado preservado (branch, chronicle 🟡 ficam). Próximo /start detecta modo C e oferece retomar. |

---

## Por que `/start` em vez de `/issue` ou `/ship` direto

Time iniciante decora **1 palavra**. Não precisa lembrar:
- Quando usar `/issue` vs `/ship`
- Se o /issue trabalhar liga no /ship ou não
- Se precisa criar branch antes
- Se precisa criar Issue antes

A skill faz a triagem automaticamente. Se você tem código pronto, vai direto. Se não, conversa. Se tem Issue, usa. Se não tem, oferece criar. Se tá em branch errada, ajusta.

Resultado: a fricção mental de "qual comando uso agora?" some.
