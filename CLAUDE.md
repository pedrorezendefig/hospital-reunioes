# Regras do Projeto — Hospital Reuniões

## Deploy e spec

- **Toda operação de deploy passa por `/deploy`** (skill versionada em `.claude/skills/deploy/`). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Fonte da verdade da infra:** `docs/spec/deploy/project.json` (manual; com `description`, `stack`, `integrations`, `next_actions`). `state.json` e `history.json` são auto-gerados pela `/deploy`.
- **Snapshot vivo da aplicação:** `docs/spec/snapshots/` — 7 arquivos enxutos (ROTAS · ENTIDADES · SCHEMA · MIGRATIONS · INTEGRACOES · FLUXOGRAMAS · ESTRUTURA) regenerados a cada deploy pela skill `/snapshot` (invocada automaticamente pelo `/deploy ship` pós-health verde). Mais detalhes na seção "Snapshot vivo da aplicação" abaixo.
- **Cronologia unificada de mudanças:** `docs/spec/chronicles/` — 1 MD por mudança, com prefix de cor indicando estado:
  - **🟡** `🟡-YYYY-MM-DD-HHMM-<slug>.md` — plano sem deploy (criado manualmente ou pelo `/ship`).
  - **🟢** `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy healthy.
  - **🔴** `🔴-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy failed / rolled-back.
  - Quando `/deploy ship` roda, ele procura um plano 🟡 com slug similar ao commit. Se acha, anexa seção `## Implementação / Deploy` no final do MD do plano, atualiza YAML frontmatter (autor, SHA, data, resultado) e renomeia 🟡 → 🟢/🔴. Se não acha, cria novo 🟢/🔴 sem corpo de plano.
- **Changelog flat (cronologia única):** `docs/spec/CHANGELOG.md` — prepended pelo `/deploy ship` a cada deploy. Tem 100% do histórico em uma página, offline.
- **Histórico mensal:** `docs/spec/historico/YYYY-MM.md` — changelog humano de commits agrupado por tipo, com autor (gerado manualmente).
- **Não criar** `PRODUCAO.md`, `deploy-history.md`, `dashboard.html`. Não criar pasta `planos/` na raiz nem `implementacoes/` solta — tudo passa por `docs/spec/chronicles/`. Não recriar `blueprint/` (substituído por `docs/spec/`).

## Workflow de time (3 pessoas: Pedro + 2 contratados)

Cada um tem conta GitHub própria e é collaborator do repo. Trabalho passa por PR via skill `/ship` (`.claude/skills/ship/`):

- **Entry point único = `/start`**. Detecta contexto: se working tree tem diff → cria branch + chronicle 🟡 inferido + encadeia `/ship --from-diff`. Se está limpo → invoca `superpowers:brainstorming` pra alinhar abordagem antes de criar chronicle. Se existe chronicle 🟡 da branch atual → modo `retomar` (continuidade entre sessões).
- `/ship "<descrição>" [--issue N] [--type fix|feature|chore|refactor|docs] [--from-diff] [--no-deploy] [--no-merge] [--skip-review]` é o motor por baixo do `/start`. Faz tudo: branch + chronicle 🟡 + commit (conventional commits) + push + abre PR via gh CLI + roda 5 camadas de gate (ver "5 camadas de gate" abaixo) + aprova (self-approval permitido) + mergeia (squash) + `/deploy ship` (que invoca `/snapshot` pós-health). Tipicamente não é invocado direto pelo time — chama `/start`.
- **Backlog**: GitHub Issues + GitHub Projects board "Hospital Sprint" (colunas: Backlog, A fazer, Em progresso, Em review, Concluído).
- **Notificações**: GitHub Mobile (push notifications nativas, identificação por nome do repo) + GitHub Discussions (canal persistente dentro do repo, com categorias Anúncios/Ideias/Dúvidas/Decisões). Sem Discord/Slack — tudo via GitHub.
- **Branch protection**: main exige 1 approval + status checks (CI verde) + linear history. Self-approval permitido (5 camadas de gate validam).
- **Onboarding**: ver `docs/onboarding/dev.md`.

## Fluxo do time (3 pessoas)

Time iniciante decora **1 palavra**: `/start`. O resto é roteamento interno entre skills.

1. **Refinar a ideia (opcional, antes do `/start`)** — modo plano nativo do Claude Code (`Shift+Tab+Tab`). Conversa com o assistente, ele lê código relevante, propõe abordagem. Aprovou? Sai do plan mode, ele implementa. Alternativa: invocar diretamente `superpowers:brainstorming` que `/start` já faz automaticamente quando working tree tá limpo.
2. **`/start`** — entry point único. Lê working tree:
   - Limpo → invoca `superpowers:brainstorming` + `writing-plans` → cria chronicle 🟡 com plano executável (checkboxes).
   - Limpo + chronicle 🟡 da branch atual existe → modo `retomar` (lê progresso, oferece continuar de onde parou).
   - Tem diff → cria branch + chronicle 🟡 + encadeia `/ship --from-diff` (commit → PR → review → merge → deploy).
   - Flags: `--rapido` pula brainstorming · `--rigoroso` força brainstorming mesmo com diff · `debug` invoca `systematic-debugging`.
