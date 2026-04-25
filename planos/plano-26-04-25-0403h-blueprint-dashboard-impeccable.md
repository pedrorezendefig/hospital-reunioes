# Plano — Blueprint de deploy reorganizado + dashboard.html auto-atualizável + impeccable

## Plano

### Contexto

`blueprint/DEPLOY.md` virou um arquivo de 211 linhas que mistura nove naturezas diferentes (UUIDs, três grupos de env vars, secrets, excludes, status, histórico, gates, rollback, comandos MCP). Pedro relatou que está "muito confuso, várias variáveis" e propôs trocar por algo visual — "um `.html` com motion, ou algo impecável". O plano evolui o blueprint em três frentes:

1. **Reorganiza o blueprint**: separa o que é doc humana (markdown, raramente editado) do que é estado dinâmico (JSON, escrito pela skill).
2. **Cria um dashboard local auto-atualizável**: `blueprint/dashboard.html`, regenerado pela skill `/deploy` a cada ship, sem servidor, sem build, sem deps.
3. **Instala a skill `pbakaus/impeccable`** globalmente em `~/.claude/skills/` para usar durante a construção do dashboard, sem poluir o repo.

Resultado esperado: um arquivo `dashboard.html` que Pedro abre direto no browser e vê — em segundos — saúde da produção, último deploy, gates do pre-flight, env vars, migrations e timeline. O markdown deixa de ser misturado e cada arquivo passa a ter uma única responsabilidade.

### Decisões já travadas

