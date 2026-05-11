# Plano — Skill `/deploy` unificada (Abordagem C) + `blueprint/DEPLOY.md`

> Após ExitPlanMode, este arquivo é movido para a raiz do projeto como `plano-deploy-unificado.md` (convenção do CLAUDE.md).

---

## Contexto

Hoje o projeto tem **3 skills de deploy** com sobreposição pesada:
- `/start-deploy` — setup inicial do Coolify (7 fases)
- `/sop-check` — pre-flight checklist (5 fases A–E, orquestrador que chama `/producao-doc` + `/deploy`)
- `/deploy` — deploy contínuo (8 passos com sub-etapas)

**Dores mapeadas (todas confirmadas):**
1. 3 comandos separados — nunca sabe qual usar
2. Perguntas redundantes durante o fluxo (commit? versão? rollback A/B/C?)
3. Steps manuais fora do terminal (abrir Coolify, rodar psql, copiar SQL)
4. Docs fragmentados em 3 lugares (`deploy-history.md`, `PRODUCAO.md`, `<projeto>-env-producao.txt`)

**Decisões do usuário:**
- Perfil alvo: Pedro (dev único, quer reduzir overhead cognitivo). Jargão técnico ok, mas cirúrgico.
- Doc "só saída": skill pergunta quando precisa, doc reflete o estado depois (nada de editar doc antes pra configurar).
- Coolify do zero (primeiro deploy ainda não rolou).
- **Abordagem C escolhida:** 1 skill `/deploy` com subcomandos explícitos (`setup`, `status`, `rollback`).
- Migrations: aplicar auto, exceto DDL destrutivo (DROP, TRUNCATE, DROP COLUMN) → pede confirmação.
- Versionamento: só git SHA + timestamp + resumo (sem semver).

Escopo deste plano: **apenas resolver deploy.** O blueprint completo (README/ARQUITETURA/FLUXOS/AMBIENTES) e hook post-commit ficam para próxima fase — não implemento agora.

---

## Arquitetura final

Uma skill `/deploy` com 4 modos explícitos via subcomando:

```
/deploy           → modo "ship" (default) — deploy operacional diário
/deploy setup     → setup inicial do Coolify (roda 1x por projeto)
/deploy status    → reporta estado atual sem alterar nada
/deploy rollback  → reverte pro último SHA saudável
```

**Localização da skill:** `~/.claude/skills/deploy/SKILL.md` (substitui as 3 skills antigas).

**Documento vivo:** `blueprint/DEPLOY.md` (versionado na raiz do projeto, input + output da skill).

---

## Estrutura da skill `/deploy`

### Modo `/deploy` (ship — default)

Fluxo linear, sem ramificações:

```
1. Lê blueprint/DEPLOY.md (UUIDs, domínios, config)
   → se arquivo não existe ou UUIDs vazios → sugere `/deploy setup` e para
2. Pre-flight (silencioso quando passa, reporta só falha):
   · lint backend: `uv run ruff check . && uv run ruff format --check .`
   · lint frontend: `pnpm lint && pnpm exec tsc --noEmit`
   · .env.example ↔ config.py chaves sincronizadas
   · NEXT_PUBLIC_* com is_build_time=true (MCP env_vars list)
   · vars prod-only: ENVIRONMENT=production, DEBUG=false, ENABLE_BYPASS_ENDPOINTS=false, CLICKSIGN_BASE_URL=https://app.clicksign.com
   · secrets auto-gerados presentes (SIGNUP_ENCRYPTION_KEY; gerar+setar se faltar)
   · .git status limpo de .env/.env.backup/credentials
   · migrations_backup/ não existe
   · lista migrations novas (mais recentes que último deploy registrado)
3. Infere mensagem de commit via diff (conventional commits: feat/fix/chore/refactor + escopo)
   [PERGUNTA ÚNICA: "msg: <inferida>. ok? (enter / e para editar / n para abortar)"]
4. git add <arquivos modificados - exclude hard-coded> && git commit -m "<msg>" && git push origin main
5. Monitora deploy Coolify via MCP (loop get até finished/failed)
   Output compacto: "backend: queued → building → deploying → finished (1m12s)"
6. Aplica migrations novas (se houver):
   · Parse SQL → classifica cada statement: safe vs destrutivo
   · Safe (CREATE, INSERT, SELECT, ALTER...ADD, UPDATE com WHERE): aplica via `mcp__coolify__application` terminal exec no container supabase-db
   · Destrutivo (DROP, TRUNCATE, DELETE sem WHERE, ALTER...DROP COLUMN/CONSTRAINT): mostra SQL completo e pede confirmação explícita
7. Health check:
   · `mcp__coolify__diagnose_app` backend + frontend
   · curl https://api.mala-ia.cloud/api/health (espera {"status":"ok"})
   · curl -I https://app.mala-ia.cloud (espera 200)
8. Se health falhou: auto-rollback (1 tentativa, modo B do /deploy atual) → redeploy último SHA healthy via MCP
9. Atualiza blueprint/DEPLOY.md:
   · seção "Status atual" (sobrescreve)
   · seção "Histórico" (append no topo, mantém 10)
```

