---
name: deploy
description: Deploy via Coolify a partir de docs/spec/deploy/project.json. Modos: ship (default), status, rollback, setup, migrate-blueprint. Use para subir para prod, ver o estado de produção ou reverter.
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
- `<repo>/docs/spec/CHANGELOG.md` — **cronologia flat** (append-only). Prepended pelo ship a cada deploy. Tem 100% do histórico em uma página, offline.

Schema completo do `project.json` em `.claude/skills/deploy/references/project-schema.md`.

---

## Princípio arquitetural

**Esta skill é metodologia pura. Zero conhecimento sobre projetos específicos.** Tudo que varia entre projetos (paths, portas, domínios, comandos de build/lint, env vars, secrets, gates) vem de `project.json` no repo. Se você está editando esta skill e sente vontade de escrever `Hospital`, `mala-ia.cloud`, `8000`, `/api/health`, ou um caminho `/Users/...` — pare. Esse valor pertence ao `project.json`.

A skill executa sempre o mesmo algoritmo (pre-flight → commit → push → monitor → migrations → health → rollback se falhar → reescrever JSONs → atualizar CHANGELOG + snapshot). Cada passo é completamente parametrizado pelo `project.json` do repo atual.

---

## Princípios operacionais

1. **Silencioso quando passa, vocal quando falha.** Pre-flight só reporta itens que quebraram. `--verbose` expõe tudo.
2. **Mínimo de perguntas.** A única pergunta no caminho feliz do `ship` é confirmação da mensagem de commit. `setup` pergunta o necessário pra construir o `project.json`. Status/rollback não perguntam (rollback só pede confirmação do alvo).
3. **Migrations destrutivas sempre pedem confirmação explícita.** DROP, TRUNCATE, DELETE-sem-WHERE, ALTER-DROP: mostra SQL e espera "y".
4. **Idempotência:** rodar 2× sem mudança = mesmo resultado. JSONs são reescritos inteiros (sem merge parcial); HTML é regerado a partir do template.
5. **Secrets nunca vazam.** Valores de env vars nunca vão para log, commit, JSON, HTML ou histórico. Só existem em memória durante execução e no Coolify. JSONs guardam apenas `name` + `present: true|false`. Antes de escrever `state.json`, a skill roda gate de regex anti-vazamento: se um valor escalar bate `(?:[a-zA-Z0-9+/]{40,}|sk-[a-zA-Z0-9]{20,})`, o write é abortado.
6. **Token do Coolify vem do repo.** A fonte canônica é `<repo>/tokens/.env` (pasta git-ignored) com `COOLIFY_ACCESS_TOKEN` e `COOLIFY_BASE_URL`; o CLI `coolify` guarda o mesmo par no contexto ativo (`~/.config/coolify/config.json`). Se um comando do CLI retornar **401**, não re-tentar igual: ler o token atualizado de `<repo>/tokens/.env`, rodar `coolify context set-token <contexto> "$COOLIFY_ACCESS_TOKEN"` e repetir o passo. Último recurso: a API HTTP direta (`curl -H "Authorization: Bearer $COOLIFY_ACCESS_TOKEN" "$COOLIFY_BASE_URL/api/v1/..."`). Rotação de token = editar `<repo>/tokens/.env` + `coolify context set-token` (o valor fica entre aspas: token Sanctum tem `|`). Nunca logar o valor.

---

## Acesso ao Coolify (CLI `coolify`)

Todo acesso ao Coolify passa pelo **CLI oficial** `coolify` (binário no PATH, credencial no contexto ativo, config em `~/.config/coolify/config.json`). Esse é o **único** caminho: desde 18/08/2026 a sessão do Claude não tem nenhuma outra integração com o Coolify. O nome do contexto é do ambiente, não da skill (no Hospital: `hsm`); `coolify context list` mostra qual está ativo.

### Comandos usados nesta skill

