# Deploy `7457c69` - 🟢 healthy

- **Data**: 2026-05-08 01:39 -03:00
- **SHA**: `7457c69`
- **Modo**: ship (manual, sem skill `/deploy`)
- **Resultado**: healthy
- **Subject**: Aplica ruff format em pdf_generator.py + ship dos 5 commits da migração de domínio.

## Serviços tocados

- backend
- frontend (subiu junto pelos 5 commits anteriores que ainda não tinham deploy registrado)

## Commits que entraram nesse ship

- `7457c69` chore(backend): aplica ruff format em pdf_generator.py
- `003ed6f` fix(frontend): pinna pnpm@9 (versao 11+ bloqueia build scripts)
- `8785e2a` fix(frontend): aprova build scripts (sharp, unrs-resolver) no pnpm
- `0c9e936` fix(frontend): bump base image para node:22-alpine
- `4897ae1` fix(infra): frontend mantem subdominio app.hospitalsaomatheus.cloud
- `20ef76c` feat(infra): migra dominio de mala-ia.cloud para hospitalsaomatheus.cloud

## Health pós-deploy

| Serviço | URL | Status | Latência |
|---|---|---|---|
| backend | https://api.hospitalsaomatheus.cloud/api/health | 200 healthy | 64ms |
| frontend | https://app.hospitalsaomatheus.cloud | 200 (Next.js prerender HIT) | n/a |
| supabase studio | https://studio.hospitalsaomatheus.cloud | 401 (auth required, esperado) | n/a |

## Notas

Deploy manual sem MCP do Coolify por causa de **token revogado** (`COOLIFY_ACCESS_TOKEN` retornando 401 Unauthenticated). Coolify auto-deployou via webhook do GitHub App após push em main, mas a sincronização do `state.json`/`history.json`/`PROJETO.md` foi feita manualmente.

**O CI continua vermelho** por dois motivos paralelos que **não bloqueiam deploy** (Coolify usa Dockerfile, alinhado com node:22-alpine + pnpm@9):

1. **Backend pytest**: a fixture global do pydantic `Settings` exige `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`. Sem essas vars no ambiente do GitHub Actions, qualquer `import` dos módulos do backend explode com `ValidationError`. Fix: criar `tests/conftest.py` com `os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")` e idem para `SERVICE_ROLE_KEY`. Alternativa: adicionar essas como secrets no Actions (overhead de manter em sync).
2. **Frontend lint**: `.github/workflows/ci.yml` usa `actions/setup-node@v4` com `node-version: "20"` mas `pnpm/action-setup@v4` com `version: latest` (que hoje é pnpm 11.0.8). pnpm 11 importa `node:sqlite` (built-in só do Node 22+). Fix: mudar para `node-version: "22"` e `version: "9"` (alinha com Dockerfile).

**Ação pendente para Pedro:** renovar token do Coolify e atualizar via:
```bash
claude mcp remove coolify -s user
claude mcp add coolify -s user -- npx -y @masonator/coolify-mcp \
  -e COOLIFY_ACCESS_TOKEN=<novo-token> \
  -e COOLIFY_BASE_URL=https://coolify.mala-ia.cloud
```

DNS `coolify.hospitalsaomatheus.cloud` ainda não foi criado (registro A faltando). UI continua acessível pelo domínio antigo.

---
_Gerado manualmente (sem skill `/deploy`)._
