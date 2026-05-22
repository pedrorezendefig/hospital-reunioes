---
title: "fix(secretaria): permitir editar participantes na tela Editar reunião"
author: Pedro Rezende <pmrdef@gmail.com>
type: fix
issue: null
pr: 11
date_planned: 2026-05-22T16:56:00-03:00
date_deployed: null
sha: null
branch: fix/secretaria-editar-participantes
result: pending
status: in_progress
last_touched: 2026-05-22T16:56:00-03:00
plan_source: manual
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

**Tarefa atual:** ship + deploy (em andamento via `/ship --from-diff`).

- [x] 1. Adicionar `participantesIniciais: string[]` em `secretaria/nova/page.tsx` — snapshot dos vínculos do banco pra base de diff.
  - Critério: state existe, populado em `carregarReuniaoExistente` junto com `participantesSelecionados`.
- [x] 2. Remover o gate `{!editId && (...)}` em volta do `<MultiSelect />` — exibir bloco também em modo edição.
  - Critério: secretária abre "Editar reunião" e vê a lista pré-selecionada com os atuais participantes da reunião.
- [x] 3. `useEffect` que vigia `facilitadorId` e força sua presença em `participantesSelecionados` — facilitador não pode ser desmarcado.
  - Critério: trocar facilitador via combobox adiciona o novo na lista automaticamente; desmarcar via X re-injeta na próxima renderização.
- [x] 4. Em `handleSubmit`, modo edição: calcular `toAdd = atual − iniciais` e `toRemove = iniciais − atual − [facilitadorId]`. Chamar `POST /api/reunioes/:id/participantes` (lote) e `DELETE /api/reunioes/:id/participantes/:pid` em paralelo via `Promise.all`.
  - Critério: salvar reunião dispara as chamadas certas; backend envia convite só pros novos.
- [x] 5. Toast de aviso amigável (`warning`) se alguma sincronização de participantes falhar — não interromper o sucesso global do PATCH.
  - Critério: se 1 DELETE der erro, o restante segue, e o usuário vê toast informativo em vez de "Erro ao salvar".
- [x] 6. Atualizar a nota inline embaixo do MultiSelect — explicar que entrar = convite, sair = remoção.
- [x] 7. Validar `next lint` e `tsc --noEmit` (sem erros novos).
- [ ] 8. Ship via `/ship --from-diff` (commit + push + PR + 5 camadas de gate + merge squash + `/deploy ship`).
- [ ] 9. Verificação manual em produção: abrir uma reunião PROGRAMADA pela conta da secretária, adicionar um participante novo e remover outro, confirmar persistência e convite por email.

## Execução / Resultados

_(preenchido automaticamente por `/deploy ship` pós-health)_
