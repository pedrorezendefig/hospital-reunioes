# Plano — Reversão completa do agente Ana (versão beta sem resquício)

## Plano

### Contexto

Em 2026-04-27, após mapear o que estava prestes a subir pra produção (65 commits da branch `feat/ana-fase1-foundation` com agente Ana BETA: backend de tool calling streaming, frontend `/admin/ana`+QuickPanel ⌘K, 5 migrations 032-036, telemetria, 4 telas admin removidas), Pedro decidiu **abortar a Ana inteira** e seguir com versão beta sem agente — a branch nunca deve mergear, todos os artefatos devem ser removidos do `main`, e o trabalho não-Ana já em andamento (redesign de pendências, `transcricao_extractor` multi-formato, logo HSM, planos de remoção do campo "local") deve ser preservado.

### Escopo

- Desfazer **65 commits** da branch `feat/ana-fase1-foundation` (83 arquivos, +14012/-2591 linhas)
- Remover do disco todos os artefatos Ana:
  - Backend: `app/services/ana_*.py`, `app/services/ana_tools/`, `app/routers/admin/ana.py`, `app/services/llm_client.py`
  - Frontend: `app/admin/ana/`, `components/ana/`, `lib/anaClient.ts`, `stores/anaStore.ts`
  - Migrations: `032_ana_conversations.sql` … `036_ana_readonly_role.sql`
  - Planos: master + Fase 1 + Fases 3-7 (+ docs auxiliares)
- Restaurar 4 telas admin removidas pelo commit `2294263` (`/admin/cargos`, `/admin/setores`, `/admin/tipos-reuniao` e a 4ª, voltam ao serem readicionadas pelo reset)
- Reset `main` local pra `origin/main` (perde 2 commits de docs Ana adiantados em main local: `58e9f34`, `e22d197`)
- **Matar** a branch local `feat/ana-fase1-foundation` (sem espelho remoto, deleção segura)
- **Preservar** trabalho não-Ana em andamento via stash + pop assistido (resolver conflitos)
- Manter rede de proteção via tag git: `backup/pre-revert-ana-2026-04-27`

### Passos executados

1. Tag de backup `backup/pre-revert-ana-2026-04-27` apontada pra `8d734f9` (ponta da branch antes da deleção)
2. `git stash push -u -m "pre-revert-ana: working tree em 2026-04-27T07:30:24Z"` — preservou 38 mod + 8 untracked
3. `git checkout main && git reset --hard origin/main` — HEAD = `9d0d198`
4. `git stash pop` + 4 conflitos resolvidos:
   - `app/services/ana_schema.py` → `git rm` (descartado)
   - `app/services/ana_tools/mutacoes_leves.py` → `git rm` (descartado)
   - `planos/plano-26-04-27-0227h-redesign-lista-pendencias.md` → `git checkout --theirs` + add (preservado)
   - `backend/pyproject.toml` → resolvido via Edit: mantém `docx2txt>=0.8`, remove `psycopg2-binary` e `sse-starlette` (Ana-específicas)
5. `rm -rf app/services/ana_tools/` — pasta com `__pycache__` órfão
6. `git branch -D feat/ana-fase1-foundation` (era `8d734f9`)
7. `rm ~/.claude/plans/contexto-que-voc-scalable-hennessy.md` (plano de deploy abortado)
8. `uv sync --extra dev` — removeu 13 pacotes obsoletos, reinstalou dev deps
9. `pytest -q` (backend) → **189 passed, 1 failed pré-existente**
10. `pnpm build` (frontend) → **25 páginas geradas sem erro, sem `/admin/ana`**

### Critérios de sucesso (todos atendidos)

- ✅ `git branch -a` não lista mais `feat/ana-fase1-foundation`
- ✅ Tag `backup/pre-revert-ana-2026-04-27` resolve `8d734f9` (recuperabilidade preservada)
- ✅ `find hospital-reunioes -name 'ana_*' -not -path '*/node_modules/*'` retorna vazio
- ✅ `ls supabase/migrations/` mostra `031_drop_signup_requests.sql` como última
- ✅ `pnpm build` gera 25 páginas com `/admin/cargos`, `/admin/setores`, `/admin/tipos-reuniao` presentes; sem `/admin/ana`
- ✅ Pytest sem regressões (única falha é pré-existente em `origin/main`, ver pendências)

### Riscos e atenção

