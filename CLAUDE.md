# Regras do Projeto — Hospital Reuniões

## Deploy e spec

- **Toda operação de deploy passa por `/deploy`** (skill versionada em `.claude/skills/deploy/`). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Especificação executável:** `docs/spec/` — gerado pelo pipeline REVERSA (`/spec update`, ~10-12 min) ao final de cada `/deploy ship`. Estrutura padrão: `sdd/`, `architecture.md`, `c4-*.md`, `erd-complete.md`, `domain.md`, `gaps.md`, `confidence-report.md`, `traceability/`, etc. Cada afirmação tem escala 🟢 confirmado, 🟡 inferido, 🔴 lacuna.
- **Fonte da verdade da infra:** `docs/spec/deploy/project.json` (manual; com `description`, `stack`, `integrations`, `next_actions`). `state.json` e `history.json` são auto-gerados pela `/deploy`.
- **Cronologia unificada de mudanças:** `docs/spec/chronicles/` — 1 MD por mudança, com prefix de cor indicando estado:
  - **🟡** `🟡-YYYY-MM-DD-HHMM-<slug>.md` — plano sem deploy (criado manualmente ou pelo `/ship`).
  - **🟢** `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy healthy.
  - **🔴** `🔴-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy failed / rolled-back.
  - Quando `/deploy ship` roda, ele procura um plano 🟡 com slug similar ao commit. Se acha, anexa seção `## Implementação / Deploy` no final do MD do plano, atualiza YAML frontmatter (autor, SHA, data, resultado) e renomeia 🟡 → 🟢/🔴. Se não acha, cria novo 🟢/🔴 sem corpo de plano.
- **Changelog flat (cronologia única):** `docs/spec/CHANGELOG.md` — prepended pelo `/deploy ship` a cada deploy. Tem 100% do histórico em uma página, offline.
- **Histórico mensal:** `docs/spec/historico/YYYY-MM.md` — gerado por `/spec historico` (changelog humano de commits agrupado por tipo, com autor).
- **Não criar** `PRODUCAO.md`, `deploy-history.md`, `dashboard.html`. Não criar pasta `planos/` na raiz nem `implementacoes/` solta — tudo passa por `docs/spec/chronicles/`. Não recriar `blueprint/` (substituído por `docs/spec/`).

## Workflow de time (3 pessoas: Pedro + 2 contratados)

Cada um tem conta GitHub própria e é collaborator do repo. Trabalho passa por PR via skill `/ship` (`.claude/skills/ship/`):

- `/ship "<descrição>" [--issue N] [--type fix|feature|chore|refactor|docs|spec] [--no-deploy] [--no-merge] [--skip-review]` faz tudo de uma vez: branch + chronicle 🟡 + commit (conventional commits) + push + abre PR via gh CLI + roda `/code-review` e `/security-review` + aprova (self-approval permitido) + mergeia (squash) + `/deploy ship` (inclui `/spec update`).
- **Backlog**: GitHub Issues + GitHub Projects board "Hospital Sprint" (colunas: Backlog, A fazer, Em progresso, Em review, Concluído).
- **Notificações**: GitHub Mobile (push notifications nativas, identificação por nome do repo) + GitHub Discussions (canal persistente dentro do repo, com categorias Anúncios/Ideias/Dúvidas/Decisões). Sem Discord/Slack — tudo via GitHub.
- **Branch protection**: main exige 1 approval + status checks (CI verde) + linear history. Self-approval permitido (o `/ship` rodou `/code-review` e `/security-review`).
- **Onboarding**: ver `docs/onboarding/dev.md` (a criar).

## Issues e Discussions

O time tá começando em GitHub workflow. Pra evitar que pessoas escrevam Issue mal-estruturada (ou abandonem porque "é chato abrir uma"), usa-se a skill **`/issue`** (versionada em `.claude/skills/issue/`). É conversacional e faseada:

- **`/issue new`** (ou `/issue`): inicia diálogo guiado — pergunta uma coisa por vez (tipo, área, descrição, reprodução, prioridade, assignee), estrutura body com seções, mostra preview, cria via `gh issue create`. Pode encadear `/ship` ao final.
- **`/issue listar`**: lista Issues abertas em tabela. Aceita filtros em PT ("só os bugs", "só os meus").
- **`/issue pegar <N>`**: importa Issue #N pro contexto da conversa (body + comments) sem agir. Oferece próximos passos.
- **`/issue trabalhar <N>`**: importa + invoca `/ship` automaticamente. Caminho mais comum: time iniciante pega uma Issue e o Claude começa a trabalhar.
- **`/issue comentar <N>`** e **`/issue fechar <N>`**: ações curtas com preview e confirmação.

A skill é **didática**: explica termos técnicos na primeira menção (PR, branch, label), comenta o que tá fazendo nos bastidores (`gh issue create` vs browser), nunca cria/edita Issue sem preview + confirmação, e sugere **GitHub Discussions** quando o conteúdo não é acionável (dúvida, ideia, decisão exploratória).

Discussions tem 4 categorias no repo: **Anúncios**, **Ideias**, **Dúvidas**, **Decisões**. Habilitado via `gh api -X PATCH "/repos/pmrdef/hospital" --raw-field has_discussions=true` (passo 5 do `GITHUB-SETUP.md`).

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

Cada arquivo tem **YAML frontmatter** e **duas seções obrigatórias**:

```markdown
---
title: <tipo>(<escopo>): <descrição>
author: <Nome> <email>
type: fix|feature|chore|refactor|docs|spec
issue: <N ou null>
pr: <N ou null>
date_planned: <ISO-8601>
date_deployed: null
sha: null
branch: <branch>
result: pending
---

## Plano
[escopo, passos, critérios de sucesso, riscos, valor pro negócio]

## Execução / Resultados
[registro do que foi feito, resultados, desvios, itens pendentes]
```

Quando o plano é cumprido via `/deploy ship` (ou via `/ship`) e o slug bate por similaridade com o commit, o arquivo automaticamente vira 🟢 (ou 🔴 se falhou) e ganha uma seção `## Implementação / Deploy` no final. **O timestamp no nome do arquivo passa a ser a data/hora do deploy** (sobrescreve o do plano), e o nome ganha o `<sha7>` do commit. O YAML frontmatter é atualizado com `date_deployed`, `sha`, `result`, `duration_*`.

```
🟡-2026-05-12-0930-foo.md  →  🟢-2026-05-12-1145-abc1234-foo.md
```

Exceção temporária: `plano.md` na raiz do projeto (plano de migração REVERSA + workflow de time) é permitido. Apagar quando a migração for considerada concluída e estável.

Exceção temporária: `GITHUB-SETUP.md` na raiz (tutorial guiado do setup remoto GitHub) é permitido até o Pedro fazer o setup. Apagar depois.

Não usar `.claude/plans/`. Não criar `.md` de plano em `planos/` (essa pasta não existe mais).

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
| `/spec update` | Pós-deploy | ⚠ pipeline REVERSA. Falha não derruba ship; ship segue healthy + marca chronicle com warning. Pulável com `--skip-spec` |

Além disso, `prod_only_assertions` no `project.json` exige `ENVIRONMENT=production`, `DEBUG=false`, `ENABLE_BYPASS_ENDPOINTS=false`, `CLICKSIGN_BASE_URL=https://app.clicksign.com` no backend Coolify. Divergência bloqueia o ship.

O backend tem hard-fail em `config.py:validate_debug_prod()`: se `DEBUG=true` chegar em prod, o container não sobe.
