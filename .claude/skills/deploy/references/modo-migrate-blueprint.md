## Modo `migrate-blueprint`

Invocação: `/deploy migrate-blueprint [--dry-run]`. Roda **uma única vez** por projeto. Migra:
- **Legado v0** (`blueprint/DEPLOY.md` único) → estrutura v2.
- **Legado v1** (`state.json` schema 1.0 sem `project.json`) → adicionar `project.json` v2 ao lado.

### Detecção

- Existe `docs/spec/deploy/project.json` válido → reportar "Já migrado" e parar (idempotência).
- Existe `docs/spec/deploy/state.json` (sem `project.json`) → modo **v1→v2**.
- Existe `blueprint/DEPLOY.md` (sem `docs/spec/deploy/`) → modo **v0→v2**.
- Nada existe → reportar "Nada a migrar. Rode `/deploy setup`." e parar.

### Modo v1→v2 (state.json existe, sem project.json)

1. Ler `state.json` schema 1.0 + `coolify.md` legado (se existir).
2. Construir `project.json`:
   - `project.{name,slug,description}`: pedir/inferir (slug derivado de `production.repo`).
   - `git.{repo,branch}` ← `state.production.{repo,branch}`.
   - `coolify.*` ← `state.production.{coolify_url, project_uuid, server_uuid, github_app_uuid, vps_ip, domain_root}`.
   - `services[]` ← `state.services[]`, completando campos faltantes:
     - `type` inferido: `id == "backend"` + presença de `pyproject.toml` no path → `fastapi`; `id == "frontend"` + `package.json` com next → `nextjs`; `id == "supabase"` → `supabase`.
     - `build.{base_directory, ports_exposes, dockerfile_location, build_pack}` ← do `coolify.md` legado + `coolify app get <uuid> --format json`.
     - `deploy.fqdn` derivado de `state.services[].domain`.
     - `deploy.health_check` ← `state.services[].health_path` + heurística (body_regex pra FastAPI = `^\{"status":"ok"\}$`).
     - `lint` ← heurística por type (FastAPI: ruff; Next.js: pnpm lint + tsc --noEmit).
     - `env_keys.{build_time, runtime_required, runtime_optional}` ← parsing de `state.env_vars`.
     - `prod_only_assertions` ← extrair de `gates` legados (busca por chaves com valor literal em `coolify.md` legado).
     - `diff_routing.trigger_paths` ← `["<base_directory sem leading slash>/**"]`.
   - `secrets_auto_generated[]` ← `state.secrets[]` + extrair generator do `secrets.md` legado.
   - `migrations` ← detectar diretório (default `<service supabase base>/migrations`) + container_pattern.
   - `gates.{env_example_sync, migrations_backup_dir}` ← detectar presença no projeto.
   - `hard_excluded` ← parser de `gates.md` legado, ou defaults.
   - `commit_inference.scope_map` ← gerar a partir dos `services[].diff_routing.trigger_paths`.

3. Escrever `docs/spec/deploy/project.json`.

4. **Não tocar** em `state.json`/`history.json` — schema 1.0 continua válido.

5. Apagar (se existirem, são legado da estrutura antiga absorvida pelo `project.json`):
   - `docs/spec/deploy/coolify.md` (UUIDs/portas agora em `project.json`)
   - `docs/spec/deploy/env-vars.md` (env vars já em `project.json.services[].env_keys`)
   - `docs/spec/deploy/secrets.md` (secrets em `project.json.secrets_auto_generated`)
   - `docs/spec/deploy/gates.md` (gates em `project.json.gates`)
   - `blueprint/dashboard.html` (legado)
   - `blueprint/DEPLOY.md.legacy` (caso de v0)


7. Reportar:
   ```
   Migração v1→v2 concluída.
   project.json: <path>
   Rode /deploy status pra confirmar leitura do project.json.
   ```

### Modo v0→v2 (DEPLOY.md monolítico existe)

1. Parsear `blueprint/DEPLOY.md` (marcadores `<!-- blueprint:section:xxx -->` ou heurística por header).
2. Construir `state.json` schema 1.0 + `project.json` schema 2.0 + `history.json` no mesmo passo.
3. `state.json`: como hoje (UUIDs/domínios/portas/health_path da seção `config-coolify`; status atual via CLI em paralelo).
4. `history.json`: parsear bloco `historico` em `deploys[]`.
5. `project.json`: gerar via mesmo procedimento do v1→v2, usando o state recém-construído como entrada.
6. Renomear `blueprint/DEPLOY.md` → `blueprint/DEPLOY.md.legacy` (a info foi absorvida pelo `project.json`).
8. Reportar resultado.

### Dry-run

Imprimir plano (que arquivos seriam criados, qual estado seria capturado, quais entradas no `project.json`) sem escrever nada.

---