- Working tree continua com **38 modificados + 8 untracked** NÃO commitados — todo trabalho em progresso do Pedro. **Não foi incluído neste commit** (commit é só do plano). Pedro deve fazer commits temáticos depois.
- Falha pré-existente em `test_admin_acoes_massa.py::TestBulkReprocessarIA::test_completed_com_falha_parcial`: mock `fake_run` com 4 args vs `orchestrator.run_pipeline` com 6 args reais. Confirmado via `git diff origin/main` (sem divergência). **Não relacionado à reversão.**
- Migration nova `supabase/migrations/003_drop_local_reuniao.sql` (untracked) usa numeração 003 que conflita com histórico (003 já existe em outra migration antiga). Pedro deve renomear pra `037_drop_local_reuniao.sql`.

## Execução / Resultados

### Linha do tempo (UTC, 2026-04-27)

| Hora | Operação | Resultado |
|---|---|---|
| 07:30:24Z | Tag `backup/pre-revert-ana-2026-04-27` → `8d734f9` | ✅ |
| 07:30:24Z | Stash `pre-revert-ana: working tree...` | ✅ 45 entradas |
| ~07:31Z | `checkout main` + `reset --hard origin/main` | ✅ HEAD `9d0d198` |
| ~07:32Z | `stash pop` + resolução de 4 conflitos | ✅ |
| ~07:33Z | `git branch -D feat/ana-fase1-foundation` | ✅ "Deleted branch (was 8d734f9)" |
| ~07:34Z | `rm ~/.claude/plans/contexto-que-voc-scalable-hennessy.md` | ✅ |
| ~07:35Z | `uv sync` + `uv sync --extra dev` | ✅ 13 deps obsoletas removidas |
| ~07:36Z | `pytest -q` | ✅ 189 passed / 1 falha pré-existente |
| ~07:37Z | `pnpm build` (via `npx pnpm@9`) | ✅ 25 páginas |

### Estado pós-reversão

- **Branch ativa:** `main` alinhada com `origin/main` (HEAD `9d0d198 — refactor: remove fluxo signup self-service + adiciona PWA mobile shell`)
- **Branches restantes:** `archive/pre-blueprint`, `feature/remove-google-auth`, `fix/security-phase3-4`, `main`, `remotes/origin/main`
- **Working tree:** 38 modificados + 8 untracked (todos não-Ana, trabalho em progresso a ser commitado em sessões futuras)
- **Memórias persistentes:** auditadas, nenhuma referência específica à Ana (8 entradas em `~/.claude/projects/-Users-pedrorezende-PedroDev-Hospital/memory/MEMORY.md`)
- **Stash entries:** `stash@{0}` é antigo (`WIP on main: 2eee782 fix(chat-correcao)…`), pré-existente, não tocado

### Pendências (Pedro)

1. Commitar o trabalho preservado em commits temáticos:
   - Redesign da lista de pendências (modificações em `app/pendencias/page.tsx`, `kanban/page.tsx`, components, plano `plano-26-04-27-0227h…`)
   - `transcricao_extractor.py` + `UploadTranscricaoModal.tsx` + plano `plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md` + dep `docx2txt` no pyproject
   - Remover-local-renomear-objetivo-pauta (modificações em prompts, schemas, `PreparacaoChecklist.tsx` etc + plano `plano-26-04-27-0421h…`)
   - Logo HSM (`LOGO HSM.png`, `logo-hsm.png`, `fonts/`, `Logo.tsx`)
   - Atualizações de blueprint dashboard/state/history
2. Renomear `supabase/migrations/003_drop_local_reuniao.sql` pra próximo número disponível (sugestão: `032_drop_local_reuniao.sql` ou `037_…`)
3. Resolver bug pré-existente do mock em `test_admin_acoes_massa.py::TestBulkReprocessarIA::test_completed_com_falha_parcial` — não relacionado à Ana, mas trava CI
4. Eventualmente deletar a tag `backup/pre-revert-ana-2026-04-27` quando tiver certeza absoluta de que nada será reaproveitado

### Comandos de recuperação (caso precise voltar atrás)

```bash
# Recuperar a branch deletada
git checkout -b feat/ana-recovered backup/pre-revert-ana-2026-04-27

# Listar os 65 commits descartados
git log backup/pre-revert-ana-2026-04-27 --oneline ^origin/main

# Cherry-pick um commit específico (ex: refactor llm_client)
git cherry-pick 0db12c6  # feat(backend): wrapper LLM compartilhado apontando para OpenRouter
git cherry-pick 4a4e196  # refactor(backend): ai_processor usa llm_client compartilhado

# Apagar a tag de backup quando não precisar mais
git tag -d backup/pre-revert-ana-2026-04-27
```
