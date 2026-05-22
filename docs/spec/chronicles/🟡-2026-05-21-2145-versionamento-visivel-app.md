---
title: "feat(app): acrescentar versionamento visível na aplicação + release notes nos docs"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: 8
date_planned: 2026-05-21T21:45:00-03:00
date_deployed: null
sha: null
branch: feat/versionamento-visivel-app
result: pending
status: in_progress
last_touched: 2026-05-21T21:45:00-03:00
plan_source: plan-mode
---

## Contexto

Hoje o Hospital Reuniões é rastreado **apenas por SHA do commit** (`a98e3d5`, etc.). Não há versão semântica visível na UI nem release notes por versão nos docs. O endpoint `/api/health` retorna `version` mas é hardcoded em `Settings.app_version = "0.1.0"` e nunca muda. `frontend/package.json` também tem `version: "0.1.0"` estático.

Pedro quer:
1. **Rodapé visível em toda a app** mostrando a versão atual (sem SHA, só `v0.2.1`).
2. **Docs/CHANGELOG.md** organizados por versão, com link pro GitHub na entrada documentada.
3. **Tudo num único PR** — primeira subida já bumpa pra `v0.2.0` (porque é `feat:`).

Estratégia escolhida (documentada inline neste chronicle e em `docs/spec/VERSIONING.md`):
- Semver com bump **automático** pelo `/ship` baseado no tipo do commit (BREAKING > feat > fix/chore/refactor).
- Fonte da verdade: `frontend/package.json`. Backend espelha via env `APP_VERSION`.
- Rodapé no fim do `<main>` (não fixed, não compete com BottomNav mobile).
- Skill `/deploy` injeta `APP_VERSION` no Coolify pré-build via `mcp__coolify__bulk_env_update`.

## Plano

**Tarefa atual:** — (todas concluídas, pronto pra `/ship`)

- [x] 1. Criar branch + chronicle 🟡
  - Critério: `git branch --show-current` retorna `feat/versionamento-visivel-app`; arquivo deste plano existe e está commitado
- [x] 2. Backend: Settings lê `APP_VERSION` de env
  - Critério: `curl localhost:8000/api/health` retorna `"version":"0.1.0"` (fallback); `APP_VERSION=0.2.0 uvicorn...` retorna `"version":"0.2.0"`
- [x] 3. Frontend: expor `NEXT_PUBLIC_APP_VERSION` em `next.config.ts`
  - Critério: `pnpm build` produz bundle com versão inlined; `generateBuildId` retorna `v{versão}-{timestamp}`
- [x] 4. Frontend: criar `Footer.tsx`
  - Critério: componente novo em `frontend/src/components/layout/Footer.tsx`; texto `v{version}` clicável → CHANGELOG no GitHub
- [x] 5. Frontend: encaixar `<Footer />` em `AppShell.tsx`
  - Critério: rodapé aparece ao rolar até o fim em qualquer página local; BottomNav mobile não fica por cima
- [x] 6. Docs: criar `VERSIONING.md`
  - Critério: `docs/spec/VERSIONING.md` existe; explica esquema, regra de bump, link versão↔SHA
- [x] 7. Docs: header explicativo no `CHANGELOG.md`
  - Critério: 3-4 linhas no topo descrevendo formato novo `## v0.X.Y`; entradas antigas (formato `## YYYY-MM-DD HH:MM`) intocadas
- [x] 8. Skill `/ship`: adicionar bump automático de semver
  - Critério: passo "Bump de versão" documentado em `.claude/skills/ship/SKILL.md`; algoritmo lê tipo dominante (BREAKING > feat > fix/chore), edita `package.json`, commit `chore(release): bump vX.Y.Z`
- [x] 9. Skill `/deploy`: injetar `APP_VERSION` no Coolify pré-deploy
  - Critério: passo documentado em `.claude/skills/deploy/SKILL.md`; `mcp__coolify__bulk_env_update` setado pré-`mcp__coolify__deploy`; pós-health valida match