**Perguntas que a skill FAZ** (exatamente 1 no fluxo ok, 0-1 extras se migrations destrutivas):
- Confirmação de mensagem de commit (enter/editar/abortar)
- SE houver DDL destrutivo: "Aplicar este SQL? [mostra SQL] (y/n)"

**Perguntas que a skill NUNCA faz** (decisão automatizada):
- "quer commitar?" → sempre sim se pre-flight passou
- "quer incluir todos arquivos?" → sempre sim, exclui hard-coded: `.env`, `.env.backup`, `.env.local`, `deploy-history.md`, `*-env-producao.txt`, `credentials*`
- "qual a versão?" → SHA + timestamp, sem semver
- "rollback opção A/B/C?" → só B (redeploy último SHA), auto-aciona em falha

**Escape hatches:**
- `/deploy --verbose` → mostra cada gate passando (default silencioso)
- `/deploy --skip-lint` → pula lint (só pra emergência, reporta warning)
- `/deploy --no-migrations` → ignora migrations mesmo se houver novas

### Modo `/deploy setup`

Roda 1x no projeto pra criar tudo no Coolify do zero. Preserva a lógica do `/start-deploy` atual, mas enxuta.

```
1. Perguntas iniciais (4 perguntas, resto infere):
   · Domínio principal? (ex: mala-ia.cloud)
   · IP da VPS? (ex: 31.97.29.32)
   · Nome do GitHub repo? (ex: pedrorezendefig/hospital-reunioes)
   · Branch de deploy? (default: main)
2. Detecta tech stack (Next.js + FastAPI + Supabase) lendo package.json, pyproject.toml, supabase/config.toml
3. Valida/cria Dockerfiles (modo produção, usuário não-root, HEALTHCHECK)
4. Cria no Coolify via MCP (em sequência, com confirm antes):
   · Projeto
   · Supabase service (se ainda não existe)
   · App backend (base_directory, ports, fqdn, health_check)
   · App frontend (base_directory, ports, fqdn, NEXT_PUBLIC_* com is_build_time=true)
5. Env vars: lê .env.example + pede valor para cada chave marcada "<PREENCHER>" (1 vez, salva no Coolify direto)
6. Gera secrets auto-gerados (SIGNUP_ENCRYPTION_KEY via cryptography.fernet) e seta no backend
7. Imprime tabela de DNS para configurar no Cloudflare/Hostinger (mostra registros A)
8. Aguarda user confirmar DNS propagado (pergunta "dns ok? (y)")
9. Dispara primeiro deploy via MCP + monitora
10. Escreve blueprint/DEPLOY.md com os UUIDs gerados, domínios, vars obrigatórias
11. Ao fim: "Setup completo. Use /deploy pra deploys futuros."
```

### Modo `/deploy status`

Zero alterações. Só lê e reporta:

```
1. Lê blueprint/DEPLOY.md
2. Chama mcp__coolify__list_applications + get_application pra cada app
3. Chama mcp__coolify__diagnose_app backend + frontend
4. Compara SHA local (HEAD) vs último SHA em produção
5. Reporta em 1 tela:
   · Apps: backend (healthy/down, último deploy, latência)
           frontend (healthy/down, último deploy)
           supabase (healthy/down)
   · SHA local vs prod: "atrás em 3 commits" ou "em sync"
   · Migrations novas pendentes: N arquivos
   · Último deploy: 2026-04-20 18:30 — abc1234 — feat: ata PDF
```

### Modo `/deploy rollback`

Reverte de forma determinística:

