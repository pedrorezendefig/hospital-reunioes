# Gates, rollback, excludes e referência MCP

## Pre-flight gates

Lista do que `/deploy` valida automaticamente antes de commitar. Flag `--verbose` mostra cada gate passando.

- **Lint backend:** `uv run ruff check . && uv run ruff format --check .`
- **Lint frontend:** `pnpm lint && pnpm exec tsc --noEmit`
- **`.env.example` ↔ `config.py`:** mesmo conjunto de chaves
- **Git status limpo de secrets:** nenhum `.env`, `.env.backup`, `credentials*`, `.pem`, `.key` staged
- **`migrations_backup/` ausente**
- **NEXT_PUBLIC_* build-time:** `is_build_time=true` no Coolify
- **Vars prod-only:** valor exato conforme `env-vars.md`
- **Secrets auto-gerados:** presentes e não vazios (gera se faltar)
- **Migrations novas:** lista para aplicação (não bloqueia pre-flight)

## Rollback

`/deploy` dispara rollback automático (1 tentativa) se health check pós-deploy falhar: redeploya o último SHA saudável via `mcp__coolify__deploy`.

`/deploy rollback` (manual) lê o histórico de `history.json`, identifica último deploy `healthy`, pede confirmação, redeploya.

Se rollback automático também falhar, a skill para e pede intervenção humana com logs.

Migrations aplicadas **não são revertidas automaticamente**. Se necessário, criar migration de rollback manual.

## Arquivos hard-excluded do commit

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

## Comandos de referência (MCP Coolify)

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
