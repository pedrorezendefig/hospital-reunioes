---
title: "fix(secretaria): habilitar edição de participantes na tela Editar reunião"
author: Pedro Rezende <pmrdef@gmail.com>
type: fix
issue: null
pr: 11
date_planned: 2026-05-22T16:56:00-03:00
date_deployed: 2026-05-22T17:15:13-03:00
sha: 2e745ab
branch: fix/secretaria-editar-participantes
result: healthy
status: done
last_touched: 2026-05-22T17:15:13-03:00
plan_source: manual
duration_deploy_s: 169
services_touched:
  - backend
  - frontend
migrations_applied: 0
app_version: "0.3.1"
---

## Contexto

A secretária abre `/secretaria` → clica no ícone de lápis ao lado de uma reunião → cai em `/secretaria/nova?edit=<id>` (rotulada na UI como **"Editar reunião"**). Nessa tela ela vê título, data, hora, tipo, facilitador, pauta — mas **não vê participantes**. Pra mexer em participantes ela teria que ir manualmente pelo Calendário → reunião → modo PROGRAMADA, caminho que não está sinalizado.

Raiz no código (`frontend/src/app/secretaria/nova/page.tsx`):

- O bloco `<MultiSelect ... Participantes />` estava envolto em `{!editId && (...)}` — só aparecia em criação. Linha 336 da versão antiga.
- O submit em modo edição não enviava `participante_ids` ao PATCH `/api/reunioes/:id`. Linha 188-190.
- A nota inline pedia "use a tela de edição da reunião" — mas a secretária *está* na tela de edição da reunião, do ponto de vista dela. Texto enganador.

Backend já aceita a operação pela secretária:

- `POST /api/reunioes/:id/participantes` e `DELETE /api/reunioes/:id/participantes/:pid` em `backend/app/routers/reunioes.py:496-547` não têm gate de role — só exigem `status_ata == "PROGRAMADA"`.
- `POST` envia convite por email automaticamente apenas pra IDs realmente novos (linha 511-516 / 523-524).

## Plano

**Tarefa atual:** ✅ deploy 2e745ab healthy.

- [x] 1. Adicionar `participantesIniciais: string[]` em `secretaria/nova/page.tsx` — snapshot dos vínculos do banco pra base de diff.
- [x] 2. Remover o gate `{!editId && (...)}` em volta do `<MultiSelect />` — exibir bloco também em modo edição.
- [x] 3. `useEffect` que vigia `facilitadorId` e força sua presença em `participantesSelecionados` — facilitador não pode ser desmarcado.
- [x] 4. Em `handleSubmit`, modo edição: calcular `toAdd = atual − iniciais` e `toRemove = iniciais − atual − [facilitadorId]`. Chamar `POST /api/reunioes/:id/participantes` (lote) e `DELETE /api/reunioes/:id/participantes/:pid` em paralelo via `Promise.allSettled` (originalmente `Promise.all`, ajustado pelo code-review pra não mascarar sucesso do PATCH em erro de rede).
- [x] 5. Toast `warning` se alguma sincronização falhar — não interromper o sucesso global do PATCH.
- [x] 6. Atualizar a nota inline embaixo do MultiSelect — explicar que entrar = convite, sair = remoção.
- [x] 7. Validar `next lint` e `tsc --noEmit` (sem erros novos).
- [x] 8. Ship via `/ship --from-diff` (commit + push + PR + 5 camadas de gate + merge squash + `/deploy ship`).
- [ ] 9. Verificação manual em produção: abrir uma reunião PROGRAMADA pela conta da secretária, adicionar um participante novo e remover outro, confirmar persistência e convite por email.

## Execução / Resultados

PR #11 mergeado em squash como commit `2e745ab`. Bump de versão patch: `0.3.0 → 0.3.1`.

### Gates (5 camadas verdes)

1. **`/code-review`** — 1 finding endereçado: `Promise.all` mascarava o sucesso do PATCH em erro de rede em qualquer fetch de sync de participantes. Trocado por `Promise.allSettled` no commit `f3b61f2`.
2. **`/security-review`** — sem findings. Diff é client-side TSX sem novas surfaces (autorização gateada no backend, sem injeção de HTML).
3. **`superpowers:requesting-code-review`** — verdict "Ready to merge: Yes". Follow-ups arquiteturais registrados como dívida.
4. **CI Actions** — 3/3 SUCCESS no commit final `f3b61f2`: Backend Lint+Tests · Frontend Lint+Type · Docker Build sanity.
5. **`verification-before-completion`** — `tsc --noEmit` exit 0, `npm run lint` exit 0, `npm run build` exit 0 com 23 páginas geradas (rota `/secretaria/nova` em 6.09 kB).

### Deploy

- **Backend rebuild:** 36s (commit `2e745ab` via webhook Coolify às 20:12:24 UTC, finished 20:13:00 UTC).
- **Frontend rebuild:** 2m49s (started 20:12:24 UTC, finished 20:15:13 UTC).
- **APP_VERSION sync:** Coolify env `APP_VERSION=0.3.1` setado pré-merge no Passo 8.5 do `/ship` pra evitar race com webhook.
- **Health pós-deploy:**
  - `GET https://api.hospitalsaomatheus.cloud/api/health` → `200 {"status":"healthy","db":"healthy","app":"Hospital Reuniões API","version":"0.3.1"}` em 76ms.
  - `GET https://app.hospitalsaomatheus.cloud` → 200 em 111ms, footer mostrando `v0.3.1`.
- **Sem migrations.** Sem rollback. Sem env changes além do APP_VERSION.

### Follow-ups gerados pelo code-review

1. **Backend PATCH deveria promover novo facilitador em `reuniao_participantes`** — hoje só `/transferir-facilitador` (super_admin) faz upsert. Frontend cobre via `useEffect` + `toAdd`, mas é dívida arquitetural que vai ressurgir em outras telas. Replicar a lógica do upsert no PATCH fecharia o gap.
2. **MultiSelect compartilhado com `lockedValues: string[]`** — eliminaria o blink visual de 1 frame quando a secretária tenta desmarcar o chip do facilitador atual e dá feedback explícito ("não pode remover").
3. **Smoke test manual em prod (tarefa #9 acima)** — pendente; incluir os 3 edge cases mapeados pelo subagent: (a) trocar facilitador onde o novo já era participante; (b) trocar + remover antigo via UI; (c) tentar desmarcar facilitador atual.

### Notas operacionais

- Houve sessão paralela do Claude rodando trabalho em outra branch (`feature/planejamento-estrutura` → PR #12). O squash merge do PR #12 acabou trazendo o filename renomeado do chronicle (`🟡 → 🟢`) sem o conteúdo atualizado. Os artefatos finais de deploy (state.json, history.json, CHANGELOG, conteúdo do chronicle) foram re-aplicados em `main` num commit subsequente fora do ciclo `/deploy ship` automatizado.
