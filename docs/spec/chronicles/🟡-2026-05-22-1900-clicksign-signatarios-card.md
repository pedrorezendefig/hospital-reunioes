---
title: "feat(clicksign): card de signatarios com status + lembrete; remove modo sandbox"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: null
date_planned: 2026-05-22T19:00:00-03:00
date_deployed: null
sha: null
branch: feat/clicksign-signatarios-status
result: pending
status: in_progress
last_touched: 2026-05-22T19:00:00-03:00
plan_source: plan-mode
---

## Contexto

Hoje o card "Aguardando Assinatura Digital" mostra só envelope_id + bloco DEV laranja (botão Simular Sandbox, dead-code em prod). Diretor precisa ir até o ClickSign pra saber quem assinou e quem falta — fricção repetida em toda ata.

Este PR:

1. **Remove definitivamente o modo sandbox/DEV** — 4 endpoints (aprovar-bypass, aprovar-bypass-todas, simular-assinatura, _executar_simulacao), flag `ENABLE_BYPASS_ENDPOINTS` + validator, teste relacionado em test_secretaria_gates, linha em .env.example, assertion em project.json.
2. **Substitui o bloco visual** pelo novo `SignatariosCard` com lista de signatários (verde = assinou + timestamp · amarelo = pendente + botão "Lembrar"), contador "X de Y", botão "Atualizar" (refresh manual + auto-poll 30s via `usePolling`).
3. **Adiciona endpoint** `GET /reunioes/{id}/signatarios/status` que consulta ClickSign em tempo real (rate-limit 60/min).
4. **Adiciona endpoint** `POST /reunioes/{id}/signatarios/{signer_id}/lembrar` que reenvia o email de assinatura pro signer pendente, com template custom em PT-BR (rate-limit 10/min).
5. **Estende clicksign_service** com `list_signers(envelope_id)` e `remind_signer(envelope_id, signer_id, message)`.
6. **Migration 039** adiciona coluna `envelope_id_clicksign` (separada de `envelope_key_clicksign` que era, na verdade, o document_id usado pelo webhook). Reuniões pré-PR2 caem em modo degradado (faixa amarela + lista local sem timestamps reais).

Plano completo em `~/.claude/plans/image-1-eu-preciso-tranquil-seal.md`.

## Plano

**Tarefa atual:** 1. Migration 039 + clicksign_service

- [ ] 1. Migration `039_add_envelope_id_clicksign.sql`
  - Critério: ALTER TABLE aditivo + comment
- [ ] 2. `clicksign_service.list_signers(envelope_id)` + `remind_signer(envelope_id, signer_id, message)`
  - Critério: padrão idêntico aos GETs existentes (`get_signed_document`), retorno normalizado, tratamento httpx
- [ ] 3. Update `clicksign_service.start_signature_flow` pra gravar `envelope_id_clicksign`
  - Critério: 1 linha extra no update final, sem quebrar webhook
- [ ] 4. Deletar 4 endpoints sandbox em `routers/reunioes.py`
  - Critério: aprovar-bypass, aprovar-bypass-todas, simular-assinatura, _executar_simulacao + grep zero
- [ ] 5. Adicionar endpoint `GET /reunioes/{id}/signatarios/status`
  - Critério: gates auth/secretaria/visibilidade + modo legacy + 503 em falha ClickSign
- [ ] 6. Adicionar endpoint `POST /reunioes/{id}/signatarios/{signer_id}/lembrar`
  - Critério: rate-limit 10/min + template PT-BR + 502 em falha ClickSign
- [ ] 7. Limpeza config.py + tests + .env.example + project.json
  - Critério: `enable_bypass_endpoints` + `validate_bypass_prod` removidos; teste do bypass deletado; .env e project.json sem referência
- [ ] 8. Criar `test_signatarios_status.py` (endpoint status + lembrete + service)
  - Critério: ≥10 testes verdes cobrindo paths felizes + 4xx/5xx
- [ ] 9. Criar `frontend/src/components/reunioes/SignatariosCard.tsx`
  - Critério: lista + contador + Atualizar + Lembrar por linha pendente + skeleton + erro + legacy_warning
- [ ] 10. Atualizar `frontend/src/app/reunioes/[id]/page.tsx`
  - Critério: import novo + delete handleAprovarBypass + delete handleSimularAssinatura + delete botão bypass + substitui bloco DEV pelo `<SignatariosCard>`
- [ ] 11. Rodar `ruff check && ruff format --check && pytest` + `npm run lint && tsc --noEmit`
  - Critério: 0 erros lint + suite verde + smoke grep "bypass|sandbox|simular_assinatura|enable_bypass" zerado
- [ ] 12. Commit + push + abrir PR (rebase sobre main após PR1 mergeado)
  - Critério: PR aberto + CI verde + chronicle 🟡 vira 🟢 no /deploy ship

## Edge cases cobertos

- ClickSign down → 503 + lista cacheada na UI
- Reunião pré-PR2 sem envelope_id → modo degradado (faixa amarela + Lembrar disabled)
- Rate limit ClickSign (60/min) vs nosso polling 30s × 10 usuários = 20/min — folgado
- Lembrar clicado em rajada → backend rate-limit 10/min + UI esconde botão 60s pós-sucesso
- Drift ClickSign > local → ClickSign é source of truth, enriquece com nome local
- Polling após usuário sair → cleanup automático do `useEffect` (padrão React)

## Execução / Resultados

_(preenchido durante o ship)_
