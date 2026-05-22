---
title: "fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub"
author: Pedro Rezende <pmrdef@gmail.com>
type: fix
issue: null
pr: 9
date_planned: 2026-05-22T15:41:35Z
date_deployed: null
sha: null
branch: fix/versao-footer-sem-link-direita
result: pending
status: in_progress
last_touched: 2026-05-22T15:41:35Z
plan_source: manual
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
- `<footer>` agora usa `text-right px-4` em vez de `text-center`.
- Versão exibida via `<span aria-label="Versão vX.Y.Z">`.

Deploy via `/ship --from-diff` (single-checkbox, change trivial).
