---
slug: planejamento-subpastas-skill
title: "Planejamentos versionados em docs/planejamento/ com subpastas, header de progresso e auto-import do plan mode"
status: ativo
plan_source: plan-mode-claude
author: "Pedro Rezende <pmrdef@gmail.com>"
date_created: "2026-05-23T18:06:55-03:00"
date_last_touched: "2026-05-23T18:25:00-03:00"
branch: feat/planejamento-subpastas-skill
chronicle: null
pr: 17
sha_inicio: cfdce2a
sha_atual: 7e4ef47
estimativa_horas: 3
fase_atual: "PR #17 enriquecido com onboarding completo, aguardando review + merge"
fase_numero: 8
fases_total: 8
tarefas_total: 8
tarefas_concluidas: 8
imported_from: /Users/pedrorezende/.claude/plans/image-1-enquanto-estou-rustling-flute.md
---

> ## Progresso: 100%
> **Fase 8 de 8** — PR #17 enriquecido com onboarding completo, aguardando review + merge
> **8 de 8 tarefas** concluídas
> **Última atualização:** 2026-05-23 18:25 · SHA `7e4ef47`
> **Branch:** `feat/planejamento-subpastas-skill` → PR [#17](https://github.com/pedrorezendefig/hospital-reunioes/pull/17)

## 4. Tarefas

- [x] 4.1 Fase 1 — Estrutura de pastas + migração (3 subpastas em `em-andamento/` + `finalizado/`, `git mv` do plano existente pra `manual/`)
  - Critério: `ls docs/planejamento/em-andamento/{plan-mode,superpowers,manual}/.gitkeep` retorna OK
- [x] 4.2 Fase 2 — Skill `/planejamento` + 2 helpers (`recalc_progress.sh` + `import_planmode.sh`)
  - Critério: `bash .claude/skills/planejamento/scripts/recalc_progress.sh --help` mostra help
- [x] 4.3 Fase 3 — README de planejamento reescrito (nova estrutura + schema do header + skill `/planejamento`)
  - Critério: `grep -c "^## " docs/planejamento/README.md` retorna ≥ 6
- [x] 4.4 Fase 4 — Plumbing em `/start`, `/ship`, `/deploy` + override no `CLAUDE.md`
  - Critério: `grep -l 'em-andamento/\*/' .claude/skills/{start,ship,deploy}/SKILL.md` retorna os 3
- [x] 4.5 Fase 5 — Hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json`
  - Critério: `jq '.hooks.PostToolUse[] | select(.matcher == "ExitPlanMode")' ~/.claude/settings.json` retorna o objeto
- [x] 4.6 Fase 6 — Dogfooding: importar este plano via `/planejamento importar` + ajustar slug + recalcular header
  - Critério: `ls docs/planejamento/em-andamento/plan-mode/2026-05-23-1806-planejamento-subpastas-skill.md` existe
- [x] 4.7 Fase 7 — Commit incremental + abrir PR via `gh` CLI (1 PR único)
  - Critério: `gh pr view 17 --json state | jq -r .state` retorna `OPEN`
- [x] 4.8 Fase 8 — Enriquecer onboarding com setup completo do Claude Code pro time (claude-setup.md + atualizar dev.md + CLAUDE.md + README de planejamento aponta pro guia)
  - Critério: `ls docs/onboarding/claude-setup.md && grep -q "claude-setup.md" docs/onboarding/dev.md CLAUDE.md` retorna OK

# Plano — Planejamentos versionados em `docs/planejamento/` com subpastas por origem, header de progresso bem chuta e auto-importação do plan mode

## Contexto

Hoje os planejamentos do projeto Hospital vivem em **3 lugares distintos**:

1. `~/.claude/plans/*.md` — saída do plan mode nativo do Claude Code (`Shift+Tab+Tab`). Fora do repo, descartável, sem schema padronizado. O caso atual: `~/.claude/plans/image-1-eu-preciso-tranquil-seal.md` (PR1 hotfix + PR2 signatários card) está aí, mas **nunca foi importado** pro repo. Próxima sessão Claude perde esse contexto se não souber procurar nessa pasta.
2. `docs/spec/chronicles/{🟡,🟢,🔴}-*.md` — diário curto pós-PR (1 chronicle por commit/PR). Cobre "o que mergeou", não "qual é o plano em curso".
3. `docs/planejamento/{em-andamento,finalizado}/*.md` — **infra já existe** (criada no PR #12), com schema rico (frontmatter de 15 campos + 8 seções) e `/start` + `/ship` + `/deploy` já integrados. Mas: (a) está **vazia em `em-andamento/`** porque nunca dispara automaticamente quando você sai do plan mode; (b) **não distingue origem** (Superpowers vs plan-mode vs manual) — tudo iria na mesma pasta; (c) o campo `fase_atual` está no frontmatter mas **não tem header visual chuta** no topo do arquivo (você precisa abrir e ler YAML pra saber "Fase 2 de 5 - 40%").

**Objetivo deste plano:** fechar essas 3 lacunas pra que abrir qualquer plano em `docs/planejamento/em-andamento/` mostre, na primeira tela, "**Progresso: 40% · Fase 2 de 5 · 6 de 15 tarefas · atualizado 19:45 · branch X · PR #15**" sem precisar parsear nada — e que o plano do plan mode chegue lá automaticamente sem você lembrar de copiar à mão. Resultado: começar uma sessão Claude nova no mesmo terminal vira "lê 1 arquivo, sabe exatamente onde parou e o quê fazer a seguir".

---

## 1. Solução em 5 partes

### Parte A — Reorganização de pastas por origem

```
docs/planejamento/
├── README.md                          (atualizado)
├── em-andamento/
│   ├── plan-mode/                     ← NOVO. Planos do Shift+Tab+Tab (importados via hook)
│   │   └── .gitkeep
│   ├── superpowers/                   ← NOVO. Output de superpowers:writing-plans
│   │   └── .gitkeep
│   └── manual/                        ← NOVO. Você escreve à mão no VS Code
│       └── .gitkeep
└── finalizado/
    ├── plan-mode/.gitkeep
    ├── superpowers/.gitkeep
    └── manual/
        └── 2026-05-22-1714-planejamento-estrutura.md   (migrado do raiz)
```

Migração do plano existente preserva blame via `git mv`.

### Parte B — Header de progresso (bloco padronizado, logo após frontmatter)

Schema obrigatório em todo plano. Reescrito por `/planejamento progresso` (e por `/ship`/`/deploy` nos checkpoints automáticos):

```markdown
---
slug: clicksign-signatarios-card
status: ativo
fase_atual: "PR2 — implementando SignatariosCard.tsx"
tarefas_total: 15
tarefas_concluidas: 6
fases_total: 3
fase_numero: 2
sha_atual: f99c81d
branch: feat/clicksign-signatarios-status
pr: 15
date_last_touched: 2026-05-22T19:45:00Z
---

## 1. Visão
...
```

Algoritmo: % = `round(tarefas_concluidas / tarefas_total * 100)`. Quando frontmatter desincroniza dos checkboxes do body (caso comum: dev marca `[x]` no VS Code sem atualizar frontmatter), o script **recalcula a partir dos checkboxes** e atualiza o frontmatter junto. Frontmatter vira derivado, body é fonte da verdade.

**Novos campos no frontmatter** (aditivos, retrocompatíveis):
- `fases_total: <int>` — quantas fases o plano tem no total (ex: 3 PRs sequenciais = 3 fases). Default 1.
- `fase_numero: <int>` — número da fase em curso. Default 1.

Planos existentes sem esses campos: `/planejamento progresso` deduz `fase_numero=1, fases_total=1` e popula automaticamente.

### Parte C — Skill nova `/planejamento` (4 subcomandos)

Localização: `.claude/skills/planejamento/SKILL.md` (versionada no repo).

| Subcomando | O que faz |
|---|---|
| `/planejamento progresso [--file <path>]` | Recalcula header do plano atual (default: o único em `em-andamento/<*>/`; se >1, lista). Conta `[x]` vs `[ ]` no body, atualiza header + frontmatter (`tarefas_concluidas`, `date_last_touched`). Idempotente. |
| `/planejamento importar [--source <path>] [--type plan-mode\|superpowers]` | Importa plano externo. Default `--source`: arquivo mais recente em `~/.claude/plans/`. Adiciona frontmatter mínimo, header de progresso vazio, salva em `em-andamento/<type>/<YYYY-MM-DD-HHMM>-<slug>.md`. Slug derivado da H1 ou nome do arquivo. **Não commita** — deixa staged. |
| `/planejamento status` | Lista todos os planos em `em-andamento/<*>/` com nome curto + progresso. Visão "qual trabalho tá aberto pra mim". Útil pra retomar entre sessões. |
| `/planejamento finalizar [--abort]` | Default: move plano da branch atual de `em-andamento/<source>/` pra `finalizado/<source>/`, atualiza `status: finalizado` no frontmatter. `--abort`: deleta o arquivo (igual o `/deploy` faz em falha sem recovery). |

Helper scripts:
- `.claude/skills/planejamento/scripts/recalc_progress.sh` — parser bash do markdown que reescreve header in-place. Chamado pelo `progresso` e por `/ship`/`/deploy`.
- `.claude/skills/planejamento/scripts/import_planmode.sh` — chamado pelo hook ExitPlanMode com path do arquivo gerado.

### Parte D — Hook PostToolUse:ExitPlanMode (auto-import do plan mode)

Adicionar em `~/.claude/settings.json` (escopo global, vale pra todos os projetos):

```json
"PostToolUse": [
  {
    "matcher": "ExitPlanMode",
    "hooks": [
      {
        "type": "command",
        "command": "INPUT=$(cat); CWD=$(echo \"$INPUT\" | jq -r '.cwd // \"\"'); if [ -d \"$CWD/docs/planejamento/em-andamento/plan-mode\" ]; then bash \"$CWD/.claude/skills/planejamento/scripts/import_planmode.sh\" \"$INPUT\" 2>&1; fi; true"
      }
    ]
  }
]
```

Comportamento:
1. Dispara só se `docs/planejamento/em-andamento/plan-mode/` existir no CWD (não vaza pra projetos sem essa estrutura).
2. Script lê o `INPUT` (transcript do tool ExitPlanMode), pega o path do arquivo gerado em `~/.claude/plans/` (mais recente nos últimos 60s), copia pra `em-andamento/plan-mode/<YYYY-MM-DD-HHMM>-<slug>.md`, adiciona frontmatter mínimo + header de progresso vazio.
3. Não commita. Faz `git add` no arquivo novo (staged). Output: "Plano importado em `docs/planejamento/em-andamento/plan-mode/<arquivo>`. Rode `git commit -m 'chore(planejamento): importar plano plan-mode'` ou deixe pro `/start`."
4. Idempotente: se já existir arquivo com mesmo slug e mtime próximo, não duplica.

### Parte E — Plumbing mínimo nas skills existentes

| Skill | Mudança | Tamanho |
|---|---|---|
| `/start` SKILL.md | (a) Modo A cria plano em `em-andamento/<source>/` (rotear por `plan_source`). (b) Modo D glob nas 3 subpastas via `em-andamento/*/`. (c) Bootstrap chama `/planejamento progresso` antes de mostrar o resumo da branch. | ~20 linhas alteradas |
| `/ship` SKILL.md | No passo "atualização contínua do plano" (que já existe), chamar `bash .claude/skills/planejamento/scripts/recalc_progress.sh <plano>` após cada checkpoint. Não inventa lógica nova — só delega. | ~5 linhas alteradas |
| `/deploy` SKILL.md | Passo 9.3.5: mover `em-andamento/<source>/<X>.md` → `finalizado/<source>/<X>.md` (preservando subpasta). | ~3 linhas alteradas |
| `CLAUDE.md` projeto | Adicionar 1 parágrafo sob "Planos" instruindo `superpowers:writing-plans` a salvar em `docs/planejamento/em-andamento/superpowers/` (override do default do plugin). | ~5 linhas adicionadas |

Skills mantêm 100% retrocompatibilidade: planos antigos em `em-andamento/` (raiz, sem subpasta) continuam sendo lidos. Planos novos vão pras subpastas.

---

## 2. Critérios de aceite verificáveis (end-to-end)

Cada cenário roda local após PR mergeado:

```bash
# Cenário 1 — Hook ExitPlanMode importa plano novo
# (manual, num terminal Claude novo no projeto Hospital)
# Shift+Tab+Tab → digita "teste de plano" → aprova → sai do plan mode
ls docs/planejamento/em-andamento/plan-mode/*.md   # esperado: 1 arquivo novo dos últimos 30s
git status                                          # esperado: arquivo novo staged

# Cenário 2 — /planejamento progresso recalcula header
echo "marca uma checkbox a mão"
sed -i '' 's/- \[ \] 4.1/- [x] 4.1/' docs/planejamento/em-andamento/plan-mode/<arquivo>.md
/planejamento progresso
grep -A 4 "^> ## Progresso" docs/planejamento/em-andamento/plan-mode/<arquivo>.md
# esperado: % subiu, "tarefas concluídas" subiu, "última atualização" = agora

# Cenário 3 — /planejamento status lista todos
/planejamento status
# esperado: tabela markdown com 1+ plano em-andamento, cada um com progresso

# Cenário 4 — /ship integrado: header atualiza pós-commit
git commit --allow-empty -m "wip(test): teste header"
/ship "teste header" --no-merge --skip-review --no-deploy
grep "SHA" docs/planejamento/em-andamento/plan-mode/<arquivo>.md
# esperado: SHA no header reflete o último commit

# Cenário 5 — /deploy move pra finalizado/<source>/
/deploy ship   # cenário real só vale com mudança real; pra teste, mocar
ls docs/planejamento/finalizado/plan-mode/   # esperado: arquivo movido pra cá

# Cenário 6 — superpowers:writing-plans salva em superpowers/
# (Invocar via /start --rigoroso com working tree limpo)
ls docs/planejamento/em-andamento/superpowers/   # esperado: arquivo novo da skill
```

## 3. Arquivos a tocar (15 no total)

**Criar:**
- `docs/planejamento/em-andamento/{plan-mode,superpowers,manual}/.gitkeep` (3 arquivos)
- `docs/planejamento/finalizado/{plan-mode,superpowers,manual}/.gitkeep` (3 arquivos)
- `.claude/skills/planejamento/SKILL.md` (skill nova)
- `.claude/skills/planejamento/scripts/recalc_progress.sh` (helper)
- `.claude/skills/planejamento/scripts/import_planmode.sh` (helper)

**Modificar:**
- `docs/planejamento/README.md` (nova estrutura + header schema + skill `/planejamento`)
- `.claude/skills/start/SKILL.md` (rotear por subpasta, glob nas 3)
- `.claude/skills/ship/SKILL.md` (delegar progresso pro helper)
- `.claude/skills/deploy/SKILL.md` (mover preservando subpasta)
- `CLAUDE.md` (override do writing-plans default)
- `~/.claude/settings.json` (hook PostToolUse:ExitPlanMode) — **OBS:** fora do repo, ação local. Documentar no README do projeto pra outros devs.

**Mover (git mv):**
- `docs/planejamento/finalizado/2026-05-22-1714-planejamento-estrutura.md` → `finalizado/manual/2026-05-22-1714-planejamento-estrutura.md`

**Importar via hook (após PR mergeado):**
- `~/.claude/plans/image-1-eu-preciso-tranquil-seal.md` → `docs/planejamento/em-andamento/plan-mode/2026-05-22-1900-clicksign-signatarios-card.md` (demo manual no PR pra mostrar o fluxo funcionando)

## 4. Estratégia de PRs

**Opção recomendada: PR único** (`feature/planejamento-subpastas-skill`). Coeso, retrocompatível, ~15 arquivos. Branch protection passa porque mudanças em skill `/planejamento` e helpers não tocam código de produção da app — gates de lint/test passam triviais. Code-review automatizado foca em README + SKILL.md (markdown).

**Opção alternativa: 2 PRs sequenciais**:
- PR-A: pastas + header schema + skill `/planejamento` + README (sem hook, sem mexer em /start /ship /deploy). Mergeável independente.
- PR-B: hook ExitPlanMode + plumbing em /start /ship /deploy + override de CLAUDE.md. Depende de PR-A.

Default: PR único. Dividir só se code-review virar massivo (>500 linhas alteradas).

## 5. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Hook ExitPlanMode quebra em projetos sem `docs/planejamento/` | Guard `if [ -d "$CWD/docs/planejamento/em-andamento/plan-mode" ]` no comando do hook. Skip silencioso. |
| `recalc_progress.sh` desformatar plano (parser bash frágil) | Testar contra os 2 planos reais (atual `finalizado/manual/...` + plano migrado do plan mode). Idempotência: rodar 2x não deve mudar nada na 2ª. |
| `superpowers:writing-plans` plugin é atualizável; override em CLAUDE.md pode ser ignorado | Aceitar como tradeoff. Plan B: criar `.claude/skills/writing-plans/SKILL.md` no repo Hospital com path override (sobrescreve plugin localmente). Fica como follow-up se override de CLAUDE.md não pegar. |
| Pedro esquece de rodar `/planejamento progresso` entre `/ship`s | `/ship` Passo "atualização contínua" já chama o helper — header sempre reflete o último commit. Edits manuais entre commits ficam stale até o próximo commit, mas o impacto é cosmético. |
| Migração do plano existente perde blame | `git mv` preserva. PR vai mostrar 1 rename + 0 mudança de conteúdo nesse arquivo. |
| Hook PostToolUse:ExitPlanMode pode não estar disponível como matcher | Validar antes de implementar: criar hook mínimo de teste (`command: "echo hello >> /tmp/exitplanmode.log"`) e disparar plan mode. Se não dispara, fallback: documentar comando manual `/planejamento importar` como passo após cada plan mode. |

## 6. Comandos pra retomada (próxima sessão Claude)

```bash
# 1. Confirmar branch
git branch --show-current   # esperado: feature/planejamento-subpastas-skill (ou similar)

# 2. Ver progresso do próprio plano deste trabalho
/planejamento status

# 3. Ler estado atual do plano em curso
cat docs/planejamento/em-andamento/manual/$(ls -t docs/planejamento/em-andamento/manual/ | head -1)

# 4. Conferir hook instalado
jq '.hooks.PostToolUse[] | select(.matcher == "ExitPlanMode")' ~/.claude/settings.json

# 5. Validar helper executável
bash .claude/skills/planejamento/scripts/recalc_progress.sh --help
```

## 7. Próximos passos sugeridos após merge

Não-bloqueantes, podem virar Issues separadas:

- **`/planejamento promover --to-superpowers`** — converte plano `plan-mode/` em `superpowers/` (caso você queira expandir um plano rascunho com o schema do writing-plans).
- **Visualizador HTML** — mini-página estática que lê os planos e renderiza Kanban (em-andamento por origem + finalizado), tipo `dashboard.html`. Acoplado ao GitHub Pages.
- **Hook PreCommit que verifica header desatualizado** — bloqueia commit se header de progresso tá mais de 24h velho. Aviso só, opt-in via `.claude/settings.json`.
- **Migrar 86 planos antigos de `~/.claude/plans/`** — script one-shot que filtra por mtime > 30 dias e oferece arquivar batch em `docs/planejamento/finalizado/plan-mode/`. Limpa o `~/.claude/plans/` lotado.
