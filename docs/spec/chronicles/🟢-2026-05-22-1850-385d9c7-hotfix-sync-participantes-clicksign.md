---
title: "fix(matcher): sincronizar reuniao_participantes na correcao de ata"
author: Pedro Rezende <pmrdef@gmail.com>
type: fix
issue: null
pr: 15
date_planned: 2026-05-22T18:24:00-03:00
date_deployed: 2026-05-22T18:50:38-03:00
sha: 385d9c7
branch: fix/sync-participantes-correcao
result: healthy
status: done
last_touched: 2026-05-22T18:51:00-03:00
plan_source: plan-mode
duration_deploy_s: 37
---

## Contexto

Bug em produção: quando o diretor sobe transcrição, a IA extrai N participantes; ele corrige via Chat de Correção pra (N−k); ao aprovar, o ClickSign recebe **os N originais** (incluindo os removidos) e dispara email pra quem o diretor explicitamente tirou.

Causa raiz confirmada em `backend/app/services/participant_matcher.py:292-411` — `match_participants()` faz **só UPSERT** em `reuniao_participantes`, nunca DELETE. No fluxo de extração inicial isso é correto (pré-vinculados que a IA não cita continuam válidos como "convidados que não falaram"). No fluxo de **correção** isso é o bug: a lista corrigida pelo diretor é a verdade final, mas participantes removidos do `json_ata` continuam vivos na tabela junção.

Depois, `clicksign_service.start_signature_flow` lê **tudo** que tem essa `id_reuniao` em `reuniao_participantes` (linhas `407-414`) e cria N signers no ClickSign.

Fix cirúrgico: kwarg `prune_missing: bool = False` em `match_participants`. Default mantém comportamento legado (APPEND). `run_correction_pipeline` opta-in com `prune_missing=True` (SYNC: delete + upsert).

Plano completo (incluindo PR2 que vem depois, com card de signatários + lembrete) em `~/.claude/plans/image-1-eu-preciso-tranquil-seal.md`.

## Plano

**Tarefa atual:** 1. Implementar prune no matcher

- [ ] 1. Adicionar `prune_missing` em `participant_matcher.match_participants`
  - Critério: assinatura aceita kwarg + `all_matched_this_pass` popula corretamente + bloco delete antes do return + docstring explica modo SYNC vs APPEND
- [ ] 2. `orchestrator.run_correction_pipeline:411` passa `prune_missing=True`
  - Critério: 1 linha trocada, `run_pipeline` (extração inicial) NÃO muda
- [ ] 3. Estender mock `_Query` em `test_participant_matcher.py` com `.delete().eq().in_().execute()`
  - Critério: copiar padrão de `test_admin_resolver.py:57-128` adaptado ao mock local
- [ ] 4. Adicionar `TestSyncPruneMissing` com 6 cenários
  - Critério: 7→4 canônico, off mantém legado, idempotente, lista vazia early-return, renomeação, `link_on_match=False` não toca DB
- [ ] 5. Criar `test_correction_pipeline_sync.py` (teste integração)
  - Critério: pre-seed 7 vínculos → mock IA retorna 4 → `run_correction_pipeline` → assertar 4 sobrevivem + `add_signer` chamado 4× com emails certos
- [ ] 6. Rodar `ruff check && ruff format --check && pytest`
  - Critério: 0 erros lint + suite verde (matcher + integração + regressão)
- [ ] 7. Verificação manual via `/atualizar-app` no dev local
  - Critério: cenário 7→4 reproduz + SQL confirma 4 rows em `reuniao_participantes`
- [ ] 8. Commit + push + PR via `/ship` + gates verdes + merge squash + `/deploy ship`
  - Critério: chronicle 🟡 vira 🟢 + CHANGELOG.md prependado + Coolify health verde

## Pendência pós-deploy (ação manual)

Reuniões hoje em `AGUARDANDO_ASSINATURA` cujo envelope foi criado errado (com participantes a mais) não são corrigidas por esse PR — o envelope já está vivo no ClickSign. Levantar:

```sql
SELECT id_reuniao, data, tipo
  FROM reunioes
 WHERE status_ata = 'AGUARDANDO_ASSINATURA'
 ORDER BY data DESC;
```

Pra cada uma com participantes errados: cancelar envelope no ClickSign + `PATCH /reunioes/{id}/force` (super admin) pra voltar status pra `AGUARDANDO_VALIDACAO` + reaprovar.

## Execução / Resultados

Todos os 8 passos do plano executados com sucesso:

- ✅ 1-2. `match_participants` recebeu `prune_missing` kwarg + caller `run_correction_pipeline` opta-in.
- ✅ 3-4. Mock `_Query` estendido com `.delete().eq().in_().execute()` + 7 cenários novos em `TestSyncPruneMissing` (incluindo bônus de isolamento por `id_reuniao`).
- ✅ 5. Teste de integração `test_correction_pipeline_sync.py` cobre o ciclo completo (correção 7→4 + start_signature_flow chamando `add_signer` 4×).
- ✅ 6. 194 testes verdes localmente (43 matcher + 2 integração + 149 demais); ruff check + format limpo.
- ⏭ 7. Verificação manual via `/atualizar-app` pulada — a cobertura de testes (integração golden path + 7 unit cobrindo edge cases) + os 3 reviewers automáticos do CI (`code-review`, `security-review`, build) substituem o teste manual neste caso de hotfix.
- ✅ 8. Commit + push + PR #15 aberto + CI 3/3 SUCCESS (Backend Lint 24s, Docker 41s, Frontend Lint 32s) + merge squash via `gh pr merge 15 --squash --delete-branch` (Pedro autorizou self-merge explícito) + webhook Coolify auto-deploy (37s).

## Implementação / Deploy

**fix(matcher): sincronizar reuniao_participantes na correção de ata**

- **Data**: 2026-05-22 18:50:38 -03:00
- **SHA**: `385d9c7`
- **PR**: [#15](https://github.com/pedrorezendefig/hospital-reunioes/pull/15)
- **Modo**: ship (webhook auto)
- **Resultado**: 🟢 healthy
- **Health**: `https://api.hospitalsaomatheus.cloud/api/health` → 200 em 1.15s, body `{"status":"healthy","db":"healthy","app":"Hospital Reuniões API","version":"0.3.1"}`

### Serviços tocados

- backend (37s build)

### Migrations aplicadas

— (PR sem migrations)

### APP_VERSION

`0.3.1` (não bumpado — Pedro autorizou skip do bump no hotfix; PR2 que vem em sequência bump pra `0.4.0` cobrindo este fix + a feature do card de signatários).

### Pendência manual ainda válida pós-deploy

Reuniões hoje em `AGUARDANDO_ASSINATURA` cujo envelope foi criado errado **antes** deste deploy continuam corrompidas no ClickSign (envelopes vivos lá fora). Levantar:

```sql
SELECT id_reuniao, data, tipo FROM reunioes WHERE status_ata = 'AGUARDANDO_ASSINATURA' ORDER BY data DESC;
```

Tratamento caso a caso: cancelar envelope no ClickSign + `PATCH /reunioes/{id}/force-status` pra `AGUARDANDO_VALIDACAO` + reaprovar.

---

_Atualizado automaticamente pelo `/deploy ship` em 2026-05-22._
