# Pré-deploy checklist: CORS hard-fail + indexes em FKs + logging JSON + health rico

## Plano

### Contexto

Auditoria do app contra checklist de pré-deploy genérico (9 itens). Decidido executar 3:

- **Item 4 (CORS):** validador em `config.py` só emite warning quando `DEBUG=true` em prod. Virar hard-fail.
- **Item 7 (indexes):** FKs antigas em `reuniao.facilitador_id`, `participante_reuniao.reuniao_id`, `pendencia.reuniao_id` podem não ter index explícito. Audit + migration 038.
- **Item 8 (observabilidade):** logs em plain text, `/api/health` estático. Trocar por JSON estruturado com `request_id`/`user_id` e health que confere Supabase.

Decisão complementar: evoluir skill `/deploy` adicionando 3 gates (CORS audit, FK-index warn em migrations novas, Health body inclui `db`). Sem Sentry/UptimeRobot agora.

Plano detalhado em `~/.claude/plans/pre-deployment-checklist-shipping-to-synchronous-rocket.md`.

### Passos

1. **CORS hard-fail (`config.py` linha 78-83):** trocar `warnings.warn` por `raise ValueError`.
2. **JSON logging + middleware `request_context`:**
   - `pyproject.toml`: adicionar `python-json-logger>=2.0`, `uv lock`, `uv sync`.
   - Criar `app/middleware/__init__.py` + `app/middleware/request_context.py` (ContextVar + middleware ASGI + logger `app.requests`).
   - `main.py`: substituir formatter por JSON, registrar middleware antes do CORS, importar e usar logger novo.
   - `dependencies.py:get_current_user`: setar `user_id` no ContextVar após validar JWT.
3. **`/api/health` rico (`routers/health.py`):** query Supabase com timeout 2s, retornar `{status, db, app, version}`. 200 quando ok, 503 quando degraded.
4. **`project.json`:** atualizar `expected_body_regex` pra exigir `"db"`. Documentar gates novos.
5. **Audit FKs (read-only):** rodar SQL em prod via psql/Coolify Terminal.
6. **Migration `038_fk_indexes.sql`:** `CREATE INDEX CONCURRENTLY IF NOT EXISTS` pra cada FK descoberta sem index. Atenção: `CONCURRENTLY` não roda em transação.
7. **Skill `/deploy` (`~/.claude/skills/deploy/SKILL.md`):** adicionar Gate 11 (CORS audit), Gate FK-warn, Gate 13 (Health rich).
8. **`CLAUDE.md` do projeto:** seção "Pré-deploy checklist (auto via /deploy)" listando gates.

### Critérios de sucesso

- `DEBUG=true ENVIRONMENT=production uv run uvicorn app.main:app` falha com `ValueError`.
- `curl https://api.hospitalsaomatheus.cloud/api/health | jq '.db'` retorna `"healthy"` em prod ok, `"degraded"` com Supabase fora.
- Log do container backend no Coolify é JSON parseável com `request_id`, `user_id`, `path`, `status_code`, `latency_ms`.
- `pg_indexes` mostra index para cada FK descoberta no audit.
- Próxima execução de `/deploy ship` reporta "Gate 11/FK-warn/Gate 13: OK".

### Riscos

- `CREATE INDEX CONCURRENTLY` pode falhar no runner de migrations do Supabase (não pode estar em transação). Mitigação: aplicar via psql direto no Coolify Terminal e marcar no `schema_migrations`.
- Middleware request_id adicionar latência. Mitigação: implementação trivial (UUID + ContextVar + `time.perf_counter()`); medir local.
- Tests podem importar o validador em modo prod-sim. Mitigação: rodar `pytest` antes do commit.

## Execução / Resultados

Executado em 2026-05-17. Working copy preparada e commit deixado a cargo do próximo `/deploy ship`.

### Item 4 (CORS hard-fail)

- `hospital-reunioes/backend/app/config.py`: `validate_debug_prod()` agora lança `ValueError` quando `ENVIRONMENT=production` e `DEBUG=true`. Comportamento: container não sobe, healthcheck falha, Coolify rejeita versão.

### Item 7 (indexes em FKs antigas)

- Audit feito offline cruzando todas as declarações `REFERENCES` em `hospital-reunioes/supabase/migrations/*.sql` contra `CREATE INDEX` existentes. 5 FKs identificadas sem index:
  - `reunioes.facilitador_id` → `participantes(id)`
  - `agendamentos_email.id_acao` → `pendencias(id_acao)` ON DELETE CASCADE
  - `participantes.setor_id` → `setores(id)` ON DELETE SET NULL
  - `participantes.cargo_id` → `cargos(id)` ON DELETE SET NULL
  - `reunioes.tipo_id` → `tipos_reuniao(id)` ON DELETE SET NULL
