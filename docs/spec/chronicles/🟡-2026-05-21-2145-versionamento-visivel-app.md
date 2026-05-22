---
title: "feat(app): acrescentar versionamento visível na aplicação + release notes nos docs"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: null
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

Estratégia escolhida (ver `/Users/pedrorezende/.claude/plans/eu-preciso-colocar-um-smooth-falcon.md`):
- Semver com bump **automático** pelo `/ship` baseado no tipo do commit (BREAKING > feat > fix/chore/refactor).
- Fonte da verdade: `frontend/package.json`. Backend espelha via env `APP_VERSION`.
- Rodapé no fim do `<main>` (não fixed, não compete com BottomNav mobile).
- Skill `/deploy` injeta `APP_VERSION` no Coolify pré-build via `mcp__coolify__bulk_env_update`.

## Plano

**Tarefa atual:** 6. Docs: criar `VERSIONING.md`

- [x] 1. Criar branch + chronicle 🟡
  - Critério: `git branch --show-current` retorna `feat/versionamento-visivel-app`; arquivo deste plano existe e está commitado
- [x] 2. Backend: Settings lê `APP_VERSION` de env
  - Critério: `curl localhost:8000/api/health` retorna `"version":"0.1.0"` (fallback); `APP_VERSION=0.2.0 uvicorn...` retorna `"version":"0.2.0"`
- [x] 3. Frontend: expor `NEXT_PUBLIC_APP_VERSION` em `next.config.ts`
  - Critério: `pnpm build` produz bundle com `0.1.0` inlined; `generateBuildId` retorna versão
- [x] 4. Frontend: criar `Footer.tsx`
  - Critério: componente novo em `frontend/src/components/layout/Footer.tsx` exporta default function Footer; texto `v{version}` clicável → CHANGELOG no GitHub
- [x] 5. Frontend: encaixar `<Footer />` em `AppShell.tsx`
  - Critério: rodapé aparece ao rolar até o fim em qualquer página local; BottomNav mobile não fica por cima
- [ ] 6. Docs: criar `VERSIONING.md`
  - Critério: `docs/spec/VERSIONING.md` existe; explica esquema, regra de bump, link versão↔SHA
- [ ] 7. Docs: header explicativo no `CHANGELOG.md`
  - Critério: 3-4 linhas no topo descrevendo formato novo `## v0.X.Y`; entradas antigas (formato `## YYYY-MM-DD HH:MM`) intocadas
- [ ] 8. Skill `/ship`: adicionar bump automático de semver
  - Critério: passo "Bump de versão" documentado em `.claude/skills/ship/SKILL.md`; algoritmo lê tipo dominante (BREAKING > feat > fix/chore), edita `package.json`, commit `chore(release): bump vX.Y.Z`
- [ ] 9. Skill `/deploy`: injetar `APP_VERSION` no Coolify pré-deploy
  - Critério: passo documentado em `.claude/skills/deploy/SKILL.md`; `mcp__coolify__bulk_env_update` setado pré-`mcp__coolify__deploy`; pós-health valida match
- [ ] 10. Validar build local
  - Critério: `pnpm build` no frontend e `ruff check` no backend passam sem erro; `/atualizar-app` opcional pra ver rodapé no localhost:3000

## Execução / Resultados

(será preenchido conforme implementação avança)