| Tópico | Decisão |
|---|---|
| Onde o dashboard mora | `blueprint/dashboard.html` local (file://) |
| Source-of-truth | JSON estruturado (`state.json` + `history.json`) |
| Como o HTML lê dados | **Auto-contido**: skill regenera HTML inteiro a cada deploy, dados embutidos via `<script>const STATE = {...}</script>` |
| Motion stack | **CSS puro + View Transitions API + Web Animations API** (zero deps, zero CDN, zero build) |
| `pbakaus/impeccable` | Instalar **global** em `~/.claude/skills/` (não polui repo, sem conflito com `.gitignore`) |
| Blocos do MVP | Hero + cards de serviços + gates + timeline de deploys + matrix de env vars + migrations/próximas ações + accordion MCP |

### Arquitetura proposta

#### Nova estrutura do `blueprint/`

```
blueprint/
├── README.md                  # visão geral do projeto (mantida como está)
├── DEPLOY.md                  # vira índice curto (~30 linhas) explicando estrutura nova
├── dashboard.html             # NOVO — gerado pela skill, abre direto no browser
├── deploy/                    # NOVO — pasta dedicada
│   ├── coolify.md             # UUIDs, domínios, repo, GitHub App (humano edita raramente)
│   ├── env-vars.md            # listas backend/frontend/supabase + matriz prod-only
│   ├── secrets.md             # 3 secrets auto-gerados + comandos
│   ├── gates.md               # pre-flight + rollback policy + hard-excludes + comandos MCP
│   ├── state.json             # NOVO — snapshot atual (escrito pela skill)
│   └── history.json           # NOVO — últimos 50 deploys (escrito pela skill)
└── historico/                 # mantido (changelog humano por mês via /blueprint-sync)
    └── 2026-04.md
```

**Por que essa quebra:**
- Cada `.md` em `deploy/` tem uma natureza só → fim da mistura.
- `state.json`/`history.json` são a única fonte que a skill escreve no caminho `ship` → idempotência trivial (rewrite completo, sem marcadores HTML).
- `DEPLOY.md` raiz vira página índice (mantém bookmarks externos funcionando) com link para o dashboard.
- `dashboard.html` é apenas renderização — skill é a fonte; arquivo é derivada.

#### Schemas dos JSONs

`blueprint/deploy/state.json` (snapshot, ~80 linhas):

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-04-25T05:03:00-03:00",
  "updated_by": "deploy-skill@ship",
  "production": {
    "domain_root": "mala-ia.cloud",
    "vps_ip": "31.97.29.32",
    "coolify_url": "https://coolify.mala-ia.cloud"
  },
  "services": [
    {
      "id": "backend", "uuid": "...", "domain": "api.mala-ia.cloud",
      "port": 8000, "health_path": "/api/health",
      "status": "healthy",
      "last_deploy_sha": "5b1e071", "last_deploy_at": "...",
      "last_health_check": { "at": "...", "latency_ms": 94, "http_status": 200 },
      "build_duration_seconds": 90
    },
    { "id": "frontend", ... },
    { "id": "supabase", ... }
  ],
  "env_vars": {
    "backend": { "required": [...], "present": [...], "missing": [], "prod_only_ok": true, "violations": [] },
    "frontend": { "build_time_required": [...], "build_time_violations": [] },
    "supabase": { "mailer_keys_count": 8 }
  },
  "secrets": [
    { "name": "SIGNUP_ENCRYPTION_KEY", "service": "backend", "present": true }
  ],
  "migrations": { "total_applied": 30, "last_applied": "030_xxx.sql", "pending_local": [] },
  "gates": {
    "lint_backend": "ok", "lint_frontend": "ok", "env_example_sync": "ok",
    "secrets_clean": "ok", "migrations_backup_absent": "ok"
  },
  "next_actions": [
    { "kind": "info", "text": "Tudo verde — nada urgente." }
  ],
  "last_run": { "mode": "ship", "sha": "fe9cfbc", "result": "healthy", "duration_seconds": 247 }
}
```

`blueprint/deploy/history.json` (timeline, prepend a cada deploy, truncado a 50):

```json
{
  "schema_version": "1.0",
  "deploys": [
    {
      "at": "2026-04-25T02:03:00-03:00",
      "sha": "fe9cfbc",
      "subject": "feat(auth-email): templates pt-BR servidos via frontend/public/",
      "scope": ["frontend", "supabase-env"],
      "result": "healthy",
      "duration_seconds": 132,
      "services_touched": ["frontend"],
      "migrations_applied": [],
      "env_changes": [{ "service": "supabase", "action": "create", "keys": [...] }],
      "rollback_target_sha": null
    }
  ]
}
```

**Princípio de segurança:** os JSONs **nunca** carregam valor de env var ou secret. Só `name` + `present: true|false`. Na renderização, secret aparece como chip cinza "presente" ou vermelho "ausente".

#### Anatomia do `dashboard.html`

Arquivo único, ~600-800 linhas (HTML + CSS + JS embutidos), zero deps externas:

```
┌── <head>
│   ├── <meta charset, viewport, color-scheme="dark light">
│   └── <style> ... ~300 linhas de CSS, custom properties, container queries </style>
│
├── <body>
│   ├── <header>      Hero pulse: status global + commit + tempo desde deploy
│   ├── <section #services>   3 cards (backend/frontend/supabase) com status, latência, SHA
│   ├── <section #gates>      Checklist visual de pre-flight (8 ícones)
│   ├── <section #env-vars>   Matrix de chips coloridos, agrupado por serviço
│   ├── <section #migrations> Aplicadas vs pendentes + próximas ações sugeridas
│   ├── <section #timeline>   Últimos 10 deploys com drawer de detalhes via <dialog>
│   ├── <details #mcp-ref>    Accordion colapsado com comandos MCP (copy-on-click)
│   └── <footer>      Timestamp + link "Aberto pelo /deploy"
│
├── <script>
│   ├── const STATE = {...};           // injetado pela skill
│   ├── const HISTORY = {...};         // injetado pela skill
│   ├── render funções por seção
│   ├── stagger no load via Web Animations API
│   ├── view transitions no abrir/fechar do <dialog> de detalhes
│   └── pulse animation com CSS @keyframes (status dot)
│
└── </body>
```

**Princípios visuais (impeccable applied):**
- Tipografia: `system-ui` ou Geist (fallback `system-ui`); 1 família, 4 pesos. Sem Inter (anti-pattern impeccable: "purple gradients + Inter").
- Cor: `prefers-color-scheme` automático; paleta com 1 acento (verde-saúde), neutros frios em dark, neutros quentes em light. Nada de gradientes em texto, nada de cards aninhados em cards (anti-patterns impeccable).
- Espacial: grid responsivo via container queries; spacing scale 4/8/12/16/24/32/48/64.
- Motion: stagger fade-in dos cards (50ms apart); pulse no status dot; spring CSS no hover dos cards (`transform: translateY(-2px)`); view transition no `<dialog>` de detalhes.
- UX writing: pt-BR direto, sem jargão. "Produção saudável há 2h" > "Status: healthy".

### Mudanças necessárias na skill `/deploy`

Arquivo: `/Users/pedrorezende/.claude/skills/deploy/SKILL.md`

| Passo atual | Mudança proposta |
|---|---|
| **Passo 1 (ship)** — Lê `DEPLOY.md` | Lê `blueprint/deploy/state.json` para UUIDs/domínios + `gates.md` (em `--verbose`). Se `state.json` ausente → instrui rodar `/deploy migrate-blueprint` (subcomando novo). |
| **Passo 2.5-2.7** — Valida env vars | Inalterado, mas agora popula `state.json.env_vars` em vez de markdown. |
| **Passo 5** — Monitora deploy Coolify | Captura `build_duration_seconds` por app pra `state.json.services[].build_duration_seconds`. |
| **Passo 7** — Health check | Captura `latency_ms` real (já existe a base com `--write-out` no curl); persiste em `state.json.services[].last_health_check`. |
| **Passo 9** — Atualiza blueprint | **Mudança maior.** Reescreve `state.json` inteiro; faz prepend em `history.json` truncado a 50; **regenera** `dashboard.html` via templating embutido na skill (string interpolation). Markdown raiz `DEPLOY.md` fica intocado. |
| **Setup Fase 12** | Escreve em `coolify.md` (com marcadores `<!-- blueprint:section:xxx -->` mantidos só ali) + `state.json` inicial + `dashboard.html` inicial. |
| **Status mode** | Lê `state.json` direto (em vez de parsear markdown). Output ganha linha "Dashboard: file:///.../blueprint/dashboard.html". |
| **Rollback mode** | Lê `history.json` (mais robusto que parsear markdown); registra rollback como nova entrada com `rollback_target_sha` preenchido. |

#### Templating do `dashboard.html` na skill

A skill `/deploy` é texto markdown executado pelo Claude Code — não roda Python/JS por si só. Para regerar o HTML:
- A skill **detém** o template completo do HTML embutido em si própria, como heredoc dentro do passo 9.
- Substitui dois placeholders: `__STATE_JSON__` e `__HISTORY_JSON__` pelos conteúdos atuais.
- Escreve o arquivo final em `blueprint/dashboard.html`.

Trade-off: o template aumenta o tamanho da `SKILL.md` (de 21KB pra ~30-35KB). Aceitável.

### Migration path (do estado atual pro novo)

Subcomando novo: `/deploy migrate-blueprint`. Roda 1 vez.

1. Lê `blueprint/DEPLOY.md` atual e parseia as 9 seções.
2. Cria `blueprint/deploy/coolify.md`, `env-vars.md`, `secrets.md`, `gates.md` extraindo os blocos correspondentes.
3. Constrói `blueprint/deploy/state.json` inicial a partir do que está em `<!-- blueprint:section:status -->` + dados do Coolify (chama MCP `get_application` etc para preencher latências reais).
4. Constrói `blueprint/deploy/history.json` parseando o bloco `<!-- blueprint:section:historico -->`.
5. Renomeia `blueprint/DEPLOY.md` → `blueprint/DEPLOY.md.legacy` (mantém pra rollback do refactor) e cria novo `DEPLOY.md` curto que linka pra estrutura nova.
6. Gera `blueprint/dashboard.html` pela primeira vez.
7. Reporta diff visual ao Pedro: "antes 1 arquivo de 211 linhas; agora 4 mds + 2 jsons + 1 html, total X linhas".

Próximo `/deploy` ship usa a estrutura nova nativamente.

### Críticos a modificar

- `/Users/pedrorezende/.claude/skills/deploy/SKILL.md` — passos 1, 5, 7, 9, setup Fase 12, status, rollback + novo subcomando `migrate-blueprint` + template do `dashboard.html` embutido.
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/DEPLOY.md` — vira índice curto.
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/README.md` — atualizar 1 linha que descreve `DEPLOY.md`.

### Críticos a criar

- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/coolify.md`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/env-vars.md`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/secrets.md`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/gates.md`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/state.json`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/history.json`
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/dashboard.html`

