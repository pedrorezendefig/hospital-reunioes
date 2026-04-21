# DEPLOY — Hospital Reuniões

> Documento vivo. A skill `/deploy` lê as seções `config-*` e escreve `status` + `historico`.
>
> Seções marcadas com `<!-- blueprint:section:xxx -->` são atualizadas idempotentemente pela skill. Não edite manualmente dentro desses marcadores — a skill sobrescreve.

---

## Config — Coolify

<!-- blueprint:section:config-coolify -->

**VPS:** Hostinger 16GB — `31.97.29.32`
**Coolify:** https://coolify.mala-ia.cloud
**Projeto Coolify UUID:** `<preencher após /deploy setup>`
**Server UUID:** `<preencher após /deploy setup>`
**GitHub App UUID:** `<preencher após /deploy setup>`
**Supabase Service UUID:** `<preencher após /deploy setup>`

| App | UUID | Porta | Domínio | Health check |
|---|---|---|---|---|
| backend | `q11fubn3ezlszvwph695d9oh` | 8000 | api.mala-ia.cloud | `/api/health` |
| frontend | `n5omtnv1u8u268zprvwu7902` | 3000 | app.mala-ia.cloud | — |
| supabase-studio | `<preencher>` | — | studio.mala-ia.cloud | — |

**Branch de deploy:** `main`
**Tempo médio:** backend ~1min, frontend ~2min

---

## Config — Env vars

<!-- blueprint:section:config-env -->

### Backend — obrigatórias no Coolify

```
ENVIRONMENT
DEBUG
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
OPENAI_API_KEY
CLICKSIGN_API_KEY
CLICKSIGN_BASE_URL
CLICKSIGN_WEBHOOK_SECRET
RESEND_API_KEY
RESEND_FROM_EMAIL
SIGNUP_ENCRYPTION_KEY
SIGNUP_PASSE
ENABLE_BYPASS_ENDPOINTS
```

### Backend — prod-only (skill valida valor exato)

| Var | Valor obrigatório |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `ENABLE_BYPASS_ENDPOINTS` | `false` |
| `CLICKSIGN_BASE_URL` | `https://app.clicksign.com` |

### Frontend — build-time (skill valida `is_build_time=true`)

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_ENVIRONMENT
```

---

## Config — Secrets auto-gerados

<!-- blueprint:section:config-secrets -->

Gerados pela skill via comando local, setados no Coolify via MCP, nunca persistidos em arquivo/log.

| Var | Serviço | Gerador local |
|---|---|---|
| `SIGNUP_ENCRYPTION_KEY` | backend | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `CLICKSIGN_WEBHOOK_SECRET` | backend | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SIGNUP_PASSE` | backend | `python -c "import secrets; print(secrets.token_urlsafe(24))"` |

**Fallback** se `cryptography` não estiver disponível localmente: `docker exec hr-backend python -c "..."`.

---

## Config — Arquivos hard-excluded do commit

<!-- blueprint:section:config-excludes -->

`/deploy` nunca inclui estes arquivos em `git add`, mesmo que estejam modificados:

```
.env
.env.backup
.env.local
.env.*.local
deploy-history.md
*-env-producao.txt
credentials*
*.pem
*.key
```

---

## Status atual de produção

<!-- blueprint:section:status -->

_(Preenchido pela skill após cada `/deploy` bem-sucedido.)_

**Último deploy:** —
**Commit:** —
**Timestamp:** —

| Serviço | Status | Último deploy | Latência |
|---|---|---|---|
| backend | — | — | — |
| frontend | — | — | — |
| supabase | — | — | — |

---

## Histórico (últimos 10 deploys)

<!-- blueprint:section:historico -->

_(Vazio até o primeiro deploy. A skill mantém no máximo 10 entradas, mais recente no topo.)_

---

## Gates pré-deploy

<!-- blueprint:section:gates -->

Lista do que `/deploy` valida automaticamente antes de commitar. Flag `--verbose` mostra cada gate passando.

- **Lint backend:** `uv run ruff check . && uv run ruff format --check .`
- **Lint frontend:** `pnpm lint && pnpm exec tsc --noEmit`
- **`.env.example` ↔ `config.py`:** mesmo conjunto de chaves
- **Git status limpo de secrets:** nenhum `.env`, `.env.backup`, `credentials*`, `.pem`, `.key` staged
- **`migrations_backup/` ausente**
- **NEXT_PUBLIC_* build-time:** `is_build_time=true` no Coolify
- **Vars prod-only:** valor exato conforme tabela acima
- **Secrets auto-gerados:** presentes e não vazios (gera se faltar)
- **Migrations novas:** lista pra aplicação (não bloqueia pre-flight)

---

## Rollback

<!-- blueprint:section:rollback -->

`/deploy` dispara rollback automático (1 tentativa) se health check pós-deploy falhar: redeploya o último SHA saudável via `mcp__coolify__deploy`.

`/deploy rollback` (manual) lê o histórico, identifica último deploy healthy, pede confirmação, redeploya.

Se rollback automático também falhar → skill para e pede intervenção humana com logs.

Migrations aplicadas **não são revertidas automaticamente**. Se necessário, criar migration de rollback manual.

---

## Comandos de referência (MCP Coolify)

<!-- blueprint:section:mcp-ref -->

| Ação | Comando |
|---|---|
| Listar apps | `mcp__coolify__list_applications` |
| Detalhe de app | `mcp__coolify__get_application` |
| Disparar deploy | `mcp__coolify__deploy` |
| Monitorar deploy | `mcp__coolify__deployment` (list / get) |
| Health check | `mcp__coolify__diagnose_app` |
| Logs runtime | `mcp__coolify__application_logs` |
| Env vars | `mcp__coolify__env_vars` (list / create / update / delete) |
| Bulk env | `mcp__coolify__bulk_env_update` |
| Restart app | `mcp__coolify__control` |
