# `project.json` — schema 2.0 (referência completa)

Este documento define o "v0" de cada projeto consumido pela skill `/deploy`. Vive em `<repo>/blueprint/deploy/project.json`. A skill é metodologia pura; tudo que varia entre projetos vem deste arquivo.

## Filosofia

- **Auto-suficiente.** A skill carrega este arquivo no bootstrap e nunca precisa de conhecimento adicional sobre o projeto.
- **Editável.** Pode ser editado à mão (trocar domínio, adicionar service, ajustar gates). O `state.json` e o `dashboard.html` são reescritos no próximo ship com base no novo `project.json`.
- **Versionado.** Vai pro git junto com o código. Reviews de PR olham diff de spec assim como diff de código.
- **Stack-aware via opcionais.** Campos null/vazios desligam features (sem migrations? `migrations: null`. Sem secrets gerados? `secrets_auto_generated: []`). Skill pula gates desativados.

## Schema completo

```jsonc
{
  // ─── Versão e identidade ──────────────────────────────────────────
  "schema_version": "2.0",                  // Obrigatório. Skill recusa se != "2.0".

  "project": {
    "name": "Meu Projeto",                  // Obrigatório. Humano, vai pro dashboard.
    "slug": "meu-projeto",                  // Obrigatório. ASCII, sem espaços. Usado em logs/nomes Coolify.
    "description": "Descrição em 1 linha"   // Opcional.
  },

  // ─── Git ──────────────────────────────────────────────────────────
  "git": {
    "repo": "owner/repo-name",              // Obrigatório. Formato GitHub.
    "branch": "main",                       // Obrigatório.
    "root_relative": "."                    // Opcional, default ".". Path relativo ao repo onde fica
                                            // o código primário (suporta monorepo).
  },

  // ─── Coolify ──────────────────────────────────────────────────────
  "coolify": {
    "url": "https://coolify.exemplo.com",   // Obrigatório.
    "project_uuid": "<uuid>",               // Obrigatório.
    "server_uuid": "<uuid>",                // Obrigatório.
    "github_app_uuid": "<uuid>",            // Obrigatório.
    "vps_ip": "0.0.0.0",                    // Obrigatório. IPv4 ou IPv6.
    "domain_root": "exemplo.com"            // Opcional. Hint pra DNS e setup.
  },

  // ─── Services (1+) ────────────────────────────────────────────────
  "services": [                             // Obrigatório, pelo menos 1.
    {
      "id": "frontend",                     // Obrigatório. Único dentro do array. Usado em logs/scope.
      "type": "nextjs",                     // Obrigatório. "nextjs" | "fastapi" | "supabase" |
                                            //              "node" | "python" | "static" | "generic"
      "uuid": "<app uuid Coolify>",         // Obrigatório (preenchido pelo setup).

      // ─── Build ──
      "build": {
        "build_pack": "dockerfile",         // "dockerfile" | "nixpacks" | "static"
        "base_directory": "/",              // Build context relativo ao repo.
        "dockerfile_location": "/site-next/Dockerfile", // null se nixpacks/static.
        "ports_exposes": "3000",
        "build_args_from_env_keys": [       // Lista de chaves de env_keys.build_time
          "NEXT_PUBLIC_FOO"                 // que viram ARG no Dockerfile.
        ]
      },

      // ─── Deploy ──
      "deploy": {
        "fqdn": "https://meu-app.exemplo.com",
        "health_check": {
          "path": "/",                      // Path HTTP pro check ativo.
          "url": "https://meu-app.exemplo.com",  // URL completa (path concatenado se diferente).
          "expected_status": 200,
          "expected_body_regex": null,      // Opcional. Ex: "^\\{\"status\":\"ok\"\\}$"
          "max_latency_ms": 3000            // Health check falha se latency > isso.
        },
        "coolify_health": {                 // Health check do Coolify (Traefik usa isso).
          "enabled": true,
          "path": "/",
          "port": 3000,
          "interval_seconds": 30,
          "retries": 3
        }
      },

      // ─── Lint ──
      "lint": {                             // null pra desabilitar lint deste service.
        "cmd": "pnpm lint && pnpm exec tsc --noEmit",
        "cwd": "site-next",                 // Relativo ao repo. Onde rodar `cd <cwd> && <cmd>`.
        "trigger_paths": ["site-next/**"],  // Glob: lint só roda se diff toca aqui.
        "format_check_cmd": null,           // Ex: "uv run ruff format --check ."
        "format_fix_cmd": null,             // Ex: "uv run ruff format ."
        "skippable_with_flag": true         // Se true, --skip-lint pula este service.
      },

      // ─── Env keys ──
      // Cada item é `string` (só nome) OU `{name, purpose}` (nome + descrição funcional).
      // Strings continuam aceitas pra retrocompat; o dashboard renderiza só o nome quando
      // não há `purpose`. Objetos são preferidos: o `purpose` aparece no dashboard como
      // legenda da chave (≤80 chars sugerido). Skill tolera ambos os formatos no mesmo array.
      "env_keys": {
        "build_time": [                     // Vars necessárias no momento do build.
          { "name": "NEXT_PUBLIC_FOO", "purpose": "URL base do backend exposta ao bundle" }
        ],
        "runtime_required": [               // Vars obrigatórias em runtime. Pre-flight valida presença.
          { "name": "DATABASE_URL", "purpose": "Conexão Postgres principal" },
          "LEGACY_KEY"                      // ← string crua continua válida (purpose = null)
        ],
        "runtime_optional": [               // Vars opcionais. Pre-flight não bloqueia se faltar.
          { "name": "ANALYTICS_KEY", "purpose": "PostHog (opcional)" }
        ],
        "build_time_must_be_marked": true   // Se true, valida is_build_time=true no Coolify
                                            // pra cada chave de build_time.
      },

      // ─── Asserções de produção ──
      "prod_only_assertions": [             // Lista vazia [] desliga este gate pro service.
        {
          "key": "ENVIRONMENT",
          "value": "production",
          "comparison": "eq"                // "eq" | "regex"
        }
      ],

      // ─── Roteamento de diff ──
      "diff_routing": {
        "trigger_paths": [                  // Globs que indicam que este service foi afetado.
          "site-next/**",                   // Skill deploya/monitora apenas services tocados.
          "Dockerfile"
        ]
      }
    }
  ],

  // ─── Secrets auto-gerados ─────────────────────────────────────────
  "secrets_auto_generated": [               // Lista vazia [] desliga este gate.
    {
      "name": "MY_API_SECRET",
      "service": "backend",                 // Deve casar com algum services[].id.
      "generator": "openssl rand -hex 32"   // Comando local. Saída vai pra Coolify, nunca persistida.
    }
  ],

  // ─── Migrations ───────────────────────────────────────────────────
  "migrations": null,                       // null se projeto não tem migrations.
  // Se tem:
  // {
  //   "dir": "supabase/migrations",          // Dir relativo ao repo.
  //   "container_pattern": "supabase-db-*", // Glob pra match no `docker ps`.
  //   "db": "postgres",
  //   "user": "postgres",
  //   "destructive_regex_extra": []         // Lista de regex extras pra classificar como DESTRUCTIVE.
  // }

  // ─── Gates de pre-flight ──────────────────────────────────────────
  "gates": {
    "secrets_in_git": true,                 // Sempre true; lista vem de hard_excluded.

    "env_example_sync": null,               // null = desligado. Se objeto:
    // {
    //   "config_file": "backend/app/config.py",
    //   "example_file": "backend/.env.example",
    //   "config_class": "Settings"            // Pra parser Pydantic.
    // }

    "migrations_backup_dir": null,          // null = desligado. String = path relativo ao repo.

    "lint": true,                           // Se true, pre-flight lint rola; se false, sempre pula.

    "build_args_consistency": true,         // Valida que services[].build.build_args_from_env_keys
                                            // são subconjunto de services[].env_keys.build_time.

    "dns_resolves": true                    // Setup checa que fqdn resolve pra vps_ip antes de criar app.
  },

  // ─── Hard-excluded (paths que nunca entram em commit) ─────────────
  "hard_excluded": [                        // Globs git.
    ".env", ".env.*", "!.env.example", "!.env.local.example",
    "*-env-producao.txt", "credentials*", "*.pem", "*.key",
    "deploy-history.md"
  ],

  // ─── Inferência de mensagem de commit ─────────────────────────────
  "commit_inference": {
    "scope_map": {                          // Glob → escopo conventional commits.
      "site-next/app/**": "site",
      "*.md": "docs",
      "Dockerfile": "infra"
    },
    "subject_max_chars": 60                 // Default 60.
  }
}
```