### Sequência de execução

1. **Mover este plano** para `planos/plano-26-04-25-0403h-blueprint-dashboard-impeccable.md` (feito).
2. **Instalar impeccable** global (feito).
3. **Esboçar o dashboard.html** isoladamente — usar a skill `impeccable` para refinar visual.
4. **Migrar o blueprint** manualmente — quebrar `DEPLOY.md` em `deploy/*.md`, escrever JSONs iniciais.
5. **Atualizar a skill `/deploy`** com os passos novos + template embutido + subcomando `migrate-blueprint`.
6. **Rodar `/deploy status`** para validar leitura de `state.json`.
7. **Rodar `/deploy`** num commit pequeno para validar o ciclo completo.
8. **Abrir `dashboard.html`** no browser e validar.
9. **Commit final** consolidando.

### Verificação end-to-end

| O quê | Como testar |
|---|---|
| Migração não perde dados | Comparar UUIDs/domínios/env vars antes (`DEPLOY.md`) e depois (`state.json`). Diff manual. |
| Skill lê state.json corretamente | `/deploy status` produz output com mesmos UUIDs e SHAs. |
| Dashboard renderiza tudo | Abrir `file://.../blueprint/dashboard.html` no Chrome e Safari. Conferir 7 blocos visíveis, sem console errors. |
| JSONs não vazam secrets | `grep -iE "(api_key\|secret\|password\|token)" blueprint/deploy/state.json blueprint/deploy/history.json` deve retornar **só nomes de chaves**. |
| Dark/light funciona | Trocar `prefers-color-scheme` no DevTools. |
| Motion respeita `prefers-reduced-motion` | `@media (prefers-reduced-motion)` desabilita stagger e pulse. |
| Skill regenera HTML idempotentemente | Rodar `/deploy` 2x sem código novo: 1ª roda atualiza, 2ª pode atualizar `last_health_check` mas o resto é byte-idêntico. |
| Anti-patterns impeccable | Skill `impeccable` em modo `audit` retorna 0 violations no HTML final. |
| Rollback continua funcionando | `/deploy rollback --dry-run` lê `history.json` e mostra alvo correto. |

