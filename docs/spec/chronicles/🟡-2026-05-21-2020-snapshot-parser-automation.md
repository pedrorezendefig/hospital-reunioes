---
title: "feat(skills): automatizar /snapshot via script Python (parser routers + migrations + integracoes)"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: null
date_planned: 2026-05-21T20:20:00-03:00
date_deployed: null
sha: null
branch: feat/snapshot-parser-automation
result: pending
status: in_progress
last_touched: 2026-05-21T20:20:00-03:00
plan_source: brainstorming
---

## Contexto

A skill `/snapshot` foi criada no PR #6 (mergeado em `e9f64ee`) mas só documenta o algoritmo em pseudocódigo. Os 7 MDs em `docs/spec/snapshots/` foram populados manualmente na primeira passada. Pra cumprir a promessa de "snapshot vivo automaticamente atualizado a cada deploy", falta implementar o parser real.

Resultado esperado: `python3 .claude/skills/snapshot/scripts/snapshot.py` rodando contra o repo regenera idempotentemente os 5 MDs auto-gerados (ROTAS, ENTIDADES, SCHEMA, MIGRATIONS, INTEGRACOES), preserva blocos curated em FLUXOGRAMAS e ESTRUTURA, e alerta de gaps. Invocado automaticamente pelo `/deploy ship` Passo 9.4.

Stdlib only — sem deps externas. Self-contained num arquivo Python ~500-700 linhas.

## Plano

**Tarefa atual:** 13. Commit + push + PR

- [x] 1. Parser de routers FastAPI (AST stdlib) — 78 endpoints em 13 routers detectados
- [x] 2. Parser de migrations SQL (regex cumulativo) — 36 migrations + 13 tabelas reconstruídas
- [x] 3. Gerador ROTAS.md — agrupado por router, com docstrings reais como descrição
- [x] 4. Gerador ENTIDADES.md — colunas + tipos + constraints + defaults + FKs + indexes
- [x] 5. Gerador SCHEMA.md (Mermaid ER) — 18 FKs detectadas viraram edges; tabelas com até 8 cols
- [x] 6. Gerador MIGRATIONS.md — 36 migrations em ordem com summary correto (após fix de decorativo `=====`)
- [x] 7. Gerador INTEGRACOES.md — cruza project.json.integrations com grep no backend; pega vars relacionadas (ClickSign mostra 3 vars: API_KEY, BASE_URL, WEBHOOK_SECRET)
- [x] 8. Preservação de blocos curated + alertas — FLUXOGRAMAS/ESTRUTURA não são tocados; `detect_gaps()` alerta estados novos sem fluxograma
- [x] 9. Idempotência + flags CLI — `strip_timestamp()` + comparação. Flags `--check`, `--force`, `--only`, `--diff <base>..HEAD`, `--no-commit`, `--root`
- [x] 10. Testar contra repo atual — `--check` mostra 5 MDs mudariam, `--no-commit` regenera, conteúdo casa em estrutura com as versões manuais
- [x] 11. Atualizar snapshot/SKILL.md pra apontar pro script — header novo + sintaxe atualizada + verificação manual
- [x] 12. Atualizar deploy/SKILL.md Passo 9.4 pra invocar script real — comando exato `python3 .claude/skills/snapshot/scripts/snapshot.py` documentado
- [ ] 13. Commit + push + PR
  - Critério: PR aberto com body de 5 seções; labels type:feature, area:skills, area:spec
- [ ] 14. Rodar 5 camadas de gate
  - Critério: code-review, security-review, CI Actions, verification — todas verdes
- [ ] 15. Self-approve + merge squash
  - Critério: PR mergeado em main, branch deletada
- [ ] 16. Renomear chronicle 🟡 → 🟢
  - Critério: arquivo final `🟢-YYYY-MM-DD-HHMM-<sha>-snapshot-parser-automation.md`

## Execução / Resultados

- **2026-05-21 20:20** — Branch `feat/snapshot-parser-automation` criada. Chronicle 🟡 com checkboxes pronto.
- **2026-05-21 20:24** — Script `snapshot.py` escrito (993 linhas, stdlib only). Parser AST do FastAPI detecta `APIRouter(prefix=...)`, decorators `@router.METHOD("path")`, auth via `Depends(get_current_user)`, docstrings. Parser SQL é cumulativo (CREATE → ALTER ADD/DROP → DROP TABLE em ordem cronológica).
- **2026-05-21 20:25** — Primeira run gerou 5 MDs auto-gerados. Bug detectado em MIGRATIONS.md: summary capturando `=====` decorativo das migrations. Fix em `_migration_summary()` (skip linhas só com `=`/`-`/`*`, e strip prefix "Migration NNN:"). Re-run produziu summaries corretos.
- **2026-05-21 20:26** — SKILL.md atualizada: header novo apontando pro script como "fonte da verdade"; pseudocódigo abaixo vira "spec executável". Sintaxe trocada de `/snapshot` mágico pra `python3 .claude/skills/snapshot/scripts/snapshot.py`. Tabela de flags clara. Stats típicas do repo (78 endpoints, 13 routers, 13 tabelas, 36 migrations) documentadas.
- **2026-05-21 20:27** — `deploy/SKILL.md` Passo 9.4 atualizado: comando exato em vez de skill mágica.

### Bugs conhecidos pra próxima iteração (não bloqueiam o PR)

- `_detect_auth()` olha só `func.args` direto; não detecta `Depends(get_current_user)` aninhado em dependencies do router (ex: `/auth/invite/{participante_id}` aparece como ❌ mas tem auth na camada de dependência).
- Prefix `/api` do `health` vem do `main.py` via `app.include_router(router, prefix="/api")` — não detectado (parser só olha `app/routers/*.py`). Aparece como `/health` em vez de `/api/health`.
- Tipos de tabela mostram só primeiro fragmento (ex: `VARCHAR(10)` vira `VARCHAR`). Aceitável pra Mermaid (limite de chars).

Esses 3 são iterações futuras. A versão atual já automatiza o essencial.

## Implementação / Deploy

_(preenchido após merge)_