| O que preciso | Comando |
|---|---|
| Conferir credencial | `coolify context verify` |
| Listar apps | `coolify app list` |
| Estado de um app (status, SHA, health) | `coolify app get <uuid> --format json` |
| Estado de um service composto (Supabase) | `coolify service get <uuid> --format json` |
| Listar env vars (só keys) | `coolify app env list <uuid> --format json` (service composto: `coolify service env list <uuid>`) |
| Listar env vars com os valores reais | `coolify app env list <uuid> -s --format json` (ver pegadinha 5) |
| Criar env var | `coolify app env create <uuid> --key <KEY> --value "<valor>"` |
| Atualizar env var | `coolify app env update <uuid> <KEY> --value "<valor>"` |
| Aplicar um arquivo `.env` inteiro | `coolify app env sync <uuid> -f <arquivo.env>` |
| Listar deploys de um app | `coolify app deployments list <uuid> --format json` |
| Detalhe de um deploy | `coolify deploy get <deployment_uuid> --format json` |
| Logs do container | `coolify app logs <uuid> -n 150` |
| Logs do build | `coolify app deployments logs <uuid>` |
| Disparar deploy manual | `coolify deploy uuid <uuid>` (ver pegadinha 2) |
| Imagens disponíveis para rollback | `coolify app rollback images <uuid>` |
| Rollback para um commit | `coolify app rollback run <uuid> --commit <SHA>` (ver pegadinha 7) |
| Listar projetos e servidores | `coolify project list`, `coolify server list` |

### Pegadinhas (ler antes de rodar)

1. **`env update` é posicional e minimalista.** A forma certa é exatamente esta, sem mais nada:
   ```bash
   coolify app env update <uuid> <KEY> --value "<valor>"
   ```
   Duas maneiras de quebrar esse comando, ambas vistas em uso real:
   - `--key` **não** aponta a variável: é o **rename** (o nome novo da chave). Misturar com a chave posicional quebra a validação de argumentos (24/08/2026).
   - Acrescentar `--runtime` ou `--build-time=false` faz a API responder `422 Validation failed`, mesmo com o resto certo (28/08/2026). O update **preserva** os flags que a variável já tem, então não os repita: mande só `--value`.

   O `--value` é **obrigatório**. Não existe update que só vire um flag sem reenviar o valor.
2. **Deploy manual: tente antes de delegar.** O classifier de permissões já negou `coolify deploy uuid ...` em sessões passadas, mas a negação **não é constante** (em 01/09/2026 merge de PR por API e push na main passaram sem bloqueio). Então, com o OK humano do ship em mãos, **rode o comando**. Se a chamada for negada, aí sim peça ao humano rodar na própria sessão com o prefixo `!`: `! coolify deploy uuid <uuid>`, dizendo que foi negado. Nunca delegue por suposição. Leitura (`get`, `list`, `logs`) e `env update` sempre passaram.
3. **Não existe `coolify app deploy` nem `coolify deployment`.** O topo é `coolify deploy` (`uuid`, `name`, `batch`, `get`, `list`, `cancel`); por app, `coolify app deployments list|logs`.
4. **`--format json` imprime um banner antes do JSON.** A linha `A new version (x.y.z) is available` quebra o `jq`. Filtre sempre: `coolify app get <uuid> --format json | sed -n '/^[[{]/,$p' | jq ...`.
5. **`env list` esconde os valores.** Sem `-s`, todo `value` volta como `********`. Para **conferir keys** isso basta; para **comparar valores** é preciso `coolify app env list <uuid> -s --format json`. O valor real fica só em memória: nunca logar, commitar ou gravar em arquivo (invariante 5).
6. **O JSON de app traz segredo.** `coolify app list` e `coolify app get` devolvem os campos `manual_webhook_secret_*`, e `env list -s` devolve todos os secrets do service. Nunca colar a saída crua em log, commit, PR, issue ou nos JSONs de `docs/spec/deploy/`.
7. **Rollback precisa da imagem, não do commit.** `coolify app rollback run --commit <SHA>` só funciona enquanto a imagem daquele build existir. Confira antes com `coolify app rollback images <uuid>`: o histórico de deploy pode ter o SHA e a imagem já ter sido podada.