- Migration `hospital-reunioes/supabase/migrations/038_fk_indexes.sql` criada com `CREATE INDEX IF NOT EXISTS` (sem `CONCURRENTLY` porque o runner de migrations do Supabase aplica tudo em transação). Justificativa documentada no comentário da própria migration. Para escala maior, dropar e recriar manualmente com `CONCURRENTLY` via psql.

### Item 8 (logging JSON + health rico)

- `hospital-reunioes/backend/app/middleware/__init__.py` + `request_context.py` (novos): ContextVars `request_id_var` e `user_id_var`, `JsonFormatter` em stdlib puro (sem dep nova; abandonei o `python-json-logger` do plano original), `configure_logging()` e `RequestContextMiddleware` (ASGI via BaseHTTPMiddleware).
- `hospital-reunioes/backend/app/main.py`: `logging.basicConfig` substituído por `configure_logging()`. `RequestContextMiddleware` registrado depois do `CORSMiddleware` pra ficar outermost. `X-Request-ID` adicionado em `expose_headers` do CORS.
- `hospital-reunioes/backend/app/dependencies.py`: `get_current_user` chama `set_user_id(user_id)` após validar JWT, populando o ContextVar lido pelo `JsonFormatter`.
- `hospital-reunioes/backend/app/routers/health.py`: agora faz `SELECT id LIMIT 1` em `participantes` com timeout 2s (via `asyncio.wait_for(asyncio.to_thread(...))`). Retorna `{status, db, app, version}`. 200 quando ok, 503 quando degraded. Body novo conforme `expected_body_regex` atualizado.
- `blueprint/deploy/project.json`: `expected_body_regex` atualizado pra `^\{"status":"(healthy|degraded)","db":"(healthy|degraded)".*\}$`. 3 gates novos declarados em `gates`: `cors_audit`, `fk_index_warning`, `health_rich`.

### Evolução da skill `/deploy`

- `~/.claude/skills/deploy/SKILL.md` (skill global, não é git-tracked): adicionadas 3 sub-seções.
  - `2.10 CORS audit` (gate `cors_audit`, fail): grep em `scan_files` por `bad_patterns`.
  - `2.11 FK index warning` (gate `fk_index_warning`, warn-only): pra cada migration nova com `REFERENCES`, procura `CREATE INDEX` correspondente.
  - `7.1 Health rico` (gate `health_rich`, fail): parseia body do health, exige `required_keys`, dispara rollback se faltar.
- Cada gate é condicional a `project.json` ter a chave correspondente, então projetos antigos sem essas keys continuam funcionando sem mudança.

### CLAUDE.md do projeto

Adicionada seção "Pré-deploy checklist (auto via /deploy)" com tabela dos 10 gates ativos (incluindo os 3 novos) e nota sobre o hard-fail do `validate_debug_prod()`.

### Verificação

- `uv run ruff check .`: 1 erro auto-fixado (`datetime.timezone.utc` → `datetime.UTC` em `request_context.py`).
- `uv run ruff format .`: 2 arquivos reformatados (`config.py`, `request_context.py`).
- `uv run pytest -q`: **175 passed, 2 failed** em ~3.8s. As 2 falhas estão em `test_admin_usuarios.py::TestListUsuarios::{test_list_retorna_ativos_e_inativos,test_filtra_por_super_admin}`, ambas com `AttributeError: 'Query' object has no attribute 'split'` em `app/routers/admin/usuarios.py:195`. **Bug pré-existente**, sem relação com as mudanças deste plano (arquivo não está em `git diff`).

### Pendências externas (rodar fora do automático)

- Validar manualmente em prod após próximo `/deploy ship`:
  - `curl -s https://api.hospitalsaomatheus.cloud/api/health | jq '.db'` deve retornar `"healthy"`.
  - Abrir log do container backend no Coolify: cada linha deve ser JSON válido com `request_id` e (quando autenticado) `user_id`.
  - Conferir indexes aplicados: `SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname IN ('idx_reunioes_facilitador','idx_agendamentos_email_id_acao','idx_participantes_setor_id','idx_participantes_cargo_id','idx_reunioes_tipo_id');`.
- Bug pré-existente em `routers/admin/usuarios.py:195` (Query/split) merece um plano 🟡 próprio quando der tempo. Fix provável: trocar `access_profile_filter.split(",")` por mesmo padrão usado pra `setor` (proteção `isinstance(access_profile_filter, str)` antes do split, ou ajustar a annotation pra `Annotated[str | None, Query(...)]`).
