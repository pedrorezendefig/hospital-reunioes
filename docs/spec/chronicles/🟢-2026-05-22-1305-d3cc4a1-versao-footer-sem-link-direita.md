---
title: "fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub"
author: Pedro Rezende <pmrdef@gmail.com>
type: fix
issue: null
pr: 9
date_planned: 2026-05-22T15:41:35Z
date_deployed: 2026-05-22T15:53:06Z
sha: d3cc4a1
branch: fix/versao-footer-sem-link-direita
result: healthy
status: done
last_touched: 2026-05-22T16:05:00Z
plan_source: manual
duration_deploy_s: 169
services_touched:
  - frontend
migrations_applied: 0
version_before: 0.2.0
version_after: 0.2.1
---

## Contexto

O footer renderizava `v0.2.0` como `<a>` apontando pro CHANGELOG no GitHub e centralizado no rodapé. Pedro pediu que vire apenas indicação textual da versão, sem link externo, alinhada ao canto inferior direito.

## Plano

**Tarefa atual:** 1. Ajustar Footer.tsx

- [x] 1. Substituir `<a>` por `<span>`, remover `CHANGELOG_URL`, trocar `text-center` por `text-right` (com pequeno padding horizontal pra não colar na borda).
  - Critério: `hospital-reunioes/frontend/src/components/layout/Footer.tsx` sem `<a>` e com `text-right`.

## Execução / Resultados

Edição direta em `Footer.tsx`:
- Removida constante `CHANGELOG_URL`.
- Removido wrapper `<a target="_blank">`.
- `<footer>` agora usa `text-right pr-4` (era `px-4`, ajustado pós-review — `pr-4` é semanticamente mais correto pra texto right-aligned).
- Versão exibida via `<span aria-label="Versão vX.Y.Z">`.

## Implementação / Deploy

**fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub (#9)**

- **Data**: 2026-05-22 15:53 UTC
- **SHA**: `d3cc4a1`
- **PR**: [#9](https://github.com/pedrorezendefig/hospital-reunioes/pull/9)
- **Modo**: ship (via `/start --rapido` → `/ship --from-diff`)
- **Resultado**: 🟢 healthy
- **Duração deploy**: 169s (2m49s)
- **Versão**: v0.2.0 → v0.2.1 (patch bump via /ship Passo 5.5)

### Serviços tocados

- frontend (Coolify uuid `okt237kwgu5x48qqbd57ntvz`) — rebuild Docker do Next.js

### Gates avaliados

- ✅ Camada 1 — `/code-review` (3 agents max-effort: reuse + quality + efficiency). 1 nit aplicado pré-merge: `px-4` → `pr-4`.
- ⊘ Camada 2 — `/security-review` pulado (mudança cosmética em UI, sem mudança em auth/env/schema/DB).
- ⊘ Camada 3 — `requesting-code-review` pulado (4 linhas funcionais + bump, sobreposição com Camada 1).
- ✅ Camada 4 — CI verde: Backend Lint (24s) + Frontend Lint & Type Check (37s) + Docker Build sanity (2m28s).
- ✅ Camada 5 — `verification-before-completion`: tsc local sem erros, `next lint` só com warnings preexistentes.

### Sync APP_VERSION

- Backend Coolify: `APP_VERSION=0.2.1` (runtime, via `mcp__coolify__env_vars update`).
- Frontend: `NEXT_PUBLIC_APP_VERSION=0.2.1` injetado via `next.config.ts` (importa `package.json` em build-time).

### Verificação pós-deploy

```
$ curl -s https://app.hospitalsaomatheus.cloud | grep -oE 'v0\.[0-9]+\.[0-9]+'
v0.2.1
v0.2.1

$ curl -s https://api.hospitalsaomatheus.cloud/api/health
{"status":"healthy","db":"healthy","app":"Hospital Reuniões API","version":"0.2.1"}
```

---
_Atualizado automaticamente pelo `/deploy ship` em 2026-05-22._