```
1. Lê blueprint/DEPLOY.md histórico → identifica último deploy com status "healthy"
2. Mostra: "Reverter pra abc1234 (2026-04-19 14:15 — fix: webhook)? (y/n)"
3. Se y: mcp__coolify__deploy com uuid do deploy saudável → monitora → diagnose
4. Atualiza blueprint/DEPLOY.md com entrada "ROLLBACK"
```

---

## `blueprint/DEPLOY.md` — estrutura

Localização: `/Users/pedrorezende/PedroDev/Hospital/blueprint/DEPLOY.md` (versionado).

```markdown
# DEPLOY — Hospital Reuniões

> Documento vivo. A skill `/deploy` lê as seções de config e escreve as de estado.

---

## Config (você edita)
<!-- blueprint:section:config-coolify -->

**VPS:** Hostinger 16GB, IP `31.97.29.32`
**Coolify:** https://coolify.mala-ia.cloud
**Projeto Coolify:** <uuid>
**GitHub App UUID:** <uuid>
**Server UUID:** <uuid>

| App | UUID | Porta | Domínio | Health check |
|---|---|---|---|---|
| backend | `q11fubn3ezlszvwph695d9oh` | 8000 | api.mala-ia.cloud | /api/health |
| frontend | `n5omtnv1u8u268zprvwu7902` | 3000 | app.mala-ia.cloud | — |
| supabase | `<uuid>` | — | studio.mala-ia.cloud | — |

<!-- blueprint:section:config-env -->

### Vars obrigatórias backend (devem existir no Coolify)
ENVIRONMENT, DEBUG, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENAI_API_KEY,
CLICKSIGN_API_KEY, CLICKSIGN_BASE_URL, CLICKSIGN_WEBHOOK_SECRET,
RESEND_API_KEY, RESEND_FROM_EMAIL, SIGNUP_ENCRYPTION_KEY, SIGNUP_PASSE,
ENABLE_BYPASS_ENDPOINTS

### Vars prod-only (skill valida os valores)
| Var | Valor obrigatório |
|---|---|
| ENVIRONMENT | production |
| DEBUG | false |
| ENABLE_BYPASS_ENDPOINTS | false |
| CLICKSIGN_BASE_URL | https://app.clicksign.com |

### Vars frontend (build-time)
NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_ENVIRONMENT

<!-- blueprint:section:config-secrets -->

### Secrets auto-gerados (skill gera se faltar)
| Var | Serviço | Gerador |
|---|---|---|
| SIGNUP_ENCRYPTION_KEY | backend | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

---

## Status atual de produção (skill escreve)
<!-- blueprint:section:status -->

**Último deploy:** _(preenchido pela skill)_
**Commit:** _(SHA)_
**Timestamp:** _(YYYY-MM-DD HH:MM)_

| Serviço | Status | Último deploy | Latência |
|---|---|---|---|
| backend | — | — | — |
| frontend | — | — | — |
| supabase | — | — | — |

---

## Histórico (skill escreve, append no topo, máx 10)
<!-- blueprint:section:historico -->

_(vazio até primeiro deploy)_

---

## Gates pré-deploy
<!-- blueprint:section:gates -->

Lista do que `/deploy` valida automaticamente (informativa, você não precisa editar):

- lint backend (ruff check + format)
- lint frontend (pnpm lint + tsc --noEmit)
- .env.example ↔ config.py sincronizados
- vars prod-only com valores corretos
- NEXT_PUBLIC_* com is_build_time=true
- secrets auto-gerados presentes no Coolify
- git status sem arquivo sensível
- migrations_backup/ ausente
- migrations novas listadas (não bloqueia)
```

---

## Arquivos críticos a criar/modificar/deletar

**CRIAR:**
- `~/.claude/skills/deploy/SKILL.md` — nova skill unificada (substitui 3 antigas)
- `blueprint/DEPLOY.md` — documento vivo com config + estado
- `plano-deploy-unificado.md` (raiz do projeto, após ExitPlanMode) — copia deste plan file

**MODIFICAR:**
- `~/.claude/settings.json` — remover hook `PostToolUse` do `producao-doc-watcher` (comando antigo obsoleto)
- `.gitignore` do projeto — adicionar `/tmp/deploy.log`, remover referência a `deploy-history.md` se tiver

