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
2. UUID do projeto Coolify — se há outros `project.json` no `~/PedroDev/*/docs/spec/deploy/project.json`, oferecer reaproveitar; senão, listar `coolify project list` e perguntar
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
1. **App** via `coolify app create github`:
   ```
   project_uuid, server_uuid, github_app_uuid (do project.json em construção)
   git_repository, git_branch
   build_pack, base_directory, dockerfile_location (se aplicável), ports_exposes
   fqdn, name (default: `<slug>-<service.id>`)
   ```
2. **Health check Coolify** via `coolify app update <uuid>`:
   - `health_check_enabled`, `health_check_path`, `health_check_port`, `interval`, `retries` — todos vindos de `service.deploy.coolify_health`.

3. **Service Supabase** (só se houver service `type: supabase`):
   - `coolify service create supabase --server-uuid <s> --project-uuid <p> --environment-name production --name <nome>` (sem `--instant-deploy`).
   - Configurar env vars Supabase via `coolify service env create <service_uuid> --key <KEY> --value "<valor>"` (POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY, SERVICE_ROLE_KEY — gerar via `openssl rand -hex 32` pras que precisam).
   - `coolify service start <service_uuid>`. Aguardar `running`.

Anotar UUIDs retornados em `project.json` em construção.

### Fase 6 — Env vars

Para cada service:
- Ler `.env.example`/`.env.local.example` no `service.lint.cwd`.
- Identificar chaves marcadas `<PREENCHER>` ou vazias.
- Pedir valor 1× cada via prompt seguro (NUNCA logar).
- Aplicar **uma chave por vez**, direto do valor em memória: `coolify app env create <service.uuid> --key <KEY> --value "<valor>"`.
  > Não usar `coolify app env sync` aqui: ele exige um arquivo `.env` em disco (`-f` obrigatório), e escrever secret em arquivo quebra a invariante 5. O `sync` serve quando o arquivo `.env` já existe por outro motivo.
- Build-time: para as chaves listadas em `service.env_keys.build_time`, acrescentar `--build-time` na chamada daquela chave (o `sync` marcaria o arquivo inteiro de uma vez).

### Fase 7 — Secrets auto-gerados

Para cada `secret` em `project.secrets_auto_generated[]` (se a stack tem):
- Executar `secret.generator` localmente.
- `coolify app env create <uuid> --key <KEY> --value "<valor>"` no service correspondente (`secret.service`).
- NUNCA logar valor.

### Fase 8 — DNS

Calcular registros A necessários a partir dos `service.deploy.fqdn`. Mostrar tabela:

| Tipo | Nome | Conteúdo | Proxy |
|---|---|---|---|
| A | `<sub>` | `<vps_ip>` | DNS only |

Validar resolução: `dig +short <fqdn>` deve retornar `<vps_ip>`.

Se já resolve: silencioso. Senão: pedir pro usuário criar e confirmar (`y` pra continuar).

### Fase 9 — Primeiro deploy

Pedir ao humano `! coolify deploy uuid <service.uuid>` em cada service (comando de build, negado na sessão). Monitorar (loop Passo 5 do ship).

### Fase 10 — Inicializar blueprint

Escrever:
- `docs/spec/deploy/project.json` — versão final com UUIDs preenchidos.
- `docs/spec/deploy/state.json` — primeiro snapshot via `coolify app get <uuid> --format json` e `coolify service get <uuid> --format json` (preencher status, SHA, latência).
- `docs/spec/deploy/history.json` — `{"schema_version":"1.0","deploys":[]}`.

Reportar:
```
Setup completo. Use `/deploy` para deploys futuros.
project.json: <REPO_ROOT>/docs/spec/deploy/project.json
```

### Dry-run

Executar leituras/validações, pular `create`/`deploy`/`update`. Reportar o que FARIA.

---