### Auto-deploy por webhook é o caminho normal

Desde 27/08/2026 os webhooks do GitHub estão religados (um por app, com secret próprio): **push na branch de produção rebuilda os services sozinho**. O papel desta skill no deploy é **monitorar** o build que o push disparou, não disparar build.

Deploy manual (`coolify deploy uuid`, rodado pelo humano com `!`) é **exceção**. Só nestes casos: o webhook não disparou (nenhum deploy novo em `coolify app deployments list` depois do push), o build precisa ser refeito sem commit novo (env var trocada), ou é rollback.

---

### Semáforo de deploy (sessões paralelas)

Várias sessões `/onda` ou `/ship` rodam na mesma máquina e todas terminam na `main`. Como todo push na `main` dispara build pelo webhook, dois merges juntos viram builds concorrentes (o frontend estoura a memória da VPS), e o `/health` mostra a versão de outra sessão, o que dispara rollback errado. O semáforo serializa isso sem o humano de porteiro: quem segura a trava mergeia e deploya; as outras esperam na fila.

```bash
S=.claude/skills/deploy/scripts/semaforo.sh
$S pegar  <chave> "<o que vai subir>"   # espera até pegar; reentrante para a mesma chave
$S soltar <chave>                        # só o dono solta
$S status                                # quem segura e há quanto tempo
```

- **Chave** = identificador da sessão. Use o basename do diretório de scratchpad da sessão (é único por sessão e a sessão o conhece).
- A trava é `/tmp/deploy-semaforo-<project.slug>.lock` (pasta criada com `mkdir`, atômico). Vale só para sessões na mesma máquina, que é o caso do trabalho paralelo deste repo.
- `pegar` devolve `3` se passou o tempo de espera (default 540 s, cabe no timeout do Bash): chame de novo, sem alarde. Devolve `2` se a trava tem mais de 60 min: confira `coolify app deployments list` e, sem build rodando, `soltar <chave-do-dono> --forcar`. Nunca force com build em andamento.
- **Regra:** pegar **antes do primeiro push na `main`** (merge ou commit direto), soltar **depois** do health verde e do push do bookkeeping, ou depois do rollback. Sempre soltar, mesmo em falha.

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

### Passo 0: Pegar o semáforo

Antes de qualquer push na `main`. Chave = basename do scratchpad da sessão; descrição = o que vai subir (PRs ou commit).

```bash
.claude/skills/deploy/scripts/semaforo.sh pegar <chave> "ship: <descrição>"
```

Saída `3`: chame de novo (outra sessão está deployando). Saída `2`: trava velha, siga a regra da seção "Semáforo de deploy". Quando o `/ship` ou a `/onda` já pegaram a trava com a mesma chave, o comando devolve "já é sua" e segue.

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
- `coolify app env list <service.uuid> --format json` (ou `coolify service env list <service.uuid> --format json` se `service.type == "supabase"`).
- Comparar keys retornadas com `service.env_keys.runtime_required`. Se faltar alguma → ❌ listar faltantes e PARAR.

#### 2.6 Vars prod-only com valores exatos

Para cada `service.prod_only_assertions[]` (lista de `{key, value, comparison}`):
- Ler os valores reais: `coolify app env list <service.uuid> -s --format json`. **Sem `-s` todo valor volta `********`** e a comparação reprovaria sempre (ver pegadinha 5). O valor lido fica só em memória: não logar, não gravar.
- Comparar valor atual no Coolify com `value` esperado conforme `comparison` (`eq` | `regex`).
- Qualquer divergência → ❌ mostrar o que está errado e como corrigir (via `coolify app env update <service.uuid> <KEY> --value "<valor>"`, forma posicional) e PARAR. Oferecer corrigir via CLI com confirmação.

#### 2.7 Vars build-time marcadas