## Validação obrigatória (bootstrap)

A skill, ao ler `project.json`, valida:

1. `schema_version == "2.0"`.
2. `project.name` (string não vazia), `project.slug` (string ASCII).
3. `git.repo` no formato `owner/name`.
4. `git.branch` (string).
5. `coolify.{project_uuid, server_uuid, github_app_uuid}` (strings não vazias).
6. `services` array com >= 1 elemento. Cada elemento: `id`, `type`, `uuid`, `build`, `deploy`.

Falha em qualquer item → reportar campo ofensor e PARAR.

## Como cada modo consome este arquivo

| Modo | Leitura | Escrita |
|---|---|---|
| `ship` | Tudo. Roteia diff via `services[].diff_routing.trigger_paths`. Valida gates ativos. | Não toca `project.json`. Reescreve `state.json`/`history.json`/`dashboard.html`/`coolify.md`. |
| `setup` | N/A (cria do zero). | Escreve `project.json` final + outros artefatos. |
| `status` | Tudo (read-only). | Nada. |
| `rollback` | `services[].uuid` + `git.branch`. | Reescreve `state.json`/`history.json`/`dashboard.html`. |
| `migrate-blueprint` | Lê legado (`state.json` v1 ou `DEPLOY.md` monolítico). | Cria `project.json` schema 2.0. |

