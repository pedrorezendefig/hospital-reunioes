---
slug: planejamento-estrutura
title: "Criar docs/planejamento/ versionada como fonte única do plano de trabalho (Etapas 1-7 do enxugamento)"
status: finalizado
plan_source: manual
author: Pedro Rezende <pmrdef@gmail.com>
date_created: 2026-05-22T20:14:00Z
date_last_touched: 2026-05-22T20:48:00Z
branch: feature/planejamento-estrutura (Etapa 1) → refactor/ship-changelog-dedup (Etapa 2) → refactor/skills-planejamento-integration (Etapas 3-7)
chronicle: null
pr: 12, 13, 14
sha_inicio: 2e745ab
sha_atual: a6e1865
estimativa_horas: 6.5
fase_atual: "todas as 7 etapas mergeadas em main"
tarefas_total: 7
tarefas_concluidas: 7
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
│   └── finalizado/         (planos concluídos com sucesso (abandonos são deletados))
│       └── .gitkeep
└── spec/                   (existente, intocado)
    ├── chronicles/
    ├── snapshots/
    └── ...
```

Schema dos `.md` em `em-andamento/` e `finalizado/`:
- Filename: `YYYY-MM-DD-HHMM-<kebab-slug>.md`
- YAML frontmatter rico (15 campos incluindo `branch`, `chronicle`, `pr`, `sha_*`, `status`, `tarefas_*`)
- 8 seções: Visão, Contexto técnico, Arquitetura, Tarefas, Estado, Decisões, Comandos retomada, Histórico

## 4. Tarefas

- [x] 4.1 Criar branch `feature/planejamento-estrutura`
  - Critério: `git branch --show-current` retorna `feature/planejamento-estrutura`
- [x] 4.2 Criar `docs/planejamento/{em-andamento,finalizado}/.gitkeep`
  - Critério: `ls docs/planejamento/em-andamento/.gitkeep docs/planejamento/finalizado/.gitkeep`
- [x] 4.3 Criar `docs/planejamento/README.md` com schema completo
  - Arquivo: `/Users/pedrorezende/PedroDev/Hospital/docs/planejamento/README.md`
  - Critério: `grep -c "^## " docs/planejamento/README.md` retorna ≥ 5 (tem múltiplas seções)
- [ ] 4.4 Abrir PR, mergear, validar que estrutura aparece no GitHub
  - Critério: `gh pr view --json state | jq -r .state` retorna `MERGED`

## 5. Estado de execução

**Fase atual:** PR a abrir
**Última atualização:** 2026-05-22T20:48:00Z
**SHA atual:** a6e1865 (PR #14 mergeado)
**Branch:** main (todas as branches deletadas)

**Já feito (todas as 7 etapas do plano-mãe):**
- [x] Etapa 1 — Estrutura `docs/planejamento/` + README — PR #12 (`7b94677`)
- [x] Etapa 2 — Corte 1: única fonte de write no CHANGELOG = `/deploy` — PR #13 (`217ab64`)
- [x] Etapa 3 — Plumbing: `/start`, `/ship`, `/deploy` integrados a `docs/planejamento/` — PR #14 (`a6e1865`)
- [x] Etapa 4 — Corte 3: 3 frases mínimas de plano (no Modo B do `/start`) — PR #14
- [x] Etapa 5 — Corte 2: auto-skip Camadas 2/3 em diff cosmético (Passo 8.0 do `/ship`) — PR #14
- [x] Etapa 6 — Corte 4a: output compacto do `/ship` (4 linhas) — PR #14
- [x] Etapa 7 — Corte 4b: `/ship --resume` documentado + `/start` Modo D lê plano — PR #14

**Em andamento:** nada — plano concluído.

**Próximo passo:** validar com 1 deploy cosmético + 1 deploy não-cosmético na prática (cenários 1, 2, 3 da seção "Verificação" do plano-mãe).

**Bloqueios atuais:** nenhum

## 6. Decisões tomadas

### 6.1 Pasta na raiz `docs/planejamento/` vs `docs/spec/planejamento/`

**Decidido:** `docs/planejamento/` na raiz.
**Alternativa rejeitada:** `docs/spec/planejamento/` (subordinado a `spec/`).
**Por quê:** o plano não é spec da app (rotas, schema, integrações) — é spec do **trabalho**. Manter no nível de `docs/onboarding/` e `docs/spec/` deixa o propósito claro.

### 6.2 Move (não copy) ao arquivar

**Decidido:** quando plano vira `finalizado` (move pra `finalizado/`) ou abandono (deleta o arquivo), fazer `git mv em-andamento/X.md finalizado/X.md`.
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
- 2026-05-22T20:14 — Branch `feature/planejamento-estrutura` criada, pastas + README criados.
- 2026-05-22T20:18 — Etapa 1 mergeada via PR #12 (`7b94677`).
- 2026-05-22T20:25 — Etapa 2 (Corte 1): `/ship/SKILL.md` Passo 11 reescrito como "Resumo final" (sem prepend); `/deploy/SKILL.md` 9.5 marcado como única fonte de write no CHANGELOG.
- 2026-05-22T20:28 — Etapa 2 mergeada via PR #13 (`217ab64`).
- 2026-05-22T20:35 — Etapa 3 (parcial): `/start/SKILL.md` plumbing — Bootstrap procura plano em `docs/planejamento/em-andamento/` antes do chronicle; Modo A cria plano em vez de chronicle; Modo B exige 3 frases (Corte 3); Modo D lê plano com fallback ao chronicle (Corte 4b parcial).
- 2026-05-22T20:42 — Etapa 3 (resto): `/ship/SKILL.md` Passo 3 referencia plano via campo `planejamento:`; nova seção "Atualização contínua do plano"; Passo 8.0 detecção cosmético (Corte 2); Passo 11 output compacto (Corte 4a); seção "Retomada via plano" (Corte 4b). `/deploy/SKILL.md` Passo 9.3.5 move plano de `em-andamento/` pra `finalizado/`.
- 2026-05-22T20:46 — Etapa 3-7 (consolidadas) mergeadas via PR #14 (`a6e1865`). Branch deletada.
- 2026-05-22T20:48 — Plano arquivado. Próximo: validação prática nos próximos deploys (cenários 1, 2, 3 da seção "Verificação" do plano-mãe).

## 9. Lições e observações pra futuras sessões

- **Sequência de PRs separados** funcionou bem pra Etapas 1 e 2 (cada uma minúscula). Pra Etapas 3-7, consolidar em 1 PR economizou tempo de overhead sem perder rastreabilidade (2 commits separados dentro do PR).
- **Auto-skip de Camadas 2 e 3** aplicado manualmente nos 3 PRs deste trabalho (todas mudanças em SKILL.md). Após a Etapa 5 mergeada, isso vira automático.
- **Dogfooding desde o primeiro PR** ajudou a achar 1 bug processual: o auto-checkout pós `gh pr merge` falha se o working tree tem mudanças não-relacionadas locais (sw.js, state.json) — solução manual: `git stash` antes ou rodar `git checkout main` separado.
- **Git reset acidental** perdeu commit local d67bf3e durante manobra de mover commit pra branch correta. Recuperado via `git reflog` + `git reset --hard <sha>`. Lição: criar branch ANTES de commitar quando estiver na main por engano.
