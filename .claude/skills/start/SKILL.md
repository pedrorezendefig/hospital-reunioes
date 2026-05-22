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
/start --sem-plano            # emergência: pula as 3 frases mínimas do Modo B (cria plano com plan_source: skipped)

# Modos especiais com Superpowers
/start --rigoroso             # força brainstorming + writing-plans MESMO com working tree com diff
/start --rapido               # pula brainstorming mesmo com working tree limpo (vai direto)
/start debug                  # invoca systematic-debugging (Superpowers) em vez de brainstorming
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
4. **Detectar plano ativo da branch atual** (fonte primária pra retomada — Eixo A do plano de enxugamento):
   ```bash
   # Procura plano em docs/planejamento/em-andamento/ cujo frontmatter `branch:` bate
   CURRENT_PLAN=""
   for f in docs/planejamento/em-andamento/*.md; do
     [ -f "$f" ] || continue
     if grep -qE "^branch:\s*$BRANCH$" "$f"; then
       CURRENT_PLAN="$f"
       break
     fi
   done

   # Fallback (legacy): procura chronicle 🟡 cujo frontmatter `branch:` bate
   CURRENT_CHRONICLE=""
   for f in docs/spec/chronicles/🟡-*.md; do
     [ -f "$f" ] || continue
     if grep -qE "^branch:\s*$BRANCH$" "$f"; then
       CURRENT_CHRONICLE="$f"
       break
     fi
   done
   ```

5. **Classificar o estado**:
   - **A. Working tree limpo + sem plano/chronicle da branch** → modo `dialogo` (provavelmente nova feature).
   - **B. Mudanças no working tree** → modo `from-diff`.
   - **C. Branch já é feature branch** (`fix/...`, `feature/...` etc., não `main`) → modo `continuar`.
   - **D. Existe plano em `docs/planejamento/em-andamento/` (preferido) OU chronicle 🟡 (legacy) da branch atual** → modo `retomar`.

---

## Modo A — Diálogo (working tree limpo, sem chronicle ativo)

Você abriu o Claude Code, nada modificado, digitou `/start`. A skill assume que você quer começar do zero.

### Fluxo

1. **Pergunta aberta**:
   > "Beleza, tá tudo limpo. O que vamos fazer agora?"

2. **Decidir caminho de planejamento**:
   - **Default**: invocar a skill `superpowers:brainstorming` automaticamente. Ela dialoga 1-1 com o usuário, propõe 2-3 abordagens, fecha um design. Logo depois, `superpowers:writing-plans` gera a seção "Plano" (com checkboxes) do chronicle 🟡.
   - **`/start --rapido`**: pula brainstorming. Pergunta direto categoria/issue e cria chronicle 🟡 com plano vazio pro dev preencher.
   - **`/start debug`**: invoca `superpowers:systematic-debugging` em vez de brainstorming — pro caso de bug feio que precisa investigação raiz antes de propor fix.
   - Se o usuário prefere plan mode nativo: pode sugerir saída do `/start` + `Shift+Tab+Tab` + voltar. Mas o default novo é Superpowers in-line.

3. **Categorizar** (uma pergunta):
   > "É (a) bug · (b) feature · (c) refactor · (d) docs · (e) chore?"

4. **Issue?** (uma pergunta):
   > "Já tem Issue pra essa mudança? Manda o número, ou diz 'criar' que eu abro uma agora, ou 'sem issue' pra seguir sem."
   - Se "criar" → invocar skill `/issue` em modo `new` e voltar.
   - Se número → validar com `gh issue view <N>` e seguir.
   - Se "sem issue" → seguir.

5. **Branch + plano (em `docs/planejamento/em-andamento/`)**:
   - Gerar slug do título.
   - Criar branch `<type>/<slug>[-<issue>]`.
   - **Criar plano detalhado em `docs/planejamento/em-andamento/<YYYY-MM-DD-HHMM>-<slug>.md`** seguindo schema documentado em `docs/planejamento/README.md` (frontmatter + 8 seções: Visão, Contexto técnico, Arquitetura, Tarefas, Estado, Decisões, Comandos retomada, Histórico).
   - **Origem do conteúdo do plano** (em ordem de preferência):
     1. Output de `superpowers:writing-plans` (após brainstorming) — expandido pra schema completo.
     2. Conteúdo de `~/.claude/plans/<X>.md` (se usuário veio do plan mode nativo) — copiado e expandido.
     3. Plano vazio com seções pré-preenchidas só com placeholders (pro usuário editar à mão).
   - **NÃO criar chronicle 🟡 aqui** — chronicle é responsabilidade do `/ship` Passo 3 quando o trabalho terminar. Plano em `docs/planejamento/` é o que o dev edita ao longo do trabalho.
   - **PAUSAR** pro usuário ajustar plano + escrever código.

