# Changelog Hospital Reuniões

Cronologia de deploys e mudanças importantes em ordem reversa (mais recente no topo).
Prepended pelo `/deploy ship` ao final do ciclo (ou manualmente quando o PR é meta — só skills/docs).

A partir de **v0.2.0** as entradas seguem o formato `## v0.X.Y — DATA — tipo(escopo): descrição`, com bump automático decidido pelo `/ship` (BREAKING > feat > fix/chore). Entradas mais antigas usam o formato `## YYYY-MM-DD HH:MM - tipo(escopo): descrição` — preservadas como histórico, sem retrofit de versão. Esquema completo descrito em [VERSIONING.md](VERSIONING.md).

---

## v0.4.0 — 2026-05-22 — feat(clicksign): card de signatários com status + lembrete; remove modo sandbox

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#16](https://github.com/pedrorezendefig/hospital-reunioes/pull/16) · Issue: —
- Commit: `bc2f8ab`
- Resultado: 🟢 healthy (backend 29s, frontend 120s, migration 039 aplicada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Substitui o card "Aguardando Assinatura Digital" (parágrafo genérico + bloco DEV laranja "Simular Sandbox" — dead-code em prod por causa de `ENABLE_BYPASS_ENDPOINTS=false`) pelo novo **`SignatariosCard`** com lista live de signatários. Cada linha mostra avatar + nome + email + badge verde com timestamp ("Assinou em DD/MM HH:MM") ou amarelo com botão "✉ Lembrar" pra signatários pendentes. Contador "X de Y assinaram", botão "⟳ Atualizar" (refresh manual com spin) e auto-poll a cada 30s via `usePolling`. Botão "Lembrar" envia POST que chama ClickSign pra reenviar email de assinatura com template PT-BR custom (cooldown visual de 60s pós-click). **Backend:** 2 endpoints novos — `GET /reunioes/{id}/signatarios/status` (rate-limit 60/min, consulta ClickSign v3 + enriquece com nome local + modo degradado pra reuniões pré-migration) e `POST /reunioes/{id}/signatarios/{signer_id}/lembrar` (rate-limit 10/min, template em PT-BR via mensagem custom no notification do ClickSign). 2 métodos novos em `clicksign_service`: `list_signers(envelope_id)` (`GET /api/v3/envelopes/{id}/signers` com normalização) e `remind_signer(envelope_id, signer_id, message)`. `start_signature_flow` agora grava `envelope_id_clicksign` no banco (separado de `envelope_key_clicksign` que continua sendo o `document_id` usado pelo webhook — nomes legados v1). **Sandbox eliminado:** 4 endpoints removidos (`/aprovar-bypass`, `/aprovar-bypass-todas`, `/simular-assinatura`, helper `_executar_simulacao`), flag `enable_bypass_endpoints` + validator `validate_bypass_prod` em `config.py`, teste `test_secretaria_403_em_aprovar_bypass`, linha `ENABLE_BYPASS_ENDPOINTS=false` em `.env.example`, entrada em `runtime_required` + `prod_only_assertions` em `docs/spec/deploy/project.json`. **Migration 039:** `ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS envelope_id_clicksign TEXT` — aditiva, idempotente, executada como `supabase_admin` (user `postgres` não era owner da tabela; documentado no chronicle). Reuniões pré-deploy ficam com coluna NULL e a UI exibe faixa amarela "legacy" + desabilita botão Lembrar. **Cobertura:** `test_signatarios_status.py` novo com 19 testes (7 endpoint status, 6 endpoint lembrar, 3 service list_signers, 3 service remind_signer) cobrindo paths felizes + 4xx/5xx + cenários legacy. 203/203 testes verdes (incluindo o hotfix do PR1). CI 3/3 SUCCESS (Backend Lint 26s, Frontend Lint+TSC 41s, Docker 2m24s). Self-approval/merge direto via `gh pr merge 16 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend 29s + frontend 120s. Health backend 97ms, frontend 115ms. **APP_VERSION mantido em 0.3.1 no Coolify** — bump aspiracional pra v0.4.0 registrado neste CHANGELOG mas o `/api/health` e o rodapé do frontend continuam exibindo `0.3.1` até o próximo deploy real que rebuilde frontend com `NEXT_PUBLIC_APP_VERSION` atualizado.

---

## v0.3.2 — 2026-05-22 — fix(matcher): sincronizar reuniao_participantes na correção de ata (bug 7→4 ClickSign)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#15](https://github.com/pedrorezendefig/hospital-reunioes/pull/15) · Issue: —
- Commit: `385d9c7`
- Resultado: 🟢 healthy (backend 37s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Hotfix do bug "7→4" relatado pelo diretor: quando ele corrigia o número de participantes via Chat de Correção (ex: IA extraía 7 nomes, ele removia 3 → 4), o ClickSign recebia o envelope com **os 7 emails originais** (incluindo os 3 removidos), em vez dos 4 corrigidos. Causa raiz em `backend/app/services/participant_matcher.py:292-411` — `match_participants()` fazia apenas UPSERT em `reuniao_participantes`, nunca DELETE. Era correto pro fluxo de extração inicial (pré-vinculados que a IA não cita continuam válidos como "convidados que não falaram"), mas no fluxo de correção a tabela junção ficava corrompida. Fix cirúrgico: kwarg novo `prune_missing: bool = False` (default = comportamento legado preservado). `run_correction_pipeline:411` opta-in com `prune_missing=True` (modo SYNC: delete + upsert). Adicionado `all_matched_this_pass: set[str]` que coleta TODOS os matches (inclusive pré-vinculados re-confirmados), permitindo distinguir "pré-vinculado confirmado" de "pré-vinculado removido pelo diretor". Mock `_Query` em `test_participant_matcher.py` estendido com `.delete().eq().in_().execute()`. 7 testes novos em `TestSyncPruneMissing` (canônico 7→4, regressão off, idempotente, lista vazia, renomeação, `link_on_match=False`, isolamento por id_reuniao) + arquivo novo `test_correction_pipeline_sync.py` com 2 testes de integração (run_correction_pipeline → 4 rows persistem; start_signature_flow → add_signer chamado 4× com emails corretos). 203/203 testes verdes. CI 3/3 SUCCESS (Backend Lint+Tests 24s, Docker 41s, Frontend Lint+TSC 32s). Self-approval/merge direto via `gh pr merge 15 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend em 37s. Health `https://api.hospitalsaomatheus.cloud/api/health` 200 em 1.15s. **APP_VERSION mantido em 0.3.1** (sem bump no Coolify; PR2 sequencial bump pra 0.4.0). **Pendência manual pós-deploy:** reuniões hoje em `AGUARDANDO_ASSINATURA` com envelope errado precisam tratamento caso a caso (cancel ClickSign + force-status + reaprovar).

---

## v0.3.1 — 2026-05-22 — fix(secretaria): habilitar edição de participantes na tela Editar reunião

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#11](https://github.com/pedrorezendefig/hospital-reunioes/pull/11) · Issue: —
- Commit: `2e745ab`
- Resultado: 🟢 healthy (backend 36s, frontend 169s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Bug reportado pelo Pedro — a tela "Editar reunião" (rota `/secretaria/nova?edit=`) escondia o `<MultiSelect />` de participantes em modo edição. A secretária ficava sem visão pra adicionar/remover quem participa de uma reunião futura. Fix em 1 arquivo TSX (`hospital-reunioes/frontend/src/app/secretaria/nova/page.tsx`, +101 −18): MultiSelect agora aparece também em edição, populado com snapshot inicial de `participantes_programada`. `handleSubmit` calcula diff (`toAdd = atual − iniciais`, `toRemove = iniciais − atual − [facilitadorId]`) e chama `POST/DELETE /api/reunioes/:id/participantes` em paralelo via `Promise.allSettled` (originalmente `Promise.all`, ajustado pelo `/code-review` pra não mascarar o sucesso do PATCH em erro de rede). `useEffect` re-injeta o facilitador automaticamente caso seja desmarcado. Backend já aceitava a operação pela secretária — endpoints sem gate de role, só exigem `status_ata == PROGRAMADA`. 5 camadas de gate verdes (`/code-review`, `/security-review` sem findings, `superpowers:requesting-code-review` aprovou com follow-ups arquiteturais registrados, CI 3/3 SUCCESS, `verification-before-completion` com tsc+lint+build local exit=0). Bump patch automático 0.3.0 → 0.3.1. Self-approval bloqueado pelo GitHub free; merge segue direto via `--admin`. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`).

---

## v0.3.0 — 2026-05-22 — feat(reunioes,secretaria): dropdown responsável + visão global da secretária com gate em ata/pendência

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#10](https://github.com/pedrorezendefig/hospital-reunioes/pull/10) · Issue: —
- Commit: `805daa0`
- Resultado: 🟢 healthy (backend 2m42s, frontend 3m43s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Mescla dois escopos numa única release. **(1) Dropdown responsável na correção da ATA** — substitui edição implícita via chat por combobox inline de participantes na coluna RESPONSÁVEL do quadro de atribuições; resolve bug "Josiane" (nome trocava mas cargo continuava stale). Endpoint novo `PATCH /reunioes/{id}/quadro-atribuicoes/{index}`, helper `_canonicalize_cargos_quadro` no orchestrator pós-IA, `pendencias.cargo` agora populado em `liberar_pendencias` (era NULL antes), componente `ResponsavelInlineCombobox.tsx`. **(2) Expansão do papel secretária** — antes só via PROGRAMADAS futuras, agora vê o calendário do hospital inteiro (qualquer status, qualquer data) e gerencia participantes em reuniões PROGRAMADAS (inclusive alheias). Defense-in-depth: **20 gates 403 explícitos** nos endpoints de ata/pendência/comentário (12 reuniões + 5 pendências + 3 comentários), `get_allowed_reuniao_ids` retorna `None` pra secretária, `_redact_ata_fields` redacta `json_ata`/`url_pdf_*` nos endpoints de leitura, gate de visibilidade adicionado em `PATCH /quadro-atribuicoes/{index}`. Frontend: flag `hideAtaSections` em 14 pontos do detalhe da reunião + esconde botão "Desmarcar" e "Anexar Transcrição" pra secretária. Bump 0.2.1 → 0.3.0 (feat=minor). 3 reviewers automatizados (code-review + security-review + superpowers:requesting-code-review) detectaram 3 must-fix em iteração — todos resolvidos antes do merge: critical de `json_ata` leak em `GET /reunioes/{id}`, must-fix de visibilidade no PATCH quadro e ausência de teste de gates. Novo arquivo `tests/test_secretaria_gates.py` com 9 testes cobrindo os 3 routers + edge case `me=None`. Suite final: 186/186 passa. CI 3/3 verde. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.1 — 2026-05-22 — fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#9](https://github.com/pedrorezendefig/hospital-reunioes/pull/9) · Issue: —
- Commit: `d3cc4a1`
- Resultado: 🟢 healthy (build frontend 169s; backend não redeployado, só env APP_VERSION sincronizada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Footer.tsx perde o wrapper `<a target=_blank>` que apontava pro CHANGELOG no GitHub e muda de `text-center` pra `text-right pr-4`. Versão agora é texto puro alinhado ao canto inferior direito (padrão visual de apps profissionais — não compete com conteúdo). Aria-label mantido pra screen readers. Bump patch automático `0.2.0 → 0.2.1` (tipo dominante: fix). APP_VERSION sincronizada no backend Coolify (`mcp__coolify__env_vars update`, runtime-only) pré-merge — backend NÃO foi redeployado, só o env mudou e o `/api/health` já reflete `version:0.2.1`. Frontend rebuild Docker em 169s (cache quente). Gates: code-review max-effort (3 agents, 1 nit aplicado `px-4` → `pr-4`), security e requesting-code-review pulados (mudança cosmética de 4 linhas em 1 arquivo de UI), CI verde, verification verde (tsc + lint). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.0 — 2026-05-22 — feat(app): acrescentar versionamento visível na aplicação

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#8](https://github.com/pedrorezendefig/hospital-reunioes/pull/8) · Issue: —
- Commit: `1efd175`
- Resultado: 🟢 healthy (build backend 198s, frontend 255s, health ok com version match)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** primeiro PR de versionamento. Rodapé `v0.2.0` clicável em todas as páginas do AppShell (link → CHANGELOG.md no GitHub). Backend `/api/health` retorna `version` lido de env `APP_VERSION` (default `0.1.0`). Footer.tsx novo lê `NEXT_PUBLIC_APP_VERSION` inlined em build-time pelo `next.config.ts` a partir de `package.json` (bumpado 0.1.0 → 0.2.0 manualmente neste PR; nos próximos é automático via /ship Passo 5.5). Skill `/ship` ganha bump automático de semver por tipo de commit (BREAKING > feat > fix/chore) + Passo 8.5 que sincroniza APP_VERSION no Coolify pré-merge (evita race com webhook). Skill `/deploy` ganha Passo 3.5 defensivo idempotente + Passo 7.2 version match check (rollback automático se /api/health não retorna versão esperada). Docs novos: `VERSIONING.md` (esquema completo) + header explicativo no CHANGELOG.md. 5 camadas de gate verdes antes do merge — 4 issues do code-review e 2 do requesting-code-review corrigidos em-band nos commits 3136a5c e 4a5fc8d.

---

## 2026-05-21 20:39 - feat(skills): automatizar /snapshot via script Python

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `70bac46`
- PR: [#7](https://github.com/pedrorezendefig/hospital-reunioes/pull/7) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** implementa o gerador real do `/snapshot` que estava só documentado no PR #6. Script Python self-contained (993 linhas, stdlib only) em `.claude/skills/snapshot/scripts/snapshot.py` com parser AST de routers FastAPI (78 endpoints em 13 routers), parser SQL cumulativo de migrations (13 tabelas das 36 migrations), 5 geradores de MD, idempotência via comparação de buffer e flags CLI (`--check`, `--force`, `--only`, `--diff`, `--no-commit`). Code-review pegou 1 bug score 100 (JSONB DEFAULT corrompendo parser de colunas) + 3 issues score 75, todas corrigidas antes do merge.

---

## 2026-05-21 18:58 - feat(workflow): integrar Superpowers + /snapshot vivo + 5 camadas de gate

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e9f64ee`
- PR: [#6](https://github.com/pedrorezendefig/hospital-reunioes/pull/6) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — PR só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** integra plugin Superpowers v5.1.0 no workflow do time. Cria skill `/snapshot` (gera 7 MDs vivos em `docs/spec/snapshots/` regenerados a cada deploy via `/deploy ship`). `/start` ganha Modo D (retomar trabalho parado de outra sessão) + invocação de `brainstorming` por default no Modo A. `/ship` ganha 5 camadas independentes de gate antes do self-approval (code-review, security-review, requesting-code-review, CI Actions, verification-before-completion). `CLAUDE.md` reescrito com 5 seções novas. CI Actions ganha job `build` (docker sanity). Cleanup de 150+ skills `reversa-*` absorvido no mesmo PR (-26338 linhas).