Para cada `service` com `service.env_keys.build_time_must_be_marked == true`:
- Para cada key em `service.env_keys.build_time`, validar `is_build_time == true` no Coolify.
- Se alguma não tiver → ❌ reportar e PARAR. Marcar build-time pelo CLI é frágil: `--value` é obrigatório (reenviar o valor atual, lido com `-s`, senão a var é sobrescrita) e `--build-time` junto já devolveu `422 Validation failed`. Caminho confiável: marcar o checkbox **Build Variable** na tela do Coolify e confirmar com `coolify app env list <service.uuid> --format json`. Nunca reenviar um placeholder: o CLI grava o que receber.

#### 2.8 Secrets auto-gerados presentes

Para cada secret em `project.secrets_auto_generated[]`:
1. Verificar se a key existe no service correspondente (output de 2.5) e o valor não é vazio.
2. Se faltar/vazio:
   - Perguntar: "Secret `X` ausente em `<service>`. Gero e seto agora? (y/n)"
   - Se `y`: executar o `secret.generator` (comando local), capturar saída, `coolify app env create <service.uuid> --key <KEY> --value "<valor>"` (use `coolify service env create` se `service.type == "supabase"`). NUNCA logar ou salvar o valor.
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
# update é update-only: se a key ainda não existe, o CLI falha e o create resolve.
coolify app env update "$BACKEND_UUID" APP_VERSION --value "$APP_VERSION" 2>/dev/null \
  || coolify app env create "$BACKEND_UUID" --key APP_VERSION --value "$APP_VERSION"
```

**Idempotente** — se a env já está com o valor certo (comparar com `state.json:last_app_version`), pular silenciosamente sem chamar o CLI.

> Forma **posicional**: a chave vem depois do UUID, sem `--key` (ver pegadinha 1).

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
1. `coolify app deployments list <service.uuid> --format json` → encontrar o deploy mais recente (disparado pelo webhook do push).
2. Loop: `coolify deploy get <deployment_uuid> --format json` a cada ~10s.
3. Reportar progresso compacto: `<service.id>: queued → building → deploying → finished (1m12s)`.
4. Parar loop quando status for `finished` ou `failed`.

Se `failed` → capturar logs (`coolify app logs <service.uuid> -n 150` e `coolify app deployments logs <service.uuid>`), mostrar, seguir Passo 8 (rollback).

Se, passados ~2min do push, `coolify app deployments list` não mostrar deploy novo, o webhook não disparou: **disparar** `coolify deploy uuid <service.uuid>` e seguir monitorando. Só se a chamada for negada, pedir ao humano `! coolify deploy uuid <service.uuid>` (ver pegadinha 2).

**Capturar `build_duration_seconds`** por service (delta `started_at` → `finished_at`). Persistir em memória pra Passo 9.

### Passo 6 — Migrations novas (gate manual — aplicar no Supabase de produção)

Pular se `--no-migrations`, se `project.migrations == null`, ou se não houver migration nova.

> **Por que manual:** o Postgres do Supabase self-hosted **não é exposto** externamente (sem porta pública — `ports_mappings`/`public_port` nulos no `supabase-db`) e o CLI/API do Coolify **não executa SQL nem `docker exec`**. As migrations são aplicadas pelo humano no **SQL Editor do Supabase Studio de produção**. Esta skill **não aplica migration sozinha** — ela detecta, monta o(s) script(s) e **PARA**, entregando o passo a passo. Nunca tente `docker exec`/`psql` direto: não há esse acesso por aqui.

#### 6.1 Detectar migrations novas

Listar os arquivos em `<repo>/<project.migrations.dir>` que ainda **não foram aplicados**: comparar com o último deploy via `git diff <state.json.last_run.sha>..HEAD -- <dir>` (ou, na dúvida, as migrations adicionadas desde o último deploy registrado). Ordenar cronologicamente. Se vazio → pular o passo.

#### 6.2 Classificar (sinaliza risco, não muda o fluxo)

Para cada migration nova, classificar **SAFE** | **DESTRUCTIVE** via a regex de DDL destrutivo (`references/regex-ddl-destrutivo.md` + `project.migrations.destructive_regex_extra`). Serve para destacar risco no passo a passo; a aplicação é manual em qualquer caso.

#### 6.3 PARAR e entregar o(s) script(s) + passo a passo

Apresentar ao humano e **não prosseguir** até ele confirmar que aplicou:

- O conteúdo **completo** de cada migration nova, num bloco ` ```sql ` copiável (um bloco por arquivo, em ordem cronológica). Migrations **DESTRUCTIVE** marcadas com ⚠ e os statements destrutivos apontados por linha.
- O passo a passo:
  1. Abrir o **Supabase Studio de produção** (`project.integrations[].supabase_studio_url`, senão a URL `studio.<domínio>` — ex.: `https://studio.hospitalsaomatheus.cloud`).
  2. **SQL Editor → New query**.
  3. Colar o script. Havendo mais de um, aplicar **na ordem**, um de cada vez.
  4. **Run** (Cmd/Ctrl+Enter).
  5. Confirmar sucesso: a tabela/coluna aparece no **Table Editor**, ou rodar uma checagem (`select 1 from <tabela> limit 1;`) sem erro.