3. **`/issue`** — subskill do `/start` pra criar/listar/pegar/comentar/fechar Issue GitHub. Pode ser chamada solta também.

Skills versionadas em `.claude/skills/{start,ship,issue,deploy,snapshot,atualizar-app}/`. Documentação visual do fluxo em `docs/onboarding/workflow.html`.

**Canal do time**: GitHub Discussions no próprio repo (4 categorias: Anúncios, Ideias, Dúvidas, Decisões). Habilitado via `gh api -X PATCH "/repos/pedrorezendefig/hospital-reunioes" --raw-field has_discussions=true`. Notificações push via GitHub Mobile app. Sem Discord.

## Planos

Quando o usuário pedir planejamento, criar o plano em **`docs/spec/chronicles/`**, com nome no formato:

```
🟡-YYYY-MM-DD-HHMM-<slug>.md
```

**Timestamp = última atualização do arquivo, não criação.** Ao editar um plano 🟡 existente, **renomear** com o novo timestamp:

```
mv "🟡-2026-05-11-1400-foo.md" "🟡-2026-05-12-0930-foo.md"
```

Assim a ordenação por nome no explorer reflete sempre o que foi mexido mais recente. Use o emoji 🟡 como prefix literal. `<slug>` é uma descrição curta em kebab-case (lowercase, ascii, sem acentos).

> Para ver os mais recentes no topo do explorer, deixar o VS Code com `"explorer.sortOrder": "modified"`.

Cada arquivo tem **YAML frontmatter** e **três seções obrigatórias**:

```markdown
---
title: <tipo>(<escopo>): <descrição>
author: <Nome> <email>
type: fix|feature|chore|refactor|docs
issue: <N ou null>
pr: <N ou null>
date_planned: <ISO-8601>
date_deployed: null
sha: null
branch: <branch>
result: pending
status: not_started | in_progress | blocked | done
last_touched: <ISO-8601>
plan_source: writing-plans | plan-mode | manual | brainstorming
---

## Contexto
[por quê — valor, risco, motivação]

## Plano
**Tarefa atual:** N. <descrição>

- [x] 1. <tarefa concluída>
  - Critério: <comando ou afirmação verificável>
- [ ] 2. <tarefa a fazer>
  - Critério: ...

## Execução / Resultados
[registro do que foi feito, resultados, desvios, itens pendentes]
```

Quando o plano é cumprido via `/deploy ship` (ou via `/ship`) e o slug bate por similaridade com o commit, o arquivo automaticamente vira 🟢 (ou 🔴 se falhou) e ganha uma seção `## Implementação / Deploy` no final. **O timestamp no nome do arquivo passa a ser a data/hora do deploy** (sobrescreve o do plano), e o nome ganha o `<sha7>` do commit. O YAML frontmatter é atualizado com `date_deployed`, `sha`, `result`, `duration_*`.

```
🟡-2026-05-12-0930-foo.md  →  🟢-2026-05-12-1145-abc1234-foo.md
```

Não usar `.claude/plans/`. Não criar `.md` de plano em `planos/` (essa pasta não existe mais).

## Continuidade entre sessões

Quando uma sessão Claude estoura contexto (ou você fecha o terminal), o trabalho não é perdido — ele vive no **chronicle 🟡** comitado em git, na branch da feature. Pra retomar:

1. Abrir terminal novo
2. Estar na branch da feature: `git checkout feat/<minha-branch>`
3. Rodar `/start`
4. A skill detecta o chronicle 🟡 cujo frontmatter `branch:` casa com a branch atual, conta progresso (`[x]` vs `[ ]`), mostra resumo, e oferece retomar de onde parou via `superpowers:executing-plans`.

Mini-commits "wip" são feitos a cada checkbox concluído (`git commit -m "wip(<slug>): tarefa N — ..."`). Quando `/ship` mergeia, faz **squash** — wip some, fica só 1 commit conventional. Resultado: chronicle 🟡 commitado é a memória de trabalho **independente da sessão Claude**.

## Formato do chronicle é único

O chronicle 🟡 segue o mesmo frontmatter + seções (Contexto, Plano com checkboxes, Execução / Resultados) **independente de quem criou**:

- `superpowers:writing-plans` (formato gerado pela skill) ✅
- Plan mode nativo do Claude (`Shift+Tab+Tab`) ✅
- Dev escrevendo à mão ✅
- `superpowers:brainstorming` → writing-plans ✅

Quem lê depois (Claude novo em outra sessão, outro dev, `executing-plans`) sempre vê o mesmo esqueleto. Campo `plan_source` no frontmatter registra a origem — útil pra debugging, não pra fluxo.

## `.superpowers/` é gitignored