**DELETAR:**
- `.claude/commands/deploy.md` (projeto) — skill antiga
- `.claude/commands/sop-check.md` (projeto) — skill antiga
- `.claude/commands/start-deploy.md` (projeto) — skill antiga
- `~/.claude/skills/producao-doc/` — pasta inteira
- `~/.claude/hooks/producao-doc-watcher.sh`
- `deploy-history.md` se existir (conteúdo útil já migrou pro blueprint/DEPLOY.md)
- `PRODUCAO.md` (já está `D` no git status — confirma deleção)
- `implementacoes/` (pasta vazia)

---

## Ordem de execução

1. Ler uma última vez as 3 skills antigas para extrair lógica MCP + UUIDs exatos + algoritmos de pre-flight.
2. Criar `blueprint/DEPLOY.md` com as seções e UUIDs atuais (preenchidos manualmente com os conhecidos).
3. Criar `~/.claude/skills/deploy/SKILL.md` com os 4 modos implementados em detalhe (cada modo é uma seção do SKILL.md, escolhida via primeiro argumento).
4. Testar cada modo manualmente:
   - `/deploy status` primeiro (só lê, zero risco)
   - `/deploy setup --dry-run` (valida lógica sem criar recursos — adicionar flag se viável)
   - `/deploy` real no primeiro push (monitorar atento)
   - `/deploy rollback` intencional depois de um deploy pequeno (validar fluxo)
5. Deletar as 3 skills antigas + hook + PRODUCAO.md + implementacoes/.
6. Remover hook `PostToolUse` obsoleto do `settings.json`.
7. Atualizar CLAUDE.md do projeto pra remover referência a `implementacoes/` (separado desse plano mas mencionado pra não esquecer).

---

## Verificação end-to-end

Ao completar:

- [ ] `ls ~/.claude/skills/deploy/SKILL.md` → existe
- [ ] `ls ~/.claude/skills/producao-doc/` → não existe
- [ ] `ls ~/.claude/hooks/producao-doc-watcher.sh` → não existe
- [ ] `grep producao-doc ~/.claude/settings.json` → zero matches
- [ ] `ls .claude/commands/` → não lista deploy.md, sop-check.md, start-deploy.md
- [ ] `cat blueprint/DEPLOY.md` → tem seções config, status, histórico, gates com marcadores HTML comment
- [ ] `/deploy status` → reporta apps, SHA local vs prod, sem alterar nada
- [ ] `/deploy` em mudança trivial (ex: bump de dep) → pre-flight silencioso, 1 pergunta de commit msg, push + monitoramento, status atualizado no blueprint/DEPLOY.md
- [ ] `/deploy` com migração safe (CREATE TABLE) → aplica auto sem perguntar
- [ ] `/deploy` com migração destrutiva (DROP TABLE teste) → mostra SQL, pede confirmação
- [ ] `/deploy rollback` após deploy recente → identifica SHA anterior, pede confirmação, redeploy via MCP
- [ ] `ls implementacoes/` → não existe
- [ ] `ls PRODUCAO.md` → não existe

---

## Riscos & mitigações

| Risco | Mitigação |
|---|---|
| Regex de "DDL destrutivo" falha e aplica DROP | Lista conservadora: `DROP`, `TRUNCATE`, `DELETE\s+FROM(?!.*WHERE)`, `ALTER.*DROP`. Se QUALQUER match → sempre pede confirm. Testar com suite de SQL samples antes de usar em prod. |
| Auto-rollback piora situação (SHA anterior também quebrado) | Rollback roda 1x. Se 2º health check falhar após rollback, para e pede intervenção humana com logs. |
| Inferência de commit msg gera mensagem ruim | Sempre exibe antes + opção editar. Nunca commit cego. |
| `/deploy setup` duplica recursos que já existem no Coolify | Cada ação verifica estado atual via MCP antes de criar (idempotente). Se app existe → pergunta "usar existente ou recriar?". |
| Pre-flight silencioso esconde warnings úteis | Flag `--verbose` mostra cada gate. Saída de falha sempre reporta o item específico. |
| Deletar as 3 skills antigas impede rollback do próprio fluxo | Plano mantém estas skills no git history. Se precisar voltar, `git show HEAD~N:.claude/commands/deploy.md` recupera. |
| Skill ~400 linhas fica grande demais | Cada modo é uma seção com header claro. Índice no topo. Se passar de 500 linhas, refatoro em arquivos references/ depois. |
| MCP Coolify cai no meio do deploy | Skill tem retry com backoff em MCP calls. Se falha persistente → reporta erro e para, estado fica rastreável no blueprint/DEPLOY.md como "em progresso". |