- Pedir confirmação explícita ("apliquei / deu certo") antes de seguir.

> No fluxo `/ship` este gate é **antecipado para antes do merge** (ver `/ship` Passo 8.6), pois o merge dispara o auto-build no Coolify — o schema precisa existir **antes** do código novo subir. No `/deploy` standalone, se a migration é pré-requisito do código já em produção, há uma janela curta entre o deploy e a confirmação: aplique o quanto antes.

#### 6.4 Verificação pós-migration

Após a confirmação do humano, para cada service que depende do banco (heurística: `service.type` em `{fastapi, python, node}` + chave `*_DATABASE_URL`/`SUPABASE_*` em runtime_required):
- `coolify app get <service.uuid> --format json` → o campo `status` deve continuar `running:healthy`.
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

Combinar com `coolify app get <service.uuid> --format json` (campo `status`).

Capturar `latency_ms` (em ms) e `http_status` por service. Persistir em memória.

#### 7.1 Health rico (gate `health_rich`, fail)

Só roda se `project.gates.health_rich.enabled == true`.

Após o curl do health endpoint passar status+regex, parsear o body como JSON e validar:
```bash
for key in $(jq -r '.gates.health_rich.required_keys[]' <<< "$PROJECT_JSON"); do
  jq -e --arg k "$key" 'has($k)' <<< "$HEALTH_BODY" >/dev/null || MISSING="$MISSING $key"
done
```

Se faltar qualquer key → ❌ listar keys ausentes (ex: "health body sem campo `db`") e disparar Passo 8 (rollback). Mensagem: "Health endpoint retornou body incompleto, app pode estar respondendo sem checar dependências críticas."

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

### Passo 8 — Rollback (se health falhou)

> **A sessão detecta e prepara; o disparo é humano.** O comando de rollback dispara build e é negado pelo classifier, então esta skill não reverte sozinha: ela para, entrega o comando pronto e espera. Em modo AFK (`/onda`), isso significa produção parada no build ruim até alguém rodar o comando: reportar isso em alto e bom som, não seguir em silêncio.

Executar 1×:
1. Ler `<repo>/docs/spec/deploy/history.json` → último deploy com `result == "healthy"` por service afetado.
2. Pra cada service: `coolify app rollback images <service.uuid>` → confirmar que a **imagem** do SHA-alvo ainda existe (o `coolify app deployments list` mostra o histórico, mas imagem podada não volta).
3. Entregar ao humano, e esperar ele rodar: `! coolify app rollback run <service.uuid> --commit <SHA-alvo>`.
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

#### 9.3 — (removido) Chronicles aposentados