6. **Quando usuário retoma**:
   - Detectar que código foi escrito (diff aparece).
   - Encadear `/ship --from-diff` com tipo + issue + descrição inferidos. O `/ship` lerá o plano em `docs/planejamento/em-andamento/` pra reaproveitar contexto.

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
   > "Vou criar branch `<nome>`, mover essas mudanças pra lá, criar plano em `docs/planejamento/em-andamento/<slug>.md` (com seções inferidas do diff + 3 frases que vou te perguntar), e encadear /ship pra ir até produção. Tipo: **<type>**. Issue: <#N ou nenhuma>. Confirma? (a) Sim · (b) Ajustar tipo/título · (c) Cancelar"

6. **Quando confirma**:
   ```bash
   # Se na main: criar branch nova
   if [ "$BRANCH" = "main" ]; then
     git checkout -b "$NEW_BRANCH"
   fi
   # Se já em feature branch: usar a atual

   # Criar plano em docs/planejamento/em-andamento/ (PRÉ-condição pra /ship --from-diff)
   # Schema completo em docs/planejamento/README.md.
   # §2 Contexto técnico vem inferido do diff (paths, áreas, padrão de mudança).
   # §1 Visão / §5 Estado / §6 Decisões vêm das 3 frases que pergunto a seguir (Corte 3).
   ```

7. **Coletar 3 frases curtas pro plano** (Corte 3 do plano de enxugamento — substitui a opção antiga "Pula"):
   - "Em 1 linha, por quê essa mudança importa? (Visão)"
   - "Em 1 linha, como testar que funciona depois? (Critério de aceite)"
   - "Em 1 linha, o que pode quebrar e como reverter? (Riscos/rollback)"

   Se dev pular tudo com input vazio 3x consecutivo: criar plano com `plan_source: skipped` no frontmatter + adicionar nota visível "Plano vazio por escolha do dev". Log explícito no PR.

8. **Persistir plano e encadear /ship**:
   ```bash
   # Salva docs/planejamento/em-andamento/<YYYY-MM-DD-HHMM>-<slug>.md
   # com frontmatter completo + §1 (Visão) + §2 (Contexto inferido) + §4 (Tarefas com 1 entry inferida)
   # + §5 (Estado: "fase inicial, código já escrito") + §6 (3 frases) + §7 (comandos retomada)

   # Encadear /ship com flag --from-diff
   # (o /ship cria o chronicle 🟡 com referência ao plano no frontmatter)
   /ship "$TITLE" --type "$TYPE" $ISSUE_FLAG --from-diff
   ```

9. `--from-diff` faz com que `/ship` **pule a pausa** do Passo 4 (esperar código). Vai direto pro Passo 5 (commit + push + PR + review + merge + deploy). O chronicle 🟡 que `/ship` cria referencia o plano em `docs/planejamento/em-andamento/`.

### Flag de emergência: `--sem-plano`

Hotfix crítico onde até as 3 frases atrapalham? `/start --sem-plano "<descrição>"` pula o passo 7 inteiro. Cria plano com `plan_source: skipped` + log no PR alertando. Default permanece exigir as 3 frases — pular requer flag explícita.

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

## Modo D — Retomar (plano em `docs/planejamento/em-andamento/` ativo, nova sessão Claude)

Você abriu o Claude Code num terminal novo (a sessão anterior fechou ou estourou contexto). A branch é uma feature branch. Existe um plano em `docs/planejamento/em-andamento/<slug>.md` (preferido) OU um chronicle 🟡 (legacy) cujo `branch:` no frontmatter bate com `git branch --show-current`. Esse é o caminho **canônico de continuidade entre sessões**.

### Fluxo (caminho preferido — plano em `docs/planejamento/`)

1. **Ler o plano** identificado no Bootstrap (`$CURRENT_PLAN`).

2. **Extrair estado atual do plano**:
   - Frontmatter: `fase_atual`, `tarefas_concluidas`/`tarefas_total`, `sha_atual`, `chronicle`, `pr`.
   - §5 (Estado de execução): "Já feito", "Em andamento", "Próximo passo", "Bloqueios atuais". Snapshot, não histórico.
   - §7 (Comandos pra retomada): bash exato que valida o estado atual.

3. **Executar §7 (Comandos pra retomada)** antes de mostrar o resumo:
   ```bash
   # Roda os comandos que o plano definiu pra "se situar em <5min".
   # Tipicamente: branch certa, commits WIP feitos, testes verdes até o último checkpoint.
   # Captura output pra mostrar status real (não confiar só no que o plano DIZ).
   ```

