---
name: deploy
description: Skill de deploy via Coolify. Funciona em projetos que tenham docs/spec/deploy/project.json com toda a especificação de stack, portas, build, deploy, env vars, secrets e gates. Use sempre que o usuário pedir deploy, subir mudanças para produção, verificar estado da produção, reverter deploy, configurar Coolify do zero, ou disser "ship", "deploy", "rollback", "status de produção", "subir pra prod". Lê e escreve docs/spec/deploy/{project.json,state.json,history.json}. Ao final do ship, atualiza docs/spec/chronicles/ (renomeia plano 🟡 → 🟢/🔴, anexa seção ## Implementação/Deploy, atualiza YAML frontmatter com autor+SHA+data+resultado) e docs/spec/CHANGELOG.md (prepend cronológico).
---

# deploy — skill universal de deploy

Uma skill, cinco modos. Invocação por subcomando:

| Comando | Modo | Quando usar |
|---|---|---|
| `/deploy` | **ship** (default) | Deploy diário: pre-flight → commit → push → monitor → migrations → health → histórico |
| `/deploy setup` | **setup** | 1ª vez no projeto: cria projeto, apps, env vars, DNS guia, primeiro deploy, `project.json` |
| `/deploy status` | **status** | Só reporta estado atual, sem alterar nada |
| `/deploy rollback` | **rollback** | Reverte para último deploy `healthy` |
| `/deploy migrate-blueprint` | **migrate** | 1× por projeto: migra `blueprint/DEPLOY.md` legado (estrutura antiga) ou `state.json` schema 1.0 (sem `project.json`) para o schema 2.0 |

**Flags compartilhadas:**
- `--verbose` — mostra cada gate passando (default: silencioso quando ok)
- `--skip-lint` — pula lint (só pra emergência)
- `--no-migrations` — ignora migrations mesmo se houver novas
- `--skip-snapshot` — pula `/snapshot` ao final do ship (deploy sem regenerar snapshots de spec; só pra emergência). Substitui a flag antiga `--skip-spec` removida junto com o pipeline REVERSA. Apenas warn-only de qualquer forma — falha do snapshot não derruba ship.
- `--dry-run` — (setup/rollback/migrate) mostra o que faria sem executar

**Fonte única de verdade por projeto:**
- `<repo>/docs/spec/deploy/project.json` — **spec do projeto** (o "v0"): stack, portas, fqdn, build, env vars, secrets, gates. Lido em todos os modos. Editável manualmente; `setup`/`migrate` o gera.
- `<repo>/docs/spec/deploy/state.json` — **snapshot do estado atual**. Reescrito pelo ship/rollback/setup. Não editar à mão.
- `<repo>/docs/spec/deploy/history.json` — **timeline**. Reescrito pelo ship/rollback. Não editar à mão.
- `<repo>/docs/spec/chronicles/{🟡|🟢|🔴}-<timestamp>-<sha7>-<slug>.md` — **1 MD por mudança** (plano + deploy). 🟡 plano sem deploy, 🟢 deploy healthy, 🔴 deploy failed/rolled-back. YAML frontmatter captura autor, data, SHA, PR, Issue, resultado.
- `<repo>/docs/spec/CHANGELOG.md` — **cronologia flat** (append-only). Prepended pelo ship a cada deploy. Tem 100% do histórico em uma página, offline.

Schema completo do `project.json` em `.claude/skills/deploy/references/project-schema.md`.

---

## Princípio arquitetural

**Esta skill é metodologia pura. Zero conhecimento sobre projetos específicos.** Tudo que varia entre projetos (paths, portas, domínios, comandos de build/lint, env vars, secrets, gates) vem de `project.json` no repo. Se você está editando esta skill e sente vontade de escrever `Hospital`, `mala-ia.cloud`, `8000`, `/api/health`, ou um caminho `/Users/...` — pare. Esse valor pertence ao `project.json`.

A skill executa sempre o mesmo algoritmo (pre-flight → commit → push → monitor → migrations → health → rollback se falhar → reescrever JSONs → criar/atualizar chronicle). Cada passo é completamente parametrizado pelo `project.json` do repo atual.

---

## Princípios operacionais

1. **Silencioso quando passa, vocal quando falha.** Pre-flight só reporta itens que quebraram. `--verbose` expõe tudo.
2. **Mínimo de perguntas.** A única pergunta no caminho feliz do `ship` é confirmação da mensagem de commit. `setup` pergunta o necessário pra construir o `project.json`. Status/rollback não perguntam (rollback só pede confirmação do alvo).
3. **Migrations destrutivas sempre pedem confirmação explícita.** DROP, TRUNCATE, DELETE-sem-WHERE, ALTER-DROP: mostra SQL e espera "y".
4. **Idempotência:** rodar 2× sem mudança = mesmo resultado. JSONs são reescritos inteiros (sem merge parcial); HTML é regerado a partir do template.
5. **Secrets nunca vazam.** Valores de env vars nunca vão para log, commit, JSON, HTML ou histórico. Só existem em memória durante execução e no Coolify. JSONs guardam apenas `name` + `present: true|false`. Antes de escrever `state.json`, a skill roda gate de regex anti-vazamento: se um valor escalar bate `(?:[a-zA-Z0-9+/]{40,}|sk-[a-zA-Z0-9]{20,})`, o write é abortado.

---

## Bootstrap (executado em todo modo, antes de qualquer outra coisa)

1. **Descobrir raiz do repo:**
   ```bash
   REPO_ROOT=$(git -C "$PWD" rev-parse --show-toplevel)
   ```
   Se falhar (não é repo git) → reportar "Não é um repositório git." e PARAR.

2. **Ler `project.json`:** `$REPO_ROOT/docs/spec/deploy/project.json`.

   - **Existe e válido (schema 2.0):** seguir.
   - **Existe mas inválido** (campo obrigatório ausente, schema_version != "2.0"): reportar erro específico de schema e PARAR.
   - **Ausente, mas existe `state.json` schema 1.0** (sem `project.json` ao lado): reportar "Blueprint legado v1 detectado. Rode `/deploy migrate-blueprint` para gerar o `project.json`." e PARAR.
   - **Ausente, mas existe `blueprint/DEPLOY.md` (legado v0):** reportar "Blueprint legado v0 detectado. Rode `/deploy migrate-blueprint`." e PARAR.
   - **Nada existe e modo == `setup`:** seguir (setup vai criar tudo).
   - **Nada existe e modo != `setup`:** reportar "Blueprint não configurado. Rode `/deploy setup` primeiro." e PARAR.

3. **Validar campos obrigatórios** do `project.json`:
   - `schema_version == "2.0"`
   - `project.name` (string, não vazia)
   - `project.slug` (string, ASCII)
   - `git.repo` (formato `owner/name`)
   - `git.branch` (string)
   - `coolify.project_uuid`, `coolify.server_uuid`, `coolify.github_app_uuid`
   - `services` (array com pelo menos 1 elemento, cada um com `id`, `type`, `uuid`, `build`, `deploy`)

   Schema completo: ver `references/project-schema.md`.

---

## Modo `ship` (default, sem argumento)

Fluxo linear pós-bootstrap.

### Passo 1 — Carregar estado atual

Ler `<repo>/docs/spec/deploy/state.json` (schema 1.0 mantido). Extrair último deploy registrado por service. Se ausente → este é o primeiro ship pós-setup; tratar todos os services como "stale" e todas as migrations (se houver) como "novas".

### Passo 2 — Pre-flight (silencioso se tudo ok)

Executar em ordem. Cada gate **só roda se ativado pelo `project.json`**. Se qualquer item ativo falhar: reportar erro específico e PARAR.

#### 2.1 Git status limpo de secrets

Sempre roda. Lista de glob patterns vem de `project.hard_excluded`.

```bash
git -C "$REPO_ROOT" status --short | \
  grep -iE "^\?\?|^ ?[MA] " | \
  grep -iE "$(echo "$HARD_EXCLUDED_REGEX")" || true
```

Se qualquer linha retornar → ❌ listar arquivos, instruir `git reset HEAD <arquivo>` e adicionar ao `.gitignore`.

#### 2.2 Pasta de backup de migrations ausente

Só roda se `project.gates.migrations_backup_dir != null`.

```bash
test ! -d "$REPO_ROOT/$(jq -r .gates.migrations_backup_dir <<< "$PROJECT_JSON")"
```

Se existir → ❌ oferecer `rm -rf` com confirmação.

#### 2.3 Sincronia config ↔ env example

Só roda se `project.gates.env_example_sync != null`. Os campos `config_file`, `example_file`, `config_class` vêm do gate.

Se `config_file` termina em `.py` e `config_class` está setado: ler classe Pydantic `Settings` e extrair atributos.
Se `config_file` termina em `.ts`/`.js`: extrair chaves de `z.object({...})` ou similar (parser leve).

Comparar sets de chaves entre `config_file` e `example_file`:
- Chaves em config e não em example → ❌ adicionar ao example
- Chaves em example e não em config → ❌ remover do example

#### 2.4 Lint (pula se `--skip-lint`)

Para cada `service` em `project.services`:
- Se `service.lint == null` → pula esse service.
- Se `service.lint.trigger_paths` definido e nenhum arquivo do diff casa → pula esse service.
- Senão:
  ```bash
  cd "$REPO_ROOT/$(jq -r .lint.cwd <<< "$SVC")"
  $(jq -r .lint.cmd <<< "$SVC")
  ```
- Se `service.lint.format_check_cmd` definido, rodar também. Se falhar e `format_fix_cmd` definido, oferecer rodar.

Se qualquer comando falhar → ❌ mostrar primeiros 20 erros e PARAR.

#### 2.5 Vars obrigatórias no Coolify

Para cada `service` com `service.uuid` setado:
- `mcp__coolify__env_vars` com `action: "list"`, `uuid: <service.uuid>`, `resource: "application"` (ou `"service"` se `service.type == "supabase"`).
- Comparar keys retornadas com `service.env_keys.runtime_required`. Se faltar alguma → ❌ listar faltantes e PARAR.

#### 2.6 Vars prod-only com valores exatos

Para cada `service.prod_only_assertions[]` (lista de `{key, value, comparison}`):
- Comparar valor atual no Coolify com `value` esperado conforme `comparison` (`eq` | `regex`).
- Qualquer divergência → ❌ mostrar o que está errado e como corrigir (via `mcp__coolify__env_vars update`) e PARAR. Oferecer corrigir via MCP com confirmação.

#### 2.7 Vars build-time marcadas

Para cada `service` com `service.env_keys.build_time_must_be_marked == true`:
- Para cada key em `service.env_keys.build_time`, validar `is_build_time == true` no Coolify.
- Se alguma não tiver → ❌ oferecer `mcp__coolify__bulk_env_update` pra corrigir todas de uma vez.

#### 2.8 Secrets auto-gerados presentes

Para cada secret em `project.secrets_auto_generated[]`:
1. Verificar se a key existe no service correspondente (output de 2.5) e o valor não é vazio.
2. Se faltar/vazio:
   - Perguntar: "Secret `X` ausente em `<service>`. Gero e seto agora? (y/n)"
   - Se `y`: executar o `secret.generator` (comando local), capturar saída, `mcp__coolify__env_vars create` no service UUID. NUNCA logar ou salvar o valor.
   - Se `n`: ❌ PARAR. Instruir configuração manual.
3. Se presente com valor não-vazio: silencioso (idempotente).

#### 2.9 Listar migrations novas

Só roda se `project.migrations != null`.

```bash
ls "$REPO_ROOT/$(jq -r .migrations.dir <<< "$PROJECT_JSON")" | sort
```

Comparar com `state.migrations.last_applied`. Arquivos posteriores → "novas migrations".

Se houver: listar nomes para aplicar no Passo 6. **Não bloqueia pre-flight.**

Se é o primeiro deploy (state.migrations vazio): TODAS as migrations são "novas".

#### 2.10 CORS audit (gate `cors_audit`, fail)

Só roda se `project.gates.cors_audit.enabled == true`.

Pra cada arquivo em `project.gates.cors_audit.scan_files`:
```bash
for pattern in $(jq -r '.gates.cors_audit.bad_patterns[]' <<< "$PROJECT_JSON"); do
  grep -nF -- "$pattern" "$REPO_ROOT/<arquivo>" || true
done
```

Padrões clássicos a procurar: `allow_origins=["*"]`, `allow_origin_regex=".*"`, `Access-Control-Allow-Origin: *` literal em response, `allow_credentials=True` combinado com `*`.

Se qualquer ocorrência aparecer → ❌ listar `arquivo:linha:padrão` e PARAR. Mensagem: "CORS aberto detectado. Travar pra domínios próprios antes de subir pra produção."

#### 2.11 FK index warning (gate `fk_index_warning`, warn-only)

Só roda se `project.gates.fk_index_warning.enabled == true`.

Para cada migration nova listada em 2.9 com `REFERENCES`:
- Extrair `(tabela, coluna)` da declaração `<coluna> ... REFERENCES <pai>(...)`.
- Procurar `CREATE INDEX ... ON <tabela>(<coluna>` (ou index parcial cobrindo `<coluna>`) em qualquer arquivo `.sql` do `project.gates.fk_index_warning.scan_dir`.
- Se não achar → ⚠ avisar `<arquivo>: nova FK <tabela>.<coluna> sem index`. Continuar.

Modo `warn`: nunca bloqueia o deploy, só aparece em `--verbose` e sempre quando há ocorrência.

### Passo 3 — Inferir mensagem de commit

Ler `git diff --stat HEAD` e `git status --short`.

Mapear arquivos modificados a escopos via `project.commit_inference.scope_map` (path glob → escopo). Se nenhum mapeamento bate → escopo default = "core".

Heurísticas pra prefixo conventional:
- Novo arquivo em `**/routers/`, `**/api/` → `feat(<escopo>): <resumo>`
- Mudança em `**/test_*.py`, `**/__tests__/**`, `**/tests/**` → `test(<escopo>): <resumo>`
- Só `.md` mudou → `docs(<escopo>): <resumo>`
- `package.json`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, lockfiles → `chore(<escopo>): <resumo>`
- Padrão default → analisar diff e escolher `feat`/`fix`/`refactor`

**Resumo** = descrição curta inferida do diff (máx `commit_inference.subject_max_chars` chars, default 60).

**Mostrar ao usuário:**
```
Mensagem de commit inferida:
  <msg inferida>

Arquivos a incluir (<N>):
  <lista, máx 20 linhas>

Arquivos hard-excluded encontrados (não vão no commit):
  <lista, se houver>

Migrations novas: <N> arquivo(s)
<lista se houver, ou "—" se project.migrations == null>

Continuar? [enter=sim / e=editar msg / n=abortar]
```

- Enter → seguir com msg inferida
- `e` → pedir nova msg via prompt
- `n` → PARAR (exit code 0, sem erro)

### Passo 3.5 — Sincronizar `APP_VERSION` no Coolify

Antes do commit + push (que vai disparar o build no Coolify via webhook), garantir que `APP_VERSION` no service backend bate com a versão atual de `hospital-reunioes/frontend/package.json` (fonte da verdade — ver `docs/spec/VERSIONING.md`).

**Quando esse passo importa:** `/deploy ship` invocado **standalone** (sem `/ship`). Quando o `/ship` orquestra o ciclo completo, o Passo 8.5 do `/ship` já sincronizou antes do merge — aqui é defensivo puro (no-op se já bate).

```bash
APP_VERSION=$(python3 -c "import json; print(json.load(open('hospital-reunioes/frontend/package.json'))['version'])")
BACKEND_UUID=$(jq -r '.services[] | select(.id == "backend") | .uuid' <<< "$PROJECT_JSON")

# Setar env no Coolify ANTES do push pra evitar race com webhook auto-deploy
mcp__coolify__bulk_env_update --uuid "$BACKEND_UUID" --vars "APP_VERSION=$APP_VERSION"
```

**Idempotente** — se a env já está com o valor certo (comparar com `state.json:last_app_version`), pular silenciosamente sem chamar o MCP.

Salvar `expected_app_version = $APP_VERSION` em memória — usado no Passo 7.2 pra validar match pós-deploy.

Se o usuário rodar `/deploy ship` em projeto sem `frontend/package.json` (improvável aqui, mas a skill é universal): pular este passo silenciosamente.

---

### Passo 4 — Commit + push

```bash
cd "$REPO_ROOT"
git add <arquivos modificados, menos hard-excluded>
git commit -m "<msg confirmada>"
git push origin "$(jq -r .git.branch <<< "$PROJECT_JSON")"
```

**Nunca** `git add -A` ou `git add .`. Sempre lista explícita excluindo `project.hard_excluded`.

Se push falhar (ex: divergência com remote): reportar erro bruto, sugerir `git pull --rebase origin <branch>` manual e PARAR.

Capturar SHA: `git rev-parse --short HEAD`.

### Passo 5 — Monitorar deploy Coolify

Determinar serviços afetados pelo diff: cruzar `git diff --name-only HEAD~1 HEAD` com `service.diff_routing.trigger_paths` de cada service. Service afetado = ao menos 1 arquivo casa.

Se nenhum casa mas há mudanças → fallback "afeta todos com `service.type` em `{nextjs, fastapi, node, python, generic}`" (services que rebuildam por mudança no repo).

Para cada service afetado:
1. `mcp__coolify__deployment` `action: "list_for_app"`, `uuid: <service.uuid>` → encontrar deploy mais recente (disparado pelo webhook).
2. Loop: `mcp__coolify__deployment` `action: "get"`, `uuid: <deployment_uuid>` a cada ~10s.
3. Reportar progresso compacto: `<service.id>: queued → building → deploying → finished (1m12s)`.
4. Parar loop quando status for `finished` ou `failed`.

Se `failed` → capturar logs (`lines: 150`), mostrar, seguir Passo 8 (rollback automático).

**Capturar `build_duration_seconds`** por service (delta `started_at` → `finished_at`). Persistir em memória pra Passo 9.

### Passo 6 — Aplicar migrations novas (se houver)

Pular se `--no-migrations`, se `project.migrations == null`, ou se lista vazia.

#### 6.1 Classificar statements

Para cada arquivo novo em `<repo>/<project.migrations.dir>`:
- Parse SQL (split por `;` considerando strings).
- Pra cada statement, checar regex destrutiva (lista no fim deste documento + `project.migrations.destructive_regex_extra`).
- Classificar arquivo: **SAFE** (nenhum match) | **DESTRUCTIVE** (≥1 match).

#### 6.2 Aplicar SAFE automaticamente

Para cada migration SAFE em ordem cronológica:
- Identificar container via `project.migrations.container_pattern` (ex: `supabase-db-*`) → primeiro container que casa.
- Executar:
  ```bash
  docker exec -i <container> psql -U <project.migrations.user> -d <project.migrations.db> -f - << 'EOF'
  <SQL da migration>
  EOF
  ```

Reportar: `migrations applied: <N> safe, 0 skipped`.

Em erro SQL: capturar output, PARAR, reportar qual migration falhou e em que statement.

#### 6.3 Migrations DESTRUCTIVE — pedir confirmação

```
⚠ Migration com DDL destrutivo detectada:
  Arquivo: <nome>
  Statements afetados: <lista com nº de linha>
  SQL completo:
  ---
  <conteúdo>
  ---
  Aplicar? [y/n]
```

- `y` → aplicar como SAFE.
- `n` → pular, registrar "skipped por usuário". Perguntar se aborta ou segue sem aplicar.

#### 6.4 Verificação pós-migrations

Para cada service que depende do banco (heurística: `service.type` em `{fastapi, python, node}` + presença de chave `*_DATABASE_URL`/`SUPABASE_*` em runtime_required):
- `mcp__coolify__diagnose_app` → deve continuar healthy.
- Se não healthy: mostrar logs e disparar rollback (Passo 8).

### Passo 7 — Health check

Para cada service afetado:
- Se `service.deploy.health_check.expected_body_regex == null`:
  ```bash
  curl -fsSI --max-time 10 -w "%{time_total}" "<service.deploy.health_check.url>"
  ```
  Esperado: `<expected_status>` (ex: 200).
- Se `expected_body_regex != null`:
  ```bash
  curl -fsS --max-time 10 -w "\n%{time_total}" "<service.deploy.health_check.url><health_check.path>"
  ```
  Esperado: status `<expected_status>` e body casa regex.

Combinar com `mcp__coolify__diagnose_app`.

Capturar `latency_ms` (em ms) e `http_status` por service. Persistir em memória.

#### 7.1 Health rico (gate `health_rich`, fail)

Só roda se `project.gates.health_rich.enabled == true`.

Após o curl do health endpoint passar status+regex, parsear o body como JSON e validar:
```bash
for key in $(jq -r '.gates.health_rich.required_keys[]' <<< "$PROJECT_JSON"); do
  jq -e --arg k "$key" 'has($k)' <<< "$HEALTH_BODY" >/dev/null || MISSING="$MISSING $key"
done
```

Se faltar qualquer key → ❌ listar keys ausentes (ex: "health body sem campo `db`") e disparar Passo 8 (rollback automático). Mensagem: "Health endpoint retornou body incompleto, app pode estar respondendo sem checar dependências críticas."

Se algum check falhar → Passo 8.

#### 7.2 Version match (gate inerente ao versionamento visível)

Se o Passo 3.5 setou `expected_app_version`, validar que o backend retornou a versão esperada:

```bash
ACTUAL=$(jq -r .version <<< "$HEALTH_BODY")
if [ "$ACTUAL" != "$expected_app_version" ]; then
  # APP_VERSION env não chegou ao container ou Coolify não picked up
  # Rollback automático — versão visível na UI viraria mentirosa
  trigger_rollback "version_mismatch" "esperava v$expected_app_version, /api/health retornou v$ACTUAL"
fi
```

Se mismatch → Passo 8 (rollback). Mensagem: "APP_VERSION do Coolify não bate com /api/health — o rodapé da app exibiria versão errada."

### Passo 8 — Rollback automático (se health falhou)

Executar 1×:
1. Ler `<repo>/docs/spec/deploy/history.json` → último deploy com `result == "healthy"` por service afetado.
2. Pra cada service: `mcp__coolify__deployment list_for_app` → encontrar deployment_uuid daquele SHA.
3. `mcp__coolify__deploy` com aquele `deployment_uuid`.
4. Monitorar (loop Passo 5).
5. Health check (Passo 7).

Se health pós-rollback OK → registrar entrada com tag `[ROLLBACK-AUTO]`, reportar, parar.
Se falhar → PARAR. Logs completos + pedir intervenção humana. Tag `[FAIL-TOTAL]`.

Nunca rollback em loop.

### Passo 9 — Reescrever JSONs, regerar PROJETO.md, criar implementação

Atualizar 4 artefatos: 2 JSONs + 1 MD humano consolidado + 1 MD da implementação. JSONs e MD humano reescritos inteiros (idempotentes); implementação é arquivo novo único por ship.

#### 9.1 Reescrever `state.json` (schema 1.0)

Snapshot completo:

```json
{
  "schema_version": "1.0",
  "updated_at": "<ISO-8601 com timezone local>",
  "updated_by": "deploy-skill@<mode>",
  "production": {
    "domain_root": "<project.coolify.domain_root>",
    "vps_ip": "<project.coolify.vps_ip>",
    "coolify_url": "<project.coolify.url>",
    "project_uuid": "<project.coolify.project_uuid>",
    "server_uuid": "<project.coolify.server_uuid>",
    "github_app_uuid": "<project.coolify.github_app_uuid>",
    "repo": "<project.git.repo>",
    "branch": "<project.git.branch>",
    "project_name": "<project.project.name>"
  },
  "last_app_version": "<vX.Y.Z lida de frontend/package.json — versão semântica humana>",
  "services": [
    {
      "id": "<service.id>", "uuid": "<service.uuid>",
      "domain": "<host extraído de service.deploy.fqdn>",
      "port": <service.build.ports_exposes>,
      "health_path": "<service.deploy.health_check.path>",
      "status": "healthy|warning|down",
      "last_deploy_sha": "<sha curto>",
      "last_deploy_at": "<ISO>",
      "last_health_check": { "at": "<ISO>", "latency_ms": <int|null>, "http_status": <int>, "body_ok": <bool> },
      "build_duration_seconds": <int|null>,
      "env_count": <int>
    }
  ],
  "env_vars": { /* mapeado de project.services[].env_keys + violações detectadas */ },
  "secrets": [{ "name": "<>", "service": "<>", "present": true|false }],
  "migrations": { "total_applied": <int>, "last_applied": "<>", "pending_local": [] },
  "gates": [{ "name": "<>", "status": "ok|warn|fail|skip" }],
  "next_actions": [{ "kind": "ok|warn|info", "title": "<>", "text": "<>" }],
  "last_run": { "mode": "ship", "sha": "<sha>", "result": "healthy|rolled-back|failed", "duration_seconds": <int> }
}
```

**Gate anti-vazamento ANTES de escrever:** rodar regex `(?:[a-zA-Z0-9+/]{40,}|sk-[a-zA-Z0-9]{20,})` em todos valores escalares serializados. Se bater, ABORTAR e reportar: "Possível vazamento em state.json. Campo: <path>".

#### 9.2 Prepend em `history.json`

Inserir nova entrada no início de `deploys[]` e truncar a 50:

```json
{
  "at": "<ISO>",
  "sha": "<sha curto>",
  "app_version": "<vX.Y.Z, ou null se projeto sem semver>",
  "subject": "<msg humana em pt-BR sem prefixo conventional>",
  "raw_subject": "<msg de commit original>",
  "scope": ["<service.id>", ...],
  "result": "healthy|rolled-back|failed",
  "duration_seconds": <int>,
  "services_touched": [...],
  "env_changes": [{ "service": "<>", "action": "create|update|delete", "keys": [...] }],
  "migrations_applied": ["nome.sql", ...],
  "rollback_target_sha": "<sha>" | null,
  "notes": "<texto livre, máx 280 chars>"
}
```

`subject` é versão humanizada; se inferência ficar pobre, usar `raw_subject` em ambos.

#### 9.3 Criar/atualizar `docs/spec/chronicles/{🟢|🔴}-<timestamp>-<sha7>-<slug>.md`

Cronologia humana de produção. 1 MD por mudança (plano + deploy). 3 estados:

- **🟡** plano sem deploy (criado manualmente pelo usuário).
- **🟢** plano + deploy healthy.
- **🔴** plano + deploy failed / rolled-back / migration-failed.

Quando o `/deploy ship` roda, este passo:
1. Procura um plano 🟡 existente cujo slug tenha boa similaridade com o slug do commit.
2. Se acha: anexa uma seção `## Implementação / Deploy` no final do MD do plano e renomeia `🟡 → 🟢` (ou 🔴).
3. Se não acha: cria um novo MD `🟢-...` (ou 🔴) com slug do commit, sem corpo de plano.

Pre-flight falhando antes do commit **não** gera MD — não houve "tentativa real".

```bash
python3 - << 'PY'
import json, os, re, sys, unicodedata
from datetime import datetime
from pathlib import Path

REPO = os.environ["REPO_ROOT"]
BP = Path(REPO) / "docs" / "spec"
CHRONICLES = BP / "chronicles"
CHRONICLES.mkdir(parents=True, exist_ok=True)

state = json.loads((BP / "deploy" / "state.json").read_text())
history = json.loads((BP / "deploy" / "history.json").read_text())

last_run = state.get("last_run", {})
last_history = history.get("deploys", [{}])[0] if isinstance(history, dict) else (history[0] if isinstance(history, list) and history else {})

sha = (last_run.get("sha") or last_history.get("sha") or "")[:7] or "unknown"
result = last_run.get("result") or last_history.get("result") or "unknown"
mode = last_run.get("mode", "ship")

ts_iso = last_history.get("at") or state.get("updated_at") or datetime.now().isoformat()
try:
    ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
except Exception:
    ts = datetime.now()

# --- Slug + tokens helpers --------------------------------------------------
STOPWORDS = {"fix","data","chore","feat","refactor","test","docs","ci","build","perf",
             "com","via","para","pra","sem","sob","the","and","for","from","with",
             "ata","pdf","new","old"}

def normalize_ascii(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii","ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+","-",text).strip("-")
    return re.sub(r"-+","-",text)

def commit_text_full(raw):
    """Texto canônico do commit pra matching (sem truncar)."""
    if not raw: return ""
    m = re.match(r"^([a-zA-Z]+)(?:\(([^)]+)\))?:\s*(.+)$", raw.strip())
    if m:
        _t, scope, desc = m.groups()
        text = f"{scope} {desc}" if scope else desc
    else:
        text = raw
    return normalize_ascii(text)

def make_slug(raw):
    """Slug truncado em 50 chars pra usar no filename."""
    s = commit_text_full(raw)
    if len(s) > 50:
        s = s[:50].rsplit("-",1)[0] if "-" in s[:50] else s[:50]
    return s

def tokens(slug):
    return {t for t in slug.split("-") if len(t) >= 3 and t not in STOPWORDS}

raw_subject = last_history.get("raw_subject") or last_history.get("subject") or ""
slug = make_slug(raw_subject)
commit_full = commit_text_full(raw_subject)
commit_toks = tokens(commit_full)

# --- Prefix de cor baseado no resultado -------------------------------------
PREFIX = {
    "healthy": "🟢", "failed": "🔴", "build-failed": "🔴", "migration-failed": "🔴",
    "rolled-back": "🟡", "rollback-manual": "🟡",
}.get(result, "🟢")

# --- Procurar plano 🟡 com slug similar -------------------------------------
def parse_plano(path):
    """Espera 🟡-YYYY-MM-DD-HHMM-<slug>.md. Retorna (slug, mtime) ou None."""
    m = re.match(r"^🟡-(\d{4})-(\d{2})-(\d{2})-(\d{4})-(.+)$", path.stem)
    if not m: return None
    return m.group(5), path.stat().st_mtime

def find_plano_match():
    if not commit_toks:
        return None
    candidates = []
    for p in CHRONICLES.glob("🟡-*.md"):
        parsed = parse_plano(p)
        if not parsed: continue
        plano_slug, mtime = parsed
        p_toks = tokens(plano_slug)
        if not p_toks: continue
        common = p_toks & commit_toks
        if not common: continue
        smaller = min(len(p_toks), len(commit_toks))
        overlap = len(common) / smaller if smaller > 0 else 0
        if overlap >= 0.6:
            candidates.append((p, overlap, mtime, plano_slug))
    if not candidates: return None
    candidates.sort(key=lambda x: (-x[1], -x[2]))
    return candidates[0]

plano_match = find_plano_match()

# --- Decidir caminho final --------------------------------------------------
# Regra: o timestamp no NOME do arquivo sempre reflete o evento mais recente.
# Plano 🟡 puro → timestamp da criação. Quando vira 🟢/🔴 via deploy →
# timestamp do deploy (sobrescreve o original). Isso garante que ao ordenar
# por nome, a ordem cronológica reflete "última atualização".
deploy_date_hhmm = ts.strftime('%Y-%m-%d-%H%M')

if plano_match:
    src_plano, overlap, _mt, plano_slug = plano_match
    # Preserva o slug do plano (escolhido por humano); usa timestamp do DEPLOY.
    m = re.match(r"^🟡-\d{4}-\d{2}-\d{2}-\d{4}-(.+)\.md$", src_plano.name)
    plano_slug_clean = m.group(1) if m else plano_slug
    new_name = f"{PREFIX}-{deploy_date_hhmm}-{sha}-{plano_slug_clean}.md"
    new_path = CHRONICLES / new_name
else:
    new_name = f"{PREFIX}-{deploy_date_hhmm}-{sha}-{slug}.md" if slug else f"{PREFIX}-{deploy_date_hhmm}-{sha}.md"
    new_path = CHRONICLES / new_name

# Gate idempotência: arquivo final já existe → sai.
if new_path.exists():
    print(f"mudança já registrada (idempotente): {new_path.name}")
    sys.exit(0)

# --- Bloco "Implementação / Deploy" -----------------------------------------
result_emoji = {"healthy":"🟢","failed":"🔴","build-failed":"🔴","rolled-back":"🟡","rollback-manual":"🟡","migration-failed":"🔴"}.get(result,"⚪")

block = []
block.append("## Implementação / Deploy")
block.append("")
subject_display = last_history.get("subject") or last_history.get("raw_subject") or ""
if subject_display:
    block.append(f"**{subject_display}**")
    block.append("")
block.append(f"- **Data**: {ts.strftime('%Y-%m-%d %H:%M %z').strip()}")
block.append(f"- **SHA**: `{sha}`")
block.append(f"- **Modo**: {mode}")
block.append(f"- **Resultado**: {result_emoji} {result}")
if last_history.get("raw_subject") and last_history.get("raw_subject") != last_history.get("subject"):
    block.append(f"- **Commit raw**: `{last_history['raw_subject']}`")
if last_history.get("rollback_target_sha"):
    block.append(f"- **Rollback alvo**: `{last_history['rollback_target_sha']}`")
block.append("")

if last_history.get("services_touched"):
    block.append("### Serviços tocados")
    block.append("")
    for s in last_history["services_touched"]:
        block.append(f"- {s}")
    block.append("")

if last_history.get("migrations_applied"):
    block.append("### Migrations aplicadas")
    block.append("")
    for mg in last_history["migrations_applied"]:
        block.append(f"- `{mg}`")
    block.append("")

if last_history.get("env_changes"):
    block.append("### Mudanças de variáveis")
    block.append("")
    for ec in last_history["env_changes"]:
        action = ec.get("action","?"); service = ec.get("service","?")
        keys = ", ".join(ec.get("keys",[]))
        block.append(f"- {service}: {action} `{keys}`")
    block.append("")

if last_history.get("notes"):
    block.append("### Notas")
    block.append("")
    block.append(last_history["notes"])
    block.append("")

block.append("---")
block.append(f"_Atualizado automaticamente pelo `/deploy ship` em {ts.strftime('%Y-%m-%d')}._")

block_text = "\n".join(block)

# --- Escrever ----------------------------------------------------------------
if plano_match:
    # Move plano → novo nome, anexa seção
    plano_text = src_plano.read_text()
    merged = plano_text.rstrip() + "\n\n---\n\n" + block_text + "\n"
    src_plano.rename(new_path)
    new_path.write_text(merged)
    print(f"mudança atualizada (plano 🟡 → {PREFIX}): {new_path.name}")
    print(f"  └─ plano consumido: {src_plano.name}")
else:
    # Cria do zero (sem corpo de plano)
    head = [f"# {subject_display or f'Deploy {sha}'}", ""]
    head.append("> Mudança criada direto pelo `/deploy ship` (sem plano 🟡 prévio).")
    head.append("")
    md_text = "\n".join(head) + block_text + "\n"
    new_path.write_text(md_text)
    print(f"mudança criada ({PREFIX}): {new_path.name}")
PY
```

#### 9.3.5 Finalizar ou descartar plano (`docs/planejamento/em-andamento/`)

> **Integração com Eixo A do plano de enxugamento.** Plano vive em `docs/planejamento/em-andamento/` durante o trabalho. Ao final:
> - **Deploy healthy** → status: `finalizado`, **move** pra `docs/planejamento/finalizado/`.
> - **Deploy failed / rolled-back / abandonado** → arquivo é **deletado** do `em-andamento/`. Cronologia da falha sobrevive no chronicle 🔴 (`docs/spec/chronicles/`) e no `history.json`. Sem entrada vazia em `finalizado/` poluindo o explorer.

```bash
# Achar plano associado ao chronicle atual (campo `planejamento:` no frontmatter do chronicle)
PLAN_REL=""
if [ -n "$CHRONICLE_FINAL_PATH" ] && [ -f "$REPO_ROOT/$CHRONICLE_FINAL_PATH" ]; then
  PLAN_REL=$(grep "^planejamento:" "$REPO_ROOT/$CHRONICLE_FINAL_PATH" | sed 's/^planejamento:\s*//' | tr -d '"')
fi

# Fallback: procura plano cuja branch bate (em subpastas plan-mode/superpowers/manual + raiz legado)
if [ -z "$PLAN_REL" ] || [ ! -f "$REPO_ROOT/$PLAN_REL" ]; then
  for f in "$REPO_ROOT/docs/planejamento/em-andamento/"*/*.md "$REPO_ROOT/docs/planejamento/em-andamento/"*.md; do
    [ -f "$f" ] || continue
    if grep -qE "^branch:\s*$BRANCH$" "$f"; then
      PLAN_REL="${f#$REPO_ROOT/}"
      break
    fi
  done
fi

if [ -n "$PLAN_REL" ] && [ -f "$REPO_ROOT/$PLAN_REL" ]; then
  case "$RESULT" in
    healthy)
      # Caminho feliz: atualiza frontmatter, recalcula header, move pra finalizado/<source>/
      python3 - << PY
import re
from datetime import datetime, timezone

p = "$REPO_ROOT/$PLAN_REL"
content = open(p).read()

content = re.sub(r"^status:.*$", "status: finalizado", content, count=1, flags=re.MULTILINE)
content = re.sub(r"^sha_atual:.*$", "sha_atual: $SHA", content, count=1, flags=re.MULTILINE)
content = re.sub(r"^chronicle:.*$", "chronicle: $CHRONICLE_FINAL_PATH", content, count=1, flags=re.MULTILINE)
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
content = re.sub(r"^date_last_touched:.*$", f"date_last_touched: {now_iso}", content, count=1, flags=re.MULTILINE)

open(p, "w").write(content)
PY

      # Reescreve header de progresso final (refletindo "100%" se todas tarefas concluídas).
      # Idempotente: chamar este script depois do python acima é seguro.
      bash "$REPO_ROOT/.claude/skills/planejamento/scripts/recalc_progress.sh" "$REPO_ROOT/$PLAN_REL"

      # Calcula destino preservando subpasta de origem (plan-mode/, superpowers/, manual/).
      # Se plano vier do raiz legado, manda pra finalizado/manual/ por convenção.
      BASENAME=$(basename "$PLAN_REL")
      REL_DIR=$(dirname "$PLAN_REL")  # ex: docs/planejamento/em-andamento/plan-mode
      SOURCE=$(basename "$REL_DIR")    # ex: plan-mode (ou em-andamento se raiz legado)
      if [ "$SOURCE" = "em-andamento" ]; then SOURCE="manual"; fi
      NEW_REL="docs/planejamento/finalizado/$SOURCE/$BASENAME"
      mkdir -p "$REPO_ROOT/docs/planejamento/finalizado/$SOURCE"
      git -C "$REPO_ROOT" mv "$PLAN_REL" "$NEW_REL"
      echo "plano finalizado: $PLAN_REL → $NEW_REL"
      ;;

    rolled-back|rollback-manual|failed|build-failed|migration-failed)
      # Falha definitiva: deleta o plano. Cronologia vive no chronicle 🔴 + history.json.
      git -C "$REPO_ROOT" rm "$PLAN_REL"
      echo "plano descartado: $PLAN_REL (resultado: $RESULT — cronologia da falha em $CHRONICLE_FINAL_PATH e history.json)"
      ;;

    *)
      # Resultado desconhecido: trata como healthy por default (conservador)
      echo "[deploy] resultado '$RESULT' não mapeado — mantendo plano em em-andamento/ pra inspeção manual."
      ;;
  esac
else
  echo "[deploy] sem plano em em-andamento/ pra processar (branch $BRANCH). Continuando."
fi
```

Idempotência: se plano já está em `finalizado/` (re-run do ship pós-rollback bem-sucedido), no-op. Se já foi deletado (falha anterior), `git rm` falha silenciosamente — siga.

#### 9.4 Regenerar snapshot da aplicação (skill `/snapshot`)

Logo após o health check pós-deploy passar verde (e antes do prepend no CHANGELOG), invocar o script `snapshot.py` pra manter `docs/spec/snapshots/` fresco:

```bash
python3 .claude/skills/snapshot/scripts/snapshot.py
```

A skill é **idempotente** — se nada relevante mudou (`hospital-reunioes/backend/app/routers/**`, `hospital-reunioes/supabase/migrations/**`, `docs/spec/deploy/project.json`), não escreve nem commita.

Se mudou, a skill:
1. Regenera ROTAS.md, ENTIDADES.md, SCHEMA.md, MIGRATIONS.md, INTEGRACOES.md (auto-gerado).
2. Preserva blocos `<!-- curated:start -->...<!-- curated:end -->` em FLUXOGRAMAS.md e ESTRUTURA.md.
3. Faz **commit separado** no branch atual (geralmente `main`, pós-merge):
   ```
   chore(spec): atualizar snapshot pós deploy <sha7>
   ```
4. **Não dispara novo `/deploy ship`** — o `commit_inference.scope_map` no `project.json` mapeia `docs/spec/snapshots/**` pra escopo `spec`, e commits `chore(spec):` que tocam só `.md` não geram trigger de service (heurística no Passo 5 do ship).

Se a skill `/snapshot` falhar (ex: parser SQL quebrou em migration nova), **não bloqueia o deploy** — registra warning no output do `/deploy` e segue pra 9.5 (CHANGELOG). O usuário pode rodar `/snapshot --check` depois pra diagnosticar.

Detalhes da skill: `.claude/skills/snapshot/SKILL.md`.

#### 9.5 Prepend em `docs/spec/CHANGELOG.md`

> **Esta é a ÚNICA skill que escreve em `docs/spec/CHANGELOG.md`.** A skill `/ship` Passo 11 propositalmente NÃO prependa — display only. Único caminho de escrita: `/deploy ship` (modo ship) ou `/deploy rollback` (modo rollback). Edição manual fora dessas duas skills é desencorajada (cria divergência com `history.json`).

Cronologia flat, append-only (prepend, mais recente no topo). 1 entrada por deploy concluído.

```bash
CHANGELOG="$REPO_ROOT/docs/spec/CHANGELOG.md"

# Cria com header se não existir
if [ ! -f "$CHANGELOG" ]; then
  printf '# Changelog Hospital Reuniões\n\nCronologia de deploys em ordem reversa (mais recente no topo).\nPrepended pelo /deploy ship ao final do ciclo.\n\n---\n\n' > "$CHANGELOG"
fi

python3 /Users/pedrorezende/PedroDev/Hospital/.claude/skills/deploy/scripts/changelog_prepend.py
```

Ver `scripts/changelog_prepend.py` na própria skill — gera entrada com autor (git config), SHA, serviços tocados, resultado e link pro chronicle.

Reportar ao usuário:

```
Chronicle: <REPO_ROOT>/docs/spec/chronicles/<arquivo>.md
CHANGELOG: <REPO_ROOT>/docs/spec/CHANGELOG.md (entrada nova no topo)
```

---

## Modo `setup`

Invocação: `/deploy setup [--dry-run]`. Cria todo o blueprint do zero — só roda quando NÃO existe `project.json` no repo.

Ordem das fases:

### Fase 1 — Identidade do projeto

Perguntar:
1. Nome do projeto (humano, ex: "Meu Projeto")
2. Slug ASCII (sugestão derivada do nome, ex: "meu-projeto")
3. Descrição curta (1 linha)
4. Repo GitHub (`owner/name`, default = inferido de `git remote get-url origin`)
5. Branch de deploy (default: `main`)

### Fase 2 — Detectar stack

Buscar no repo:
- `package.json` com `"next"` em deps → service candidato `nextjs`
- `pyproject.toml` ou `requirements.txt` com `fastapi` → service candidato `fastapi`
- `pyproject.toml` ou `requirements.txt` com `flask`/`django` → `python` (genérico)
- `supabase/config.toml` ou `migrations/*.sql` no padrão Supabase → service candidato `supabase`
- `package.json` com `"react"` mas sem `"next"` → `node` (ou `static` se `build` saída em `dist/`)
- Mais de um `package.json` em subdirs → monorepo, perguntar quais virar service

Reportar stack detectada e confirmar. Pedir `base_directory` de cada service (relativo à raiz do repo).

### Fase 3 — Configuração Coolify

Perguntar:
1. URL do Coolify (default: tenta extrair de outro `project.json` no `~`)
2. UUID do projeto Coolify — se há outros `project.json` no `~/PedroDev/*/docs/spec/deploy/project.json`, oferecer reaproveitar; senão, listar `mcp__coolify__projects` e perguntar
3. UUID do servidor — idem (default: reaproveitar se único)
4. UUID do GitHub App — idem
5. IP da VPS
6. Domínio raiz (ex: `exemplo.com`) — usado pra sugerir FQDN dos services

Para cada service:
- FQDN sugerido baseado em `id` + domain_root (ex: `https://api.exemplo.com` pra service `backend` em domínio `exemplo.com`).
- Porta (default por type: nextjs/node=3000, fastapi=8000).
- Health check path (default por type: nextjs/node=`/`, fastapi=`/api/health`).

### Fase 4 — Validar Dockerfiles (se `build_pack == "dockerfile"`)

Para cada service com `build_pack: "dockerfile"`:
- Verificar Dockerfile no `dockerfile_location` declarado.
- Heurísticas mínimas por type:
  - `nextjs`: multi-stage, `output: 'standalone'` no `next.config.*`, NEXT_PUBLIC_* como ARG no builder, usuário não-root.
  - `fastapi`/`python`: base slim, deps de sistema documentadas, usuário não-root, HEALTHCHECK opcional, CMD sem `--reload`.
- Se ausente ou inadequado: oferecer criar/corrigir. Mostrar diff e confirmar antes de sobrescrever.

### Fase 5 — Criar recursos Coolify

Para cada service:
1. **App** via `mcp__coolify__application create_github`:
   ```
   project_uuid, server_uuid, github_app_uuid (do project.json em construção)
   git_repository, git_branch
   build_pack, base_directory, dockerfile_location (se aplicável), ports_exposes
   fqdn, name (default: `<slug>-<service.id>`)
   ```
2. **Health check Coolify** via `mcp__coolify__application update`:
   - `health_check_enabled`, `health_check_path`, `health_check_port`, `interval`, `retries` — todos vindos de `service.deploy.coolify_health`.

3. **Service Supabase** (só se houver service `type: supabase`):
   - `mcp__coolify__service create` tipo `supabase`, `instant_deploy: false`.
   - Configurar env vars Supabase via `mcp__coolify__env_vars create` (POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY, SERVICE_ROLE_KEY — gerar via `openssl rand -hex 32` pras que precisam).
   - `mcp__coolify__control start`. Aguardar `running`.

Anotar UUIDs retornados em `project.json` em construção.

### Fase 6 — Env vars

Para cada service:
- Ler `.env.example`/`.env.local.example` no `service.lint.cwd`.
- Identificar chaves marcadas `<PREENCHER>` ou vazias.
- Pedir valor 1× cada via prompt seguro (NUNCA logar).
- Aplicar via `mcp__coolify__bulk_env_update` (1 chamada por service).
- Build-time: marcar `is_build_time: true` para chaves listadas em `service.env_keys.build_time`.

### Fase 7 — Secrets auto-gerados

Para cada `secret` em `project.secrets_auto_generated[]` (se a stack tem):
- Executar `secret.generator` localmente.
- `mcp__coolify__env_vars create` no service correspondente (`secret.service`).
- NUNCA logar valor.

### Fase 8 — DNS

Calcular registros A necessários a partir dos `service.deploy.fqdn`. Mostrar tabela:

| Tipo | Nome | Conteúdo | Proxy |
|---|---|---|---|
| A | `<sub>` | `<vps_ip>` | DNS only |

Validar resolução: `dig +short <fqdn>` deve retornar `<vps_ip>`.

Se já resolve: silencioso. Senão: pedir pro usuário criar e confirmar (`y` pra continuar).

### Fase 9 — Primeiro deploy

`mcp__coolify__deploy` em cada service. Monitorar (loop Passo 5 do ship).

### Fase 10 — Inicializar blueprint

Escrever:
- `docs/spec/deploy/project.json` — versão final com UUIDs preenchidos.
- `docs/spec/deploy/state.json` — primeiro snapshot via `mcp__coolify__diagnose_app`/`get_application`/`get_service` (preencher status, SHA, latência).
- `docs/spec/deploy/history.json` — `{"schema_version":"1.0","deploys":[]}`.
- `docs/spec/chronicles/<timestamp>-<sha>-<resultado>.md` — primeira chronicle do projeto (Passo 9.3 do ship).

Reportar:
```
Setup completo. Use `/deploy` para deploys futuros.
project.json: <REPO_ROOT>/docs/spec/deploy/project.json
```

### Dry-run

Executar leituras/validações, pular `create`/`deploy`/`update`. Reportar o que FARIA.

---

## Modo `status`

Invocação: `/deploy status`. Zero alterações.

1. Bootstrap (lê `project.json`).
2. Em paralelo (múltiplas tool calls na mesma mensagem):
   - Pra cada `service`: `mcp__coolify__get_application` (ou `get_service` se type=supabase) + `mcp__coolify__diagnose_app`.
3. SHA local: `git rev-parse --short HEAD`.
4. SHA em prod: por service via `mcp__coolify__deployment list_for_app` (último).
5. Migrations pendentes: contar `<repo>/<project.migrations.dir>/*` mais novos que `state.migrations.last_applied` (se `project.migrations != null`).

### Output

```
═══ Status — <project.name> ═══

Services:
  ✅ <id>     <status>    <sha> (<idade>)    <latency>ms
  ...

Git:
  Local HEAD: <sha>
  Prod <service>: <sha>   (atrás em <N> commits)
  ...

Migrations pendentes: <N> arquivo(s)
  - <arquivo>
  ... (ou "—" se project.migrations == null)

Último deploy registrado:
  <data> — <sha> — <subject> — <result>

project.json: <REPO_ROOT>/docs/spec/deploy/project.json
```

Algo down → ❌ destacado.

---

## Modo `rollback`

Invocação: `/deploy rollback [--dry-run]`.

1. Bootstrap.
2. Ler `history.json`. Identificar 2º deploy mais recente com `result == "healthy"` (o mais recente pode estar danificado). Se só houver 1 → reportar e parar.
3. Mostrar candidato:
   ```
   Rollback candidato:
     De: <sha-atual> (<data> — <subject>)
     Para: <sha-alvo> (<data> — <subject>)
   Reverter? [y/n]
   ```
4. `n` → abortar.
5. `y`:
   - Pra cada service afetado naquele deploy: `mcp__coolify__deployment list_for_app` → achar deployment_uuid do SHA-alvo.
   - `mcp__coolify__deploy` com aquele UUID.
   - Monitorar (Passo 5 do ship).
   - Health check (Passo 7).
6. Reescrever `state.json` (9.1) com `last_run.mode = "rollback"`. Prepend em `history.json` (9.2) com `rollback_target_sha = <sha-alvo>` e `result = "rollback-manual"`. Criar chronicle `<timestamp>-<sha>-rollback-manual.md` (9.3) + prepend em CHANGELOG (9.4).

Dry-run: mostrar alvo e deployments, sem executar.

---

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
     - `build.{base_directory, ports_exposes, dockerfile_location, build_pack}` ← do `coolify.md` legado + `mcp__coolify__get_application`.
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

6. Criar `docs/spec/chronicles/` (vazia) se não existir.

7. Reportar:
   ```
   Migração v1→v2 concluída.
   project.json: <path>
   Próximo /deploy ship vai gerar a primeira chronicle automaticamente.
   Rode /deploy status pra confirmar leitura do project.json.
   ```

### Modo v0→v2 (DEPLOY.md monolítico existe)

1. Parsear `blueprint/DEPLOY.md` (marcadores `<!-- blueprint:section:xxx -->` ou heurística por header).
2. Construir `state.json` schema 1.0 + `project.json` schema 2.0 + `history.json` no mesmo passo.
3. `state.json`: como hoje (UUIDs/domínios/portas/health_path da seção `config-coolify`; status atual via MCP em paralelo).
4. `history.json`: parsear bloco `historico` em `deploys[]`.
5. `project.json`: gerar via mesmo procedimento do v1→v2, usando o state recém-construído como entrada.
6. Renomear `blueprint/DEPLOY.md` → `blueprint/DEPLOY.md.legacy` (a info foi absorvida pelo `project.json`).
7. Criar `docs/spec/chronicles/` (vazia).
8. Reportar resultado.

### Dry-run

Imprimir plano (que arquivos seriam criados, qual estado seria capturado, quais entradas no `project.json`) sem escrever nada.

---

## Referência — regex de DDL destrutivo

Usada no Passo 6.1 do ship. Case-insensitive. Conservadora — falso positivo > falso negativo.

```
\bDROP\s+(TABLE|COLUMN|CONSTRAINT|INDEX|SCHEMA|VIEW|FUNCTION|TRIGGER|POLICY|TYPE|DATABASE|ROLE)\b
\bTRUNCATE\s+(TABLE\s+)?\w+
\bDELETE\s+FROM\s+\w+(?![\s\S]*\bWHERE\b)
\bALTER\s+(TABLE|COLUMN)\s+.*\bDROP\b
\bALTER\s+(TABLE|COLUMN)\s+.*\bALTER\s+COLUMN\s+.*\bTYPE\b
\bGRANT\s+.*\bALL\b
\bREVOKE\b
```

`project.migrations.destructive_regex_extra[]` adiciona padrões custom. Qualquer match → DESTRUCTIVE → exigir confirmação.

---

## Anti-padrões críticos

- ❌ Hardcodar nome de projeto, domínio, path absoluto, UUID, porta, secret name nesta skill. Se você está editando este arquivo e quer escrever um valor desses, ele pertence ao `project.json`.
- ❌ `git add -A` ou `git add .` sem lista explícita.
- ❌ Aplicar migration destrutiva sem confirmação explícita.
- ❌ Persistir valor de secret em arquivo, log, JSON, HTML ou histórico.
- ❌ Rollback em loop.
- ❌ Editar `docs/spec/deploy/{state,history}.json` ou `docs/spec/chronicles/*.md` (gerados automaticamente) à mão — a skill é dona; edição manual cria drift. Se quer mudar info do projeto, edite `docs/spec/deploy/project.json` direto.
- ❌ Apagar `blueprint/DEPLOY.md.legacy` antes do primeiro ship com sucesso na estrutura nova.

---

## Relação com outras skills

- Hooks PostToolUse não disparam esta skill — invocação sempre manual.