A skill `superpowers:brainstorming` opcionalmente abre um Visual Companion (HTMLs gerados em `.superpowers/brainstorm/<id>/`). Isso é um **cache visual descartável** — não fonte da verdade. Já está no `.gitignore`. Os planos reais vivem em `docs/spec/chronicles/`.

## 5 camadas de gate antes do self-approval

Self-approval do PR (Pedro aprova o próprio PR, idem contratados) é permitido porque o `/ship` roda **5 camadas independentes** de gate antes de mergear. Qualquer veto trava:

1. **`/code-review`** — review automatizada de qualidade (Claude lê o diff)
2. **`/security-review`** — review de segurança (Claude lê o diff com foco em vulns)
3. **`superpowers:requesting-code-review`** — subagent independente com critérios rígidos (tests, edge cases, naming, propósito vs implementação)
4. **CI Actions** — `.github/workflows/ci.yml` (lint backend + lint frontend + build)
5. **`superpowers:verification-before-completion`** — roda comando real antes do merge, lê output literal, só então confirma

Self-approval acontece **só** se as 5 derem verde. Flags de emergência (`--skip-review`, `--hotfix`) reduzem o número de camadas, registram no chronicle, e exigem motivação explícita.

## Snapshot vivo da aplicação

`docs/spec/snapshots/` mantém 7 arquivos com o estado atual da aplicação, regenerados a cada deploy pela skill `/snapshot` (invocada automaticamente pelo `/deploy ship` pós-health verde):

| Arquivo | O que tem | Atualização |
|---|---|---|
| `ROTAS.md` | endpoints FastAPI (método + path + descrição + auth) | auto, parser de `routers/*.py` |
| `ENTIDADES.md` | tabelas + colunas + tipos + FKs | auto, parser de `migrations/*.sql` |
| `SCHEMA.md` | diagrama ER em Mermaid | auto, derivado das FKs |
| `MIGRATIONS.md` | lista cronológica enxuta | auto |
| `INTEGRACOES.md` | serviços externos (OpenRouter, ClickSign, Resend, ...) | auto, cruzando `project.json` com grep |
| `FLUXOGRAMAS.md` | máquinas de estado em Mermaid | **manual** (blocos `<!-- curated -->`); skill só alerta de gaps |
| `ESTRUTURA.md` | árvore de pastas backend/frontend/supabase | **parcial manual** (blocos curated) |

`/snapshot` é **idempotente** — se nada mudou, não commita. Commits gerados (`chore(spec): atualizar snapshot ...`) NÃO disparam novo deploy (o `scope_map` em `project.json` evita loop). Mermaid renderiza nativo no GitHub e GitHub Mobile.

## Pré-deploy checklist (auto via `/deploy`)

Cada `/deploy ship` roda uma bateria de gates antes de subir mudanças. Os ativos pra esse projeto estão declarados em `docs/spec/deploy/project.json` no bloco `gates`:

| Gate | Onde | Ação se falhar |
|---|---|---|
| `secrets_in_git` | Pre-flight | ❌ bloqueia se `.env`, `*.key`, `*-env-producao.txt` etc. foram adicionados ao commit |
| `env_example_sync` | Pre-flight | ❌ chaves em `Settings` (config.py) e `.env.example` precisam casar |
| `migrations_backup_dir` | Pre-flight | ❌ bloqueia se `supabase/migrations_backup` existe (resíduo perigoso) |
| `lint` | Pre-flight | ❌ ruff + ruff format (backend), pnpm lint + tsc (frontend). Pulável com `--skip-lint` |
| `build_args_consistency` | Pre-flight | ❌ NEXT_PUBLIC_* tem que estar marcado `is_build_time` no Coolify |
| `dns_resolves` | Pre-flight | ❌ FQDNs do projeto têm que resolver pro IP da VPS |
| `cors_audit` | Pre-flight | ❌ procura `allow_origins=["*"]` ou `allow_origin_regex=".*"` em config.py/main.py |
| `fk_index_warning` | Pre-flight | ⚠ avisa quando migration nova declara FK sem `CREATE INDEX` correspondente (warn-only) |
| `health_rich` | Pós-deploy | ❌ body de `/api/health` precisa conter `status` e `db`. Se faltar, rollback automático |
| Anti-leak de secrets | Pre-write `state.json` | ❌ aborta escrita se valor escalar bate regex de chave |
| `/snapshot` | Pós-deploy | ⚠ regenera `docs/spec/snapshots/`. Falha não derruba ship (warn-only) |

Além disso, `prod_only_assertions` no `project.json` exige `ENVIRONMENT=production`, `DEBUG=false`, `ENABLE_BYPASS_ENDPOINTS=false`, `CLICKSIGN_BASE_URL=https://app.clicksign.com` no backend Coolify. Divergência bloqueia o ship.

O backend tem hard-fail em `config.py:validate_debug_prod()`: se `DEBUG=true` chegar em prod, o container não sobe.