4. **Mostrar resumo pro usuário**:

   ```
   ═══ Trabalho em progresso detectado ═══

   Plano: docs/planejamento/em-andamento/<slug>.md
   Branch: <nome> · PR: #<N ou —> · Chronicle: <path ou ainda não criado>
   Fase atual: <fase_atual do frontmatter>
   Progresso: <tarefas_concluidas>/<tarefas_total> tarefas

   ✅ Já feito (do §5):
     ✓ <linha do "Já feito" #1>
     ✓ <linha do "Já feito" #2>

   ⏳ Em andamento:
     → <linha do "Em andamento">

   📋 Próximo passo:
     <linha do "Próximo passo" — 1 frase exata>

   🩺 Validação dos comandos do §7:
     <output dos comandos>

   Opções:
   (a) Continuar daqui
   (b) Abrir plano completo pra revisar
   (c) Reajustar plano antes
   (d) Abandonar (deleta o plano de em-andamento/ — falha vive no chronicle 🔴 + history.json)
   ```

5. **Aguardar input**.

6. **Continuar trabalhando (escolha "a")**:
   - Seguir o "Próximo passo" descrito em §5 do plano.
   - A cada commit/checkpoint, reescrever §5 do plano (sempre snapshot, nunca append) e atualizar `sha_atual`, `fase_atual`, `tarefas_concluidas` no frontmatter.
   - Mini-commits WIP a cada checkbox concluída: `git commit -m "wip(<slug>): tarefa N — <descricao>"`. Squash final pelo `/ship`.

### Fluxo (fallback legacy — só chronicle 🟡, sem plano)

Se `$CURRENT_PLAN == ""` mas `$CURRENT_CHRONICLE != ""`:

1. Ler chronicle 🟡 da branch.
2. Contar progresso na seção "Plano" do chronicle: `DONE=$(grep -cE "^- \[x\]" "$CURRENT_CHRONICLE")` etc.
3. Mostrar resumo enxuto (versão antiga deste fluxo, preservada como compat).
4. Oferecer **migrar o chronicle pra `docs/planejamento/em-andamento/`** automaticamente (criar arquivo expandido a partir do chronicle, manter chronicle como índice).

### Quando NÃO ativar o Modo D

- Working tree tem diff sem commit (Modo B vence — diff é mais importante que plano existente).
- Plano tem `date_last_touched` há mais de 14 dias (oferecer descartar ou retomar mesmo assim).
- Branch atual é `main` (a skill aborta — não tem como retomar planejamento na main).
- Plano tem `status: finalizado` (já foi resolvido — está em `finalizado/`, fora do bootstrap do Modo D). Planos abandonados não existem em disco (foram deletados).

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
| **plan mode (nativo)** | Antes de `/start`, pra discutir abordagem. Não é skill, é feature do Claude Code. Sai com `Shift+Tab+Tab`. |
| **`superpowers:brainstorming`** | Default no Modo A — invoca antes de criar chronicle. Substitui o sugestão antiga de plan mode. |
| **`superpowers:writing-plans`** | Logo após brainstorming — gera seção "Plano" com checkboxes no chronicle 🟡. |
| **`superpowers:executing-plans`** | No Modo D — lê chronicle 🟡 da branch e retoma de onde parou. |
| **`superpowers:systematic-debugging`** | `/start debug` — investigação raiz antes de propor fix. |
| **`superpowers:verification-before-completion`** | Implícito antes de invocar `/ship`. |
| **`/issue`** | Sub-componente: criar Issue conversacional. Chamada por `/start` se "sem issue" e usuário escolhe criar. |
| **`/ship`** | Subskill principal. `/start` encadeia `/ship --from-diff` (modo B) ou `/ship` clássico (modo A após pausa). |
| **`/deploy ship`** | Chamada por `/ship`, não diretamente por `/start`. |
| **`/snapshot`** | Chamada por `/deploy ship` pós-health. `/start` não invoca diretamente. |

A árvore de aninhamento fica:

```
/start
├─ brainstorming (Superpowers) — modo A default
├─ writing-plans (Superpowers) — pós brainstorming
├─ executing-plans (Superpowers) — modo D
├─ systematic-debugging (Superpowers) — /start debug
└─ /ship (+--from-diff)
   ├─ Camada 1: /code-review
   ├─ Camada 2: /security-review
   ├─ Camada 3: requesting-code-review (Superpowers)
   ├─ Camada 4: CI Actions
   ├─ Camada 5: verification-before-completion (Superpowers)
   └─ /deploy ship
      ├─ MCP Coolify
      └─ /snapshot (pós-health)
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