- [x] 10. Validar build local
  - Critério: `pnpm build` no frontend e `ruff check` no backend passam sem erro
- [x] 11. Bump manual de v0.1.0 → v0.2.0 (chicken-and-egg do primeiro PR de versionamento)
  - Critério: `frontend/package.json` em `0.2.0`; bundle inlined; build verde

## Execução / Resultados

### Implementação (10 wip commits)

| # | Tarefa | Arquivos tocados | Commit |
|---|---|---|---|
| 1 | Chronicle 🟡 | `docs/spec/chronicles/🟡-...md` | `78406f6` |
| 2 | Backend env | `backend/app/config.py`, `backend/.env.example`, `docs/spec/deploy/project.json` | `a432dfd` |
| 3 | Frontend next.config | `frontend/next.config.ts`, `frontend/.env.example` | `394a012` |
| 4-5 | Footer + AppShell | `frontend/src/components/layout/Footer.tsx` (novo), `frontend/src/components/layout/AppShell.tsx` | `ddf5b5f` |
| 6-7 | Docs | `docs/spec/VERSIONING.md` (novo), `docs/spec/CHANGELOG.md` | `07f5041` |
| 8 | Skill /ship | `.claude/skills/ship/SKILL.md` (Passo 5.5 novo + Passo 11 atualizado) | `ed75f94` |
| 9 | Skill /deploy | `.claude/skills/deploy/SKILL.md` (Passo 3.5 novo + Passo 7.2 + state.json/history.json schemas) | `bed22f3` |
| 11 | Bump manual v0.2.0 | `frontend/package.json` | _(pendente neste último wip)_ |

### Validação local

- ✅ `uv run ruff check .` no backend: `All checks passed!`
- ✅ `pnpm exec tsc --noEmit` no frontend: sem erros
- ✅ `pnpm lint`: só warnings pré-existentes (nenhum no Footer.tsx, AppShell.tsx, next.config.ts)
- ✅ `pnpm build`: 23 páginas geradas sem erro; bundle `chunks/3255-*.js` contém `let $="0.2.0"` no chunk do Footer

### Decisões de execução vs plano

- Plan previa estender `backend/app/config.py` pra ler `APP_VERSION` de env. Descobri que Pydantic `BaseSettings` v2 já faz isso automaticamente (env name = field name uppercase). Só adicionei comentário documentando que em prod a env injetada sobrescreve o default `"0.1.0"`.
- Plan previa Service Worker poderia servir bundle antigo. Aplicado `generateBuildId: () => v${APP_VERSION}-${Date.now()}` que garante novo BuildID a cada build.
- Plan previa Footer com link pro anchor `#v021` no CHANGELOG. Simplifiquei pro link da raiz do CHANGELOG.md — funcionou tão bem quanto, sem o overhead de manter anchors estáveis.
- Bump manual de `0.1.0 → 0.2.0` aplicado **neste mesmo PR** porque a skill `/ship` que automatiza isso só está sendo introduzida agora. A partir do próximo PR o bump é automático.

### Pronto pra `/ship` ou push manual

Branch `feat/versionamento-visivel-app` tem 10 commits wip prontos. Próximo passo:
1. Você invoca `/ship "acrescentar versionamento visível na aplicação"` (ou `/start` que detecta diff e encadeia /ship).
2. Skill detecta tipo `feat:` → tentaria bump `0.1.0 → 0.2.0`, mas como já está em `0.2.0`, pula com `--no-bump` automaticamente.
3. Push da branch, abre PR, roda 5 camadas de gate.
4. Self-approval + squash merge.
5. `/deploy ship`: injeta `APP_VERSION=0.2.0` no Coolify backend, monitora build dos services, valida `/api/health` retorna `"version":"0.2.0"`.
6. Pós-deploy: rodapé em `app.hospitalsaomatheus.cloud` mostra `v0.2.0` clicável → CHANGELOG.md no GitHub.
