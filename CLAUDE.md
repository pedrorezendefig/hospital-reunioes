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

Skills versionadas em `.claude/skills/{start,ship,issue,deploy,snapshot,atualizar-app,planejamento}/`. Documentação visual do fluxo em `docs/onboarding/workflow.html`.

**Canal do time**: GitHub Discussions no próprio repo (4 categorias: Anúncios, Ideias, Dúvidas, Decisões). Habilitado via `gh api -X PATCH "/repos/pedrorezendefig/hospital-reunioes" --raw-field has_discussions=true`. Notificações push via GitHub Mobile app. Sem Discord.

## Planos

Plano vive em **`docs/planejamento/em-andamento/<source>/<YYYY-MM-DD-HHMM>-<slug>.md`** onde `<source>` é uma de 3 subpastas:

| Subpasta | Origem | Como chega lá |
|---|---|---|
| `plan-mode/` | Plan mode nativo do Claude Code (`Shift+Tab+Tab`) | Hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json` dispara `import_planmode.sh` que importa de `~/.claude/plans/`. |
| `superpowers/` | Skill `superpowers:writing-plans` | **A skill writing-plans deve salvar planos direto em `docs/planejamento/em-andamento/superpowers/<slug>.md`** (override do default do plugin que aponta pra `docs/superpowers/plans/`). Slug = kebab-case do título. |
| `manual/` | Você escreveu à mão no VS Code, ou `/start` Modo A/B criou | Diretamente. |

Esquema completo (frontmatter + header de progresso + 8 seções) documentado em **`docs/planejamento/README.md`**. Skill `/planejamento` em `.claude/skills/planejamento/` gerencia.

**Renomeio por timestamp não se aplica aqui** — timestamp do filename = criação do plano (não mexer). Última atualização vive em `date_last_touched` no frontmatter (atualizado pelo `recalc_progress.sh`).

**Header de progresso** (bloco blockquote logo após frontmatter) é **derivado** — `bash .claude/skills/planejamento/scripts/recalc_progress.sh <plano>` reescreve a cada commit/checkpoint. Conta `[x]`/`[ ]` no body, atualiza `tarefas_concluidas` no frontmatter, mostra `Progresso X% · Fase N de M · A/B tarefas · SHA · branch · PR`.

**Trajetória do arquivo:**
- Sucesso (`/deploy ship` healthy) → `git mv em-andamento/<source>/X.md finalizado/<source>/X.md`, `status: finalizado` no frontmatter.
- Abandono → arquivo **deletado**. Cronologia da falha sobrevive no chronicle 🔴 (`docs/spec/chronicles/`) e no `history.json`.

**Chronicle 🟡/🟢/🔴 em `docs/spec/chronicles/`** continua sendo o **índice pós-fato por PR** (1 chronicle por PR mergeado). Curto, vai pro CHANGELOG, alimenta a timeline. Plano em `docs/planejamento/` é o "manual de instruções" longo (pode cobrir múltiplos PRs sequenciais via `fases_total: N`).

Não usar `.claude/plans/` como destino final (rascunho local do plan mode, importado pelo hook). Não criar `.md` de plano em `planos/` (essa pasta não existe).

## Continuidade entre sessões

Quando uma sessão Claude estoura contexto (ou você fecha o terminal), o trabalho não é perdido — vive no **plano** comitado em git, na branch da feature. Pra retomar:

1. Abrir terminal novo
2. Estar na branch da feature: `git checkout feat/<minha-branch>`
3. Rodar `/start`
4. A skill detecta o plano em `docs/planejamento/em-andamento/*/` cujo frontmatter `branch:` casa com a branch atual, recalcula o header de progresso, mostra resumo (Fase N de M · X% · próximo passo do §5), e oferece retomar via `superpowers:executing-plans`.
5. Alternativa standalone: `/planejamento status` lista todos os planos abertos com %.

Mini-commits "wip" são feitos a cada checkbox concluída (`git commit -m "wip(<slug>): tarefa N — ..."`). Quando `/ship` mergeia, faz **squash** — wip some, fica só 1 commit conventional. Resultado: plano commitado é a memória de trabalho **independente da sessão Claude**.

## Formato do plano é único

O plano segue o mesmo schema (frontmatter + header de progresso + 8 seções) **independente de quem criou** — campo `plan_source` no frontmatter registra a origem (`plan-mode-claude` / `superpowers-writing-plans` / `manual` / `skipped`). Quem lê depois sempre vê o mesmo esqueleto.

## `.superpowers/` é gitignored

A skill `superpowers:brainstorming` opcionalmente abre um Visual Companion (HTMLs gerados em `.superpowers/brainstorm/<id>/`). Isso é um **cache visual descartável** — não fonte da verdade. Já está no `.gitignore`. Os planos reais vivem em `docs/planejamento/`.

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