> O sistema de chronicles (🟡/🟢/🔴) foi descontinuado na migração para o modelo Pocock.
> O registro factual de cada deploy vive em `history.json` (9.2) + `CHANGELOG.md` (9.5); a
> narrativa do trabalho vive na própria **GitHub Issue** + no PR. Não criar nem renomear
> arquivos em `docs/spec/chronicles/`.

#### 9.3.5 — (removido) Sem planejamento versionado

> O fluxo Pocock não usa `docs/planejamento/`. O fechamento do trabalho é o `Closes #N` no
> merge do PR (o GitHub fecha a issue e remove `in-progress`/assignee). Não procurar, mover
> nem deletar planos. Cronologia da falha (se houver) vive em `history.json`.

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

Ver `scripts/changelog_prepend.py` na própria skill — gera entrada com autor (git config), SHA, serviços tocados, resultado e link para a issue/PR.

Reportar ao usuário:

```
CHANGELOG: <REPO_ROOT>/docs/spec/CHANGELOG.md (entrada nova no topo)
```

---

### Passo 10: Soltar o semáforo

Roda **sempre**: depois do health verde e do push do bookkeeping (Passo 9), depois do rollback (Passo 8), ou depois de qualquer parada por erro. Sem isso as outras sessões ficam na fila até a trava envelhecer.

```bash
.claude/skills/deploy/scripts/semaforo.sh soltar <chave>
```

## Modo `setup`

Invocação: `/deploy setup [--dry-run]`. Cria o blueprint do zero, só quando NÃO existe `project.json`. Roda uma vez por projeto. Passo a passo (10 fases) em `references/modo-setup.md`: leia só nesse caso.

---

## Modo `status`

Invocação: `/deploy status`. Zero alterações.

1. Bootstrap (lê `project.json`).
2. Em paralelo (múltiplas tool calls na mesma mensagem):
   - Pra cada `service`: `coolify app get <uuid> --format json` (ou `coolify service get <uuid> --format json` se type=supabase).
3. SHA local: `git rev-parse --short HEAD`.
4. SHA em prod: por service via `coolify app deployments list <uuid> --format json` (último) ou pelo campo `git_commit_sha` do `coolify app get`.
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

Invocação: `/deploy rollback [--dry-run]`. Reverte para o último deploy `healthy` anterior. O `rollback run` é sempre do humano (`! coolify app rollback run ...`). Passo a passo em `references/modo-rollback.md`.

---

## Modo `migrate-blueprint`

Invocação: `/deploy migrate-blueprint [--dry-run]`. Uma vez por projeto: migra `blueprint/DEPLOY.md` (v0) ou `state.json` schema 1.0 sem `project.json` (v1) para o schema 2.0. Detecção e os dois caminhos em `references/modo-migrate-blueprint.md`.

---

## Referência: regex de DDL destrutivo

Usada no gate de migrations do ship (SAFE | DESTRUCTIVE). Padrões em `references/regex-ddl-destrutivo.md`; `project.migrations.destructive_regex_extra[]` acrescenta os do projeto. Qualquer match exige confirmação.

---

## Anti-padrões críticos

- ❌ Hardcodar nome de projeto, domínio, path absoluto, UUID, porta, secret name nesta skill. Se você está editando este arquivo e quer escrever um valor desses, ele pertence ao `project.json`.
- ❌ `git add -A` ou `git add .` sem lista explícita.
- ❌ Aplicar migration destrutiva sem confirmação explícita.
- ❌ Persistir valor de secret em arquivo, log, JSON, HTML ou histórico.
- ❌ Rollback em loop.
- ❌ Editar `docs/spec/deploy/{state,history}.json` (gerados automaticamente) à mão — a skill é dona; edição manual cria drift. Se quer mudar info do projeto, edite `docs/spec/deploy/project.json` direto.
- ❌ Apagar `blueprint/DEPLOY.md.legacy` antes do primeiro ship com sucesso na estrutura nova.

---

## Relação com outras skills

- Hooks PostToolUse não disparam esta skill — invocação sempre manual.