> **Nota sobre o dashboard.** O template universal recebe três placeholders: `__STATE_JSON__`, `__HISTORY_JSON__` e `__PROJECT_JSON__`. O último é a serialização do próprio `project.json` — é dele que o dashboard tira nome do projeto, domain root, lista de services e descrições (`purpose`) das env vars. Mantenha `project.name`, `coolify.domain_root` e `services[].env_keys[].purpose` preenchidos pra um dashboard com legendas claras.

## Padrões por tipo de service

Defaults sugeridos pelo `setup` quando detecta cada stack:

### `nextjs`
```jsonc
{
  "build": { "build_pack": "dockerfile", "ports_exposes": "3000",
             "build_args_from_env_keys": ["NEXT_PUBLIC_*"] },
  "deploy": { "health_check": { "path": "/", "expected_status": 200, "expected_body_regex": null } },
  "lint": { "cmd": "pnpm lint && pnpm exec tsc --noEmit" },
  "env_keys": { "build_time_must_be_marked": true }
}
```

### `fastapi`
```jsonc
{
  "build": { "build_pack": "dockerfile", "ports_exposes": "8000" },
  "deploy": { "health_check": { "path": "/api/health", "expected_status": 200,
                                "expected_body_regex": "^\\{\"status\":\"ok\"\\}$" } },
  "lint": { "cmd": "uv run ruff check .", "format_check_cmd": "uv run ruff format --check .",
            "format_fix_cmd": "uv run ruff format ." },
  "env_keys": { "build_time_must_be_marked": false }
}
```

### `supabase`
```jsonc
{
  "build": { "build_pack": "dockerfile", "ports_exposes": null },
  "deploy": { "health_check": null },         // Service composto, health vem do `coolify service get`.
  "lint": null,
  "env_keys": { "build_time_must_be_marked": false }
}
```

### `node` / `python` / `static` / `generic`
Defaults mínimos; setup pergunta cmd, fqdn, port.

## Exemplos completos por projeto

Veja:
- `~/PedroDev/Hospital/blueprint/deploy/project.json` — full-stack (Next.js + FastAPI + Supabase + migrations + secrets gerados).
- `~/PedroDev/SiteHospital/blueprint/deploy/project.json` — frontend-only (Next.js + Sanity, sem migrations, sem secrets gerados).

## Mudanças entre v1 (legado) e v2

- v1 tinha `state.json` schema 1.0 com `production.*` + `services[]` parcial. Toda config vivia espalhada em `coolify.md`/`env-vars.md`/`secrets.md`/`gates.md` editáveis à mão.
- v2 unifica todas as specs num único `project.json` editável. `coolify.md` vira documento gerado a partir do `project.json`. `env-vars.md`/`secrets.md`/`gates.md` legados deixam de existir (informação migrou pros campos `services[].env_keys`/`secrets_auto_generated`/`gates`).
- `state.json` continua schema 1.0 (não muda) — é só snapshot, não config.

Migração 1×: `/deploy migrate-blueprint`. Idempotente.
