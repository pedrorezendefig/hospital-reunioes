---
slug: planejamento-estrutura
title: "Criar docs/planejamento/ versionada como fonte única do plano de trabalho"
status: ativo
plan_source: manual
author: Pedro Rezende <pmrdef@gmail.com>
date_created: 2026-05-22T20:14:00Z
date_last_touched: 2026-05-22T20:14:00Z
branch: feature/planejamento-estrutura
chronicle: null
pr: null
sha_inicio: 2e745ab
sha_atual: null
estimativa_horas: 1
fase_atual: "PR aberto, aguardando merge"
tarefas_total: 4
tarefas_concluidas: 3
---

## 1. Visão

Criar a pasta `docs/planejamento/` versionada com schema rico (frontmatter + 8 seções) que serve como **fonte única da verdade do plano** de cada trabalho no Hospital Reuniões. Distinta de `~/.claude/plans/` (rascunho local do plan mode), `.superpowers/brainstorm/` (cache visual descartável) e `docs/spec/chronicles/` (diário enxuto pós-fato). Objetivo: próxima sessão Claude retoma trabalho a meio caminho lendo 1 arquivo MD e rodando 4 comandos.

Esta é a **Etapa 1 de 7** do plano aprovado em `~/.claude/plans/esse-fluxo-de-deploy-ancient-dijkstra.md`. Não toca skill ainda — só infraestrutura.

## 2. Contexto técnico

### 2.1 Estado atual do código

- `/Users/pedrorezende/PedroDev/Hospital/.gitignore:16` — `.superpowers/` gitignored
- `/Users/pedrorezende/PedroDev/Hospital/.gitignore:22` — `docs/superpowers/` gitignored
- `/Users/pedrorezende/PedroDev/Hospital/docs/` — só tem `onboarding/` e `spec/` hoje
- `/Users/pedrorezende/PedroDev/Hospital/docs/spec/chronicles/` — chronicles 🟡/🟢/🔴 já existentes
- `/Users/pedrorezende/.claude/plans/` — 87 arquivos de plan mode nativo (local, fora do repo)

### 2.2 Achados de exploração

- Schema do chronicle (frontmatter YAML + Contexto/Plano/Execução) é referência boa mas enxuto demais pra "99% contexto teletransportado"
- Pasta `docs/spec/` já tem convenção `kebab-case-com-prefixo-de-cor` — vou seguir convenção análoga em `docs/planejamento/` (sem emoji, com timestamp prefix)
- Não há nenhum script ou hook que toque essas pastas hoje — Etapa 1 é puramente arquivos novos

### 2.3 Restrições e premissas

- Não mexer em skills `/start`, `/ship`, `/deploy` (essa etapa é só estrutura — Etapas 3+ farão plumbing)
- Não mexer em `docs/spec/chronicles/` (sistema paralelo, mantém)
- Etapa 1 tem que ser PR independente e mergeavel sozinho (resto do plano vem em PRs separados)

## 3. Arquitetura proposta

```
docs/
├── onboarding/             (existente)
├── planejamento/           ← NOVO
│   ├── README.md           (schema documentado)
│   ├── em-andamento/       (planos ativos)
│   │   └── .gitkeep
│   └── arquivados/         (planos finalizados/abandonados)
│       └── .gitkeep
└── spec/                   (existente, intocado)
    ├── chronicles/
    ├── snapshots/
    └── ...
```

Schema dos `.md` em `em-andamento/` e `arquivados/`:
- Filename: `YYYY-MM-DD-HHMM-<kebab-slug>.md`
- YAML frontmatter rico (15 campos incluindo `branch`, `chronicle`, `pr`, `sha_*`, `status`, `tarefas_*`)
- 8 seções: Visão, Contexto técnico, Arquitetura, Tarefas, Estado, Decisões, Comandos retomada, Histórico

## 4. Tarefas

- [x] 4.1 Criar branch `feature/planejamento-estrutura`
  - Critério: `git branch --show-current` retorna `feature/planejamento-estrutura`
- [x] 4.2 Criar `docs/planejamento/{em-andamento,arquivados}/.gitkeep`
  - Critério: `ls docs/planejamento/em-andamento/.gitkeep docs/planejamento/arquivados/.gitkeep`
- [x] 4.3 Criar `docs/planejamento/README.md` com schema completo
  - Arquivo: `/Users/pedrorezende/PedroDev/Hospital/docs/planejamento/README.md`
  - Critério: `grep -c "^## " docs/planejamento/README.md` retorna ≥ 5 (tem múltiplas seções)
- [ ] 4.4 Abrir PR, mergear, validar que estrutura aparece no GitHub
  - Critério: `gh pr view --json state | jq -r .state` retorna `MERGED`

## 5. Estado de execução

**Fase atual:** PR a abrir
**Última atualização:** 2026-05-22T20:14:00Z
**SHA atual:** (a definir após commit)
**Branch:** feature/planejamento-estrutura

**Já feito:**
- [x] 4.1 Branch criada
- [x] 4.2 Pastas + .gitkeep
- [x] 4.3 README.md com schema completo

**Em andamento:**
- [ ] 4.4 Abrir PR + mergear

**Próximo passo:**
Commitar (3 arquivos: README + 2× .gitkeep + este plano), push, abrir PR via gh CLI, aprovar (auto via /ship futuramente), mergear squash.

**Bloqueios atuais:** nenhum

## 6. Decisões tomadas

### 6.1 Pasta na raiz `docs/planejamento/` vs `docs/spec/planejamento/`

**Decidido:** `docs/planejamento/` na raiz.
**Alternativa rejeitada:** `docs/spec/planejamento/` (subordinado a `spec/`).
**Por quê:** o plano não é spec da app (rotas, schema, integrações) — é spec do **trabalho**. Manter no nível de `docs/onboarding/` e `docs/spec/` deixa o propósito claro.

### 6.2 Move (não copy) ao arquivar

**Decidido:** quando plano vira `finalizado`/`abandonado`, fazer `git mv em-andamento/X.md arquivados/X.md`.
**Por quê:** preserva blame, evita duplicação. O plano é o mesmo arquivo, só muda status.

### 6.3 Sem emoji no filename

**Decidido:** filenames com `YYYY-MM-DD-HHMM-<slug>.md`, sem emoji.
**Alternativa rejeitada:** mimic chronicle 🟡/🟢/🔴.
**Por quê:** status já vive no frontmatter. Emoji no filename ajuda no explorer pra chronicle (UX rápida), mas o plano é lido a fundo — ler frontmatter é o normal.

## 7. Comandos pra retomada

```bash
# 1. Confirma branch
git branch --show-current  # esperado: feature/planejamento-estrutura

# 2. Vê o que já existe
ls docs/planejamento/
cat docs/planejamento/README.md | head -20

# 3. Confirma onde parou (próxima tarefa)
grep -A 3 "^**Próximo passo" docs/planejamento/em-andamento/2026-05-22-1714-planejamento-estrutura.md

# 4. Estado git
git status && git log --oneline main..HEAD
```

## 8. Histórico desta sessão

- 2026-05-22T20:14 — Plano aprovado em `~/.claude/plans/esse-fluxo-de-deploy-ancient-dijkstra.md`. Iniciando Etapa 1.
- 2026-05-22T20:14 — Branch criada, pastas + README criados. Próximo: commit + PR.
