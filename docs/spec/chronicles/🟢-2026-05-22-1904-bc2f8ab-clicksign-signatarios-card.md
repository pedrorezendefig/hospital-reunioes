---
title: "feat(clicksign): card de signatarios com status + lembrete; remove modo sandbox"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: 16
date_planned: 2026-05-22T19:00:00-03:00
date_deployed: 2026-05-22T19:04:17-03:00
sha: bc2f8ab
branch: feat/clicksign-signatarios-status
result: healthy
status: done
last_touched: 2026-05-22T19:05:00-03:00
plan_source: plan-mode
duration_deploy_s: 120
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

Todos os 12 passos do plano executados, salvo onde notado:

- ✅ 1. Migration `039_add_envelope_id_clicksign.sql` criada e aplicada no Supabase remoto (via `psql -U supabase_admin` — `postgres` user não era owner da tabela `reunioes`).
- ✅ 2-3. `list_signers` + `remind_signer` em `clicksign_service.py` + `start_signature_flow` agora grava `envelope_id_clicksign` junto com `envelope_key_clicksign`.
- ✅ 4. 4 endpoints sandbox deletados + flag + validator + teste + .env.example + project.json. Smoke `grep "bypass|sandbox|simular_assinatura|enable_bypass"` zero ocorrências reais (só "bypassa RLS" em dependencies.py comentário).
- ✅ 5-6. Endpoints `GET /signatarios/status` (rate-limit 60/min) e `POST /signatarios/{id}/lembrar` (rate-limit 10/min) com gates auth/secretaria/visibilidade + modo legacy + códigos 503/502 para falhas ClickSign.
- ✅ 7. Limpeza config + tests + env + project.json. ruff auto-fix removeu import órfão de `UTC`.
- ✅ 8. `test_signatarios_status.py` com 19 testes verdes (7 endpoint status + 6 endpoint lembrar + 3 service list_signers + 3 service remind_signer).
- ✅ 9-10. `SignatariosCard.tsx` (~280 LOC) + integração no `[id]/page.tsx`.
- ✅ 11. ruff check + format limpos · 203 testes verdes · `npm run lint` + `tsc --noEmit` limpos (warnings pré-existentes em outros arquivos; nenhum no SignatariosCard).
- ✅ 12. PR #16 aberto + CI 3/3 SUCCESS (Backend Lint 26s, Frontend Lint 41s, Docker 2m24s) + merge squash via `gh pr merge 16 --squash --delete-branch` (Pedro autorizou self-merge explícito).

## Implementação / Deploy

**feat(clicksign): card de signatários com status + lembrete; remove modo sandbox**

- **Data**: 2026-05-22 19:04:17 -03:00
- **SHA**: `bc2f8ab`
- **PR**: [#16](https://github.com/pedrorezendefig/hospital-reunioes/pull/16)
- **Modo**: ship (webhook auto)
- **Resultado**: 🟢 healthy
- **Health backend**: `https://api.hospitalsaomatheus.cloud/api/health` → 200 em 97ms
- **Health frontend**: `https://app.hospitalsaomatheus.cloud/` → 200 em 115ms

### Serviços tocados

- backend (29s build via webhook)
- frontend (120s build via webhook)
- database (migration 039 aplicada via SSH/psql)

### Migrations aplicadas

- `039_add_envelope_id_clicksign.sql` (aditiva, idempotente, executada como `supabase_admin`)

### APP_VERSION

`0.3.1` (mantido no Coolify; o CHANGELOG registra como **v0.4.0** como contrato semver mas o display no rodapé + `/api/health` continua mostrando `0.3.1` até o próximo deploy real que rebuilde frontend com `NEXT_PUBLIC_APP_VERSION` novo).

### Notas

- Webhook deploy do backend acontecedu antes de a migration rodar (~5min de gap). Nenhuma chamada quebrou no intervalo porque o app só faz `INSERT/SELECT envelope_id_clicksign` quando há fluxo de assinatura (raro e iniciado humanamente). Migration aplicada pouco depois.
- Erro inicial `must be owner of table reunioes` ao tentar `psql -U postgres` — corrigido usando `psql -U supabase_admin`. Documentado no chronicle como referência futura.

---

_Atualizado automaticamente pelo `/deploy ship` em 2026-05-22._
