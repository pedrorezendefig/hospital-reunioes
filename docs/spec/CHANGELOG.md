# Changelog Hospital Reuniões

Cronologia de deploys e mudanças importantes em ordem reversa (mais recente no topo).
Prepended pelo `/deploy ship` ao final do ciclo (ou manualmente quando o PR é meta — só skills/docs).

A partir de **v0.2.0** as entradas seguem o formato `## v0.X.Y — DATA — tipo(escopo): descrição`, com bump automático decidido pelo `/ship` (BREAKING > feat > fix/chore). Entradas mais antigas usam o formato `## YYYY-MM-DD HH:MM - tipo(escopo): descrição` — preservadas como histórico, sem retrofit de versão. Esquema completo descrito em [VERSIONING.md](VERSIONING.md).

---

## v0.3.1 — 2026-05-22 — fix(secretaria): habilitar edição de participantes na tela Editar reunião

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#11](https://github.com/pedrorezendefig/hospital-reunioes/pull/11) · Issue: —
- Commit: `2e745ab`
- Resultado: 🟢 healthy (backend 36s, frontend 169s)
- Detalhe: [chronicles/🟢-2026-05-22-1715-2e745ab-secretaria-editar-participantes.md](chronicles/🟢-2026-05-22-1715-2e745ab-secretaria-editar-participantes.md)