### Riscos & guardrails

- **Secrets em JSON**: garantir que o passo 9 da skill **não** loga valores; só `present: true|false` por chave. Adicionar gate auto na skill: se `state.json` resultante contém regex `(?:[a-zA-Z0-9+/]{40,}|sk-[a-zA-Z0-9]{20,})` em qualquer campo `value`, abortar com erro.
- **Manutenção tripla (md + json + html)**: mitigado porque (a) html é gerado, sem manutenção manual; (b) md e json têm responsabilidades distintas e não se sobrepõem.
- **Drift durante migration**: manter `DEPLOY.md.legacy` 1 release antes de remover.
- **`prefers-reduced-motion`**: dashboard respeita acessibilidade; quem desativou motion vê tudo estático.
- **Tamanho do `SKILL.md`**: cresce ~50% com o template embutido. Aceitável; alternativa seria salvar template em `~/.claude/skills/deploy/dashboard-template.html` e a skill só interpolar — pode ser refactor v1.1 se a SKILL ficar pesada demais.

### Saúde da proposta

- Resolve a reclamação concreta ("muito confuso, várias variáveis").
- Atende o desejo expresso ("`.html` com motion", "impecável").
- Mantém retrocompatibilidade durante a migração.
- Zero dependências novas no projeto Hospital (motion via APIs nativas, impeccable só global).
- Fonte estruturada (`state.json`) destrava futuras integrações (CI gates, métricas, dashboard remoto se um dia quiser).
- Skill `/deploy` continua sendo a única dona do estado de produção.

---

## Execução / Resultados

### 2026-04-25 04:03h — Setup inicial

- ✅ Plano aprovado em plan mode.
- ✅ Plano original gerado em `~/.claude/plans/eu-preciso-que-voce-mutable-teapot.md` e movido aqui na convenção `planos/plano-AA-MM-DD-HHMMh-...md`.
- ✅ Skill `pbakaus/impeccable` instalada via `npx skills add pbakaus/impeccable -g -y -a claude-code`.
  - Destino: `~/.claude/skills/impeccable/`.
  - Source clonado: `~/.agents/skills/impeccable/`.
  - Security scan: Gen=Safe, Socket=0 alerts, Snyk=Low Risk.
  - Skill é **uma única** chamada `impeccable` (não 23 skills separadas como o site sugeria) — descrição cobre design/redesign/shape/critique/audit/polish/clarify/distill/harden/optimize/adapt/animate/colorize/extract.

### Pendente

- Esboçar `dashboard.html` em arquivo descartável (sandbox).
- Migrar `blueprint/DEPLOY.md` para nova estrutura (4 mds + 2 jsons + 1 html).
- Atualizar `~/.claude/skills/deploy/SKILL.md` (passos 1/5/7/9/setup-12/status/rollback + template embutido + subcomando `migrate-blueprint`).
- Rodar `/deploy status` e `/deploy` em commit pequeno para validar end-to-end.
- Commit final.