**Resumo:** Bug reportado pelo Pedro — a tela "Editar reunião" (rota `/secretaria/nova?edit=`) escondia o `<MultiSelect />` de participantes em modo edição. A secretária ficava sem visão pra adicionar/remover quem participa de uma reunião futura. Fix em 1 arquivo TSX (`hospital-reunioes/frontend/src/app/secretaria/nova/page.tsx`, +101 −18): MultiSelect agora aparece também em edição, populado com snapshot inicial de `participantes_programada`. `handleSubmit` calcula diff (`toAdd = atual − iniciais`, `toRemove = iniciais − atual − [facilitadorId]`) e chama `POST/DELETE /api/reunioes/:id/participantes` em paralelo via `Promise.allSettled` (originalmente `Promise.all`, ajustado pelo `/code-review` pra não mascarar o sucesso do PATCH em erro de rede). `useEffect` re-injeta o facilitador automaticamente caso seja desmarcado. Backend já aceitava a operação pela secretária — endpoints sem gate de role, só exigem `status_ata == PROGRAMADA`. 5 camadas de gate verdes (`/code-review`, `/security-review` sem findings, `superpowers:requesting-code-review` aprovou com follow-ups arquiteturais registrados, CI 3/3 SUCCESS, `verification-before-completion` com tsc+lint+build local exit=0). Bump patch automático 0.3.0 → 0.3.1. Self-approval bloqueado pelo GitHub free; merge segue direto via `--admin`. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`).

---

## v0.3.0 — 2026-05-22 — feat(reunioes,secretaria): dropdown responsável + visão global da secretária com gate em ata/pendência

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#10](https://github.com/pedrorezendefig/hospital-reunioes/pull/10) · Issue: —
- Commit: `805daa0`
- Resultado: 🟢 healthy (backend 2m42s, frontend 3m43s)
- Detalhe: [chronicles/🟢-2026-05-22-1628-805daa0-dropdown-responsavel-correcao-ata.md](chronicles/🟢-2026-05-22-1628-805daa0-dropdown-responsavel-correcao-ata.md)

**Resumo:** Mescla dois escopos numa única release. **(1) Dropdown responsável na correção da ATA** — substitui edição implícita via chat por combobox inline de participantes na coluna RESPONSÁVEL do quadro de atribuições; resolve bug "Josiane" (nome trocava mas cargo continuava stale). Endpoint novo `PATCH /reunioes/{id}/quadro-atribuicoes/{index}`, helper `_canonicalize_cargos_quadro` no orchestrator pós-IA, `pendencias.cargo` agora populado em `liberar_pendencias` (era NULL antes), componente `ResponsavelInlineCombobox.tsx`. **(2) Expansão do papel secretária** — antes só via PROGRAMADAS futuras, agora vê o calendário do hospital inteiro (qualquer status, qualquer data) e gerencia participantes em reuniões PROGRAMADAS (inclusive alheias). Defense-in-depth: **20 gates 403 explícitos** nos endpoints de ata/pendência/comentário (12 reuniões + 5 pendências + 3 comentários), `get_allowed_reuniao_ids` retorna `None` pra secretária, `_redact_ata_fields` redacta `json_ata`/`url_pdf_*` nos endpoints de leitura, gate de visibilidade adicionado em `PATCH /quadro-atribuicoes/{index}`. Frontend: flag `hideAtaSections` em 14 pontos do detalhe da reunião + esconde botão "Desmarcar" e "Anexar Transcrição" pra secretária. Bump 0.2.1 → 0.3.0 (feat=minor). 3 reviewers automatizados (code-review + security-review + superpowers:requesting-code-review) detectaram 3 must-fix em iteração — todos resolvidos antes do merge: critical de `json_ata` leak em `GET /reunioes/{id}`, must-fix de visibilidade no PATCH quadro e ausência de teste de gates. Novo arquivo `tests/test_secretaria_gates.py` com 9 testes cobrindo os 3 routers + edge case `me=None`. Suite final: 186/186 passa. CI 3/3 verde. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.1 — 2026-05-22 — fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#9](https://github.com/pedrorezendefig/hospital-reunioes/pull/9) · Issue: —
- Commit: `d3cc4a1`
- Resultado: 🟢 healthy (build frontend 169s; backend não redeployado, só env APP_VERSION sincronizada)
- Detalhe: [chronicles/🟢-2026-05-22-1305-d3cc4a1-versao-footer-sem-link-direita.md](chronicles/🟢-2026-05-22-1305-d3cc4a1-versao-footer-sem-link-direita.md)

**Resumo:** Footer.tsx perde o wrapper `<a target=_blank>` que apontava pro CHANGELOG no GitHub e muda de `text-center` pra `text-right pr-4`. Versão agora é texto puro alinhado ao canto inferior direito (padrão visual de apps profissionais — não compete com conteúdo). Aria-label mantido pra screen readers. Bump patch automático `0.2.0 → 0.2.1` (tipo dominante: fix). APP_VERSION sincronizada no backend Coolify (`mcp__coolify__env_vars update`, runtime-only) pré-merge — backend NÃO foi redeployado, só o env mudou e o `/api/health` já reflete `version:0.2.1`. Frontend rebuild Docker em 169s (cache quente). Gates: code-review max-effort (3 agents, 1 nit aplicado `px-4` → `pr-4`), security e requesting-code-review pulados (mudança cosmética de 4 linhas em 1 arquivo de UI), CI verde, verification verde (tsc + lint). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.0 — 2026-05-22 — feat(app): acrescentar versionamento visível na aplicação

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#8](https://github.com/pedrorezendefig/hospital-reunioes/pull/8) · Issue: —
- Commit: `1efd175`
- Resultado: 🟢 healthy (build backend 198s, frontend 255s, health ok com version match)
- Detalhe: [chronicles/🟢-2026-05-22-1146-1efd175-versionamento-visivel-app.md](chronicles/🟢-2026-05-22-1146-1efd175-versionamento-visivel-app.md)

**Resumo:** primeiro PR de versionamento. Rodapé `v0.2.0` clicável em todas as páginas do AppShell (link → CHANGELOG.md no GitHub). Backend `/api/health` retorna `version` lido de env `APP_VERSION` (default `0.1.0`). Footer.tsx novo lê `NEXT_PUBLIC_APP_VERSION` inlined em build-time pelo `next.config.ts` a partir de `package.json` (bumpado 0.1.0 → 0.2.0 manualmente neste PR; nos próximos é automático via /ship Passo 5.5). Skill `/ship` ganha bump automático de semver por tipo de commit (BREAKING > feat > fix/chore) + Passo 8.5 que sincroniza APP_VERSION no Coolify pré-merge (evita race com webhook). Skill `/deploy` ganha Passo 3.5 defensivo idempotente + Passo 7.2 version match check (rollback automático se /api/health não retorna versão esperada). Docs novos: `VERSIONING.md` (esquema completo) + header explicativo no CHANGELOG.md. 5 camadas de gate verdes antes do merge — 4 issues do code-review e 2 do requesting-code-review corrigidos em-band nos commits 3136a5c e 4a5fc8d.

---

## 2026-05-21 20:39 - feat(skills): automatizar /snapshot via script Python

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `70bac46`
- PR: [#7](https://github.com/pedrorezendefig/hospital-reunioes/pull/7) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — só toca skills + docs)
- Detalhe: [chronicles/🟢-2026-05-21-2039-70bac46-snapshot-parser-automation.md](chronicles/🟢-2026-05-21-2039-70bac46-snapshot-parser-automation.md)

**Resumo:** implementa o gerador real do `/snapshot` que estava só documentado no PR #6. Script Python self-contained (993 linhas, stdlib only) em `.claude/skills/snapshot/scripts/snapshot.py` com parser AST de routers FastAPI (78 endpoints em 13 routers), parser SQL cumulativo de migrations (13 tabelas das 36 migrations), 5 geradores de MD, idempotência via comparação de buffer e flags CLI (`--check`, `--force`, `--only`, `--diff`, `--no-commit`). Code-review pegou 1 bug score 100 (JSONB DEFAULT corrompendo parser de colunas) + 3 issues score 75, todas corrigidas antes do merge.

---

## 2026-05-21 18:58 - feat(workflow): integrar Superpowers + /snapshot vivo + 5 camadas de gate

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e9f64ee`
- PR: [#6](https://github.com/pedrorezendefig/hospital-reunioes/pull/6) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — PR só toca skills + docs)
- Detalhe: [chronicles/🟢-2026-05-21-1858-e9f64ee-superpowers-integration-v1.md](chronicles/🟢-2026-05-21-1858-e9f64ee-superpowers-integration-v1.md)

**Resumo:** integra plugin Superpowers v5.1.0 no workflow do time. Cria skill `/snapshot` (gera 7 MDs vivos em `docs/spec/snapshots/` regenerados a cada deploy via `/deploy ship`). `/start` ganha Modo D (retomar trabalho parado de outra sessão) + invocação de `brainstorming` por default no Modo A. `/ship` ganha 5 camadas independentes de gate antes do self-approval (code-review, security-review, requesting-code-review, CI Actions, verification-before-completion). `CLAUDE.md` reescrito com 5 seções novas. CI Actions ganha job `build` (docker sanity). Cleanup de 150+ skills `reversa-*` absorvido no mesmo PR (-26338 linhas).
