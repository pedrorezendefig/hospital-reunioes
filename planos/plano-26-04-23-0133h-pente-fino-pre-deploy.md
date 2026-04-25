# Plano — Pente fino pré-primeiro-deploy

## Contexto

Hospital Reuniões está prestes a fazer o **primeiro deploy de produção** via Coolify (UUIDs ainda em branco no `blueprint/DEPLOY.md`). Antes de subir, queremos passar um pente fino multi-camada (qualidade de código, simplicidade, segurança, UX) para reduzir o risco do "primeiro contato com produção".

**Estado de partida (descobertas dos exploradores):**

- ✅ Stack maduro: FastAPI + Python 3.12 (com `ruff` + `mypy` + `pytest` configurados, ~15 testes), Next.js 15 + React 19 (lint + tsc), CI já roda lint nos dois.
- ✅ Working tree GREEN: 12 arquivos modificados sem `console.log`, `pdb`, secrets hardcoded ou refs quebradas para a rota `/participantes` removida. Todos os endpoints sensíveis têm `Depends(get_current_user)`.
- ✅ Auth, CORS, Pydantic validation, middleware de proteção de rotas, gate de `ENVIRONMENT=production` e `ENABLE_BYPASS_ENDPOINTS=false` no `/deploy`.
- ⚠️ Arquivos novos `atas-migracao-*.json` na raiz (untracked, mas regra `/*.md` no `.gitignore` não cobre `.json` — risco de commit acidental).
- ⚠️ CI roda apenas lint, sem `pytest` nem `tsc --noEmit` (o tsc está no script `lint` mas não como step próprio).
- ⚠️ Frontend tem **zero testes** (decisão consciente: deixar pra próxima sprint).
- ⚠️ Arquivos enormes (`reunioes/[id]/page.tsx` 2086 linhas, `admin/usuarios/page.tsx` 810 com 4 mudanças recentes, `reunioes/page.tsx` com paginação nova) merecem segunda leitura antes de ir pra produção.
- ⚠️ Coolify ainda não foi configurado (`Projeto Coolify UUID`, `Server UUID`, `GitHub App UUID`, `Supabase Service UUID` em branco no `DEPLOY.md`).

**Objetivo:** chegar ao `/deploy` ship com (a) achados de revisão documentados, (b) simplificações aplicadas onde seguras, (c) CI mais firme, (d) Coolify configurado e gates verdes.

**Tempo estimado:** 2-3h de trabalho assistido (você aprovando cada etapa).

---

## Princípios

- **Cada relatório vai para um arquivo `.md` na raiz** (`revisao-*.md`), ignorado pelo `.gitignore` (regra `/*.md`). Você lê no VS Code, aprova mudanças, depois apaga.
- **Aplicar correções uma camada de cada vez**, não em rajada. Após cada relatório, decidimos juntos: aplicar / adiar / descartar.
- **Não introduzir refactors grandes** — esse é um pente fino pré-deploy, não um milestone novo. Achados grandes viram backlog.
- **Lint local antes de commitar**: `uv run ruff check . && uv run ruff format --check .` no backend, `pnpm lint && pnpm exec tsc --noEmit` no frontend (mesmos gates do `/deploy`).

---

## Pipeline (perfil Padrão)

### Etapa 0 — Higiene do working tree (~10min)

**Objetivo:** entrar no pente fino com tree controlada.

1. Decidir destino dos 4 untracked `atas-migracao-*.json`:
   - **Opção A:** mover para `/atas-migracao/` (já no `.gitignore`).
   - **Opção B:** adicionar `atas-migracao-*.json` ao `.gitignore` da raiz.
   - Recomendação: **Opção B** (artefatos da skill `/migrar-atas` são gerados na raiz por design — adicionar padrão).
2. Decidir o que fazer com os 12 modificados + 2 deletados:
   - Commit incremental (3-4 commits temáticos: `chore(ignore)`, `refactor(participantes)`, `feat(reunioes/pagination)`, `fix(admin/schemas)`).
   - Ou um único commit `chore(pre-deploy): higiene + ajustes finais`.
   - Recomendação: **commits temáticos** — facilitam rollback granular.

### Etapa 1 — Code review estruturado (~30min)

**Skill:** `code-review:code-review` (review da branch atual, foco nos 12 modificados).

**Output:** `revisao-code.md` — checklist por arquivo: severidade (BLOCKER/MAJOR/MINOR/NIT), descrição, sugestão concreta com path:linha.

**Foco extra:**
- `frontend/src/app/admin/usuarios/page.tsx` (810 linhas, 4 mudanças) — verificar se o tratamento granular de erros não regrediu UX.
- `frontend/src/app/reunioes/page.tsx` — paginação nova (PAGE_SIZE=15), validar comportamento de borda (página vazia, total < PAGE_SIZE).
- `backend/app/services/importacao_service.py` — campos `total_acoes/acoes_concluidas` adicionados, garantir que migrations existentes não quebram.
- `backend/app/models/admin_schemas.py` — campos Optional, verificar que clientes do schema lidam com `null`.

### Etapa 2 — Simplificação cirúrgica (~30min)

**Skill:** `simplify` (aplicada apenas aos arquivos modificados recentemente, não em arquivos legacy intocados).

**Output:** `revisao-simplify.md` — oportunidades de reuso, redução de duplicação, simplificação de estado/efeitos.

**Restrição:** **só aplicar simplificações cuja diferença é trivial de auditar** (≤30 linhas mudadas por arquivo). Se um arquivo precisa de refactor estrutural, vira backlog (`gsd-add-backlog`) — não bloqueia deploy.

### Etapa 3 — Security review (~30min)

**Skill:** `security-review` (skill nativa, varre branch atual à procura de OWASP top 10).

**Output:** `revisao-seguranca.md` — achados por severidade.

**Foco extra (validar manualmente além do que a skill detecta):**
- Confirmar `ENABLE_BYPASS_ENDPOINTS=false` em prod (já é gate do `/deploy`, mas grep também por uso real do flag em `backend/app/`).
- Confirmar que `SUPABASE_SERVICE_ROLE_KEY` nunca é exposto ao cliente (frontend só usa `NEXT_PUBLIC_SUPABASE_ANON_KEY`).
- CORS em `main.py`: `allow_origins=[settings.frontend_url]` — confirmar que `frontend_url` em prod é `https://app.mala-ia.cloud` (não `*`).
- Webhook ClickSign: `CLICKSIGN_WEBHOOK_SECRET` é validado em todo handler? (grep `webhook_secret`).
- Rate limiting: existe em algum endpoint público (`/api/health`, login, signup)? Se não, registrar como backlog (não bloqueia primeiro deploy se o app estiver atrás do Cloudflare/Coolify proxy).

### Etapa 4 — UI / UX retroativo (~30min)

**Skill:** `gsd-ui-review` (audit visual retroativo do frontend implementado).

**Output:** `revisao-ui.md` — score nas 6 dimensões (visual hierarchy, typography, color, spacing, interaction, accessibility).

**Foco:** as telas tocadas recentemente na Fase 3 (`/admin/usuarios`, `/admin/reunioes`, `/admin/pendencias`, `/reunioes` com paginação). Achados graves (a11y broken, contraste WCAG AA falhando) → corrigir antes do deploy. Achados médios → backlog.

### Etapa 5 — CI/CD reforçado (~20min)

**Arquivo:** `.github/workflows/ci.yml`.

**Mudanças:**
1. Adicionar step `Test` no job `backend-lint` (renomear para `backend`):
   ```yaml
   - name: Test (pytest)
     run: pytest --maxfail=3 --disable-warnings -q
   ```
2. Garantir que `tsc --noEmit` é step próprio no `frontend-lint` (já está, mas validar que `pnpm lint` não pula em caso de tsc fail).
3. Opcional (decidir caso a caso): adicionar `pip cache` no setup-python para acelerar.

### Etapa 6 — Setup do Coolify (~30min)

**Skill:** `/deploy setup` — preenche os UUIDs em branco no `blueprint/DEPLOY.md`:
- `Projeto Coolify UUID`
- `Server UUID`
- `GitHub App UUID`
- `Supabase Service UUID`

A skill conversa com a API do Coolify via MCP, lista projetos/servers/apps existentes, deixa você escolher e grava nos marcadores HTML. Também valida:
- `is_build_time=true` nas vars `NEXT_PUBLIC_*`.
- Vars prod-only (`ENVIRONMENT=production`, `DEBUG=false`, `ENABLE_BYPASS_ENDPOINTS=false`, `CLICKSIGN_BASE_URL=https://app.clicksign.com`).
- Secrets auto-gerados (`SIGNUP_ENCRYPTION_KEY`, `CLICKSIGN_WEBHOOK_SECRET`, `SIGNUP_PASSE`) presentes no Coolify.

### Etapa 7 — Sync do blueprint (automático)

`/blueprint-sync` roda automaticamente no `post-commit` do hook `.githooks/post-commit`. Após cada commit das etapas anteriores, README/ARQUITETURA/FLUXOS/AMBIENTES são atualizados. **Nada a fazer manualmente** — só verificar que o hook está ativo:

```bash
git config --get core.hooksPath  # deve retornar .githooks
```

Se vier vazio: `git config core.hooksPath .githooks`.

### Etapa 8 — Primeiro `/deploy` (~10min de execução, ~5min observando)

**Skill:** `/deploy` (modo ship default).

Gates pré-deploy executados pela skill:
- Lint backend + frontend (mesmos comandos das etapas locais).
- `.env.example` ↔ `config.py` (mesmo conjunto de chaves).
- Git status sem secrets staged.
- `migrations_backup/` ausente.
- Vars build-time/prod-only OK no Coolify.
- Secrets auto-gerados presentes (gera se faltar).

Após gates verdes: dispara deploy backend + frontend, monitora health check, popula `status` e `historico` no `DEPLOY.md`.

Se health check falhar pós-deploy: rollback automático (1 tentativa).

---

## Skills selecionadas (resumo)

### Núcleo (Padrão)
| Skill | Etapa | Output |
|---|---|---|
| `code-review:code-review` | 1 | `revisao-code.md` |
| `simplify` | 2 | `revisao-simplify.md` |
| `security-review` | 3 | `revisao-seguranca.md` |
| `gsd-ui-review` | 4 | `revisao-ui.md` (em `.gsd/ui-review/`) |
| `/deploy setup` | 6 | atualiza `blueprint/DEPLOY.md` |
| `/blueprint-sync` (auto) | 7 | atualiza `blueprint/*.md` |
| `/deploy` | 8 | ship + atualiza `status`/`historico` |

### Auxiliares (chamadas sob demanda)
| Skill | Quando usar |
|---|---|
| `superpowers:verification-before-completion` | Antes de marcar qualquer etapa como concluída — força rodar o comando de verificação. |
| `gsd-add-backlog` | Para qualquer achado grande que não vai bloquear o deploy (vira `999.x` no backlog). |
| `gsd-add-todo` | Para mini-tarefas pontuais que surgirem durante a revisão. |
| `superpowers:systematic-debugging` | Se algum bug aparecer durante o pente fino e não tiver fix óbvio. |

### Explicitamente fora do escopo (perfil Padrão)
| Skill | Por quê |
|---|---|
| `gsd-add-tests` (backend) | Backend já tem ~15 testes; gerar mais agora vira backlog. |
| Vitest setup (frontend) | Decisão consciente: deploy primeiro, testes na próxima sprint. |
| `claude-seo:seo-technical` | App interno (não público), security headers cobertos pelo `security-review`. |
| `claude-seo:seo-performance` | Sem necessidade de Core Web Vitals para app interno. |
| `gsd-validate-phase` (Nyquist) | Útil em milestones longos; overkill para pré-deploy. |
| `ui-ux-pro-max` / `frontend-design` | UI já está produção-ready; reservar para nova feature. |

---

## Arquivos críticos a serem analisados (referências)

- `hospital-reunioes/backend/app/main.py` — CORS, lifespan, middleware.
- `hospital-reunioes/backend/app/services/importacao_service.py:*` — mudanças no payload.
- `hospital-reunioes/backend/app/models/admin_schemas.py:*` — campos Optional.
- `hospital-reunioes/backend/app/core/config.py` — env vars + validações Pydantic.
- `hospital-reunioes/frontend/src/middleware.ts` — auth + rotas protegidas.
- `hospital-reunioes/frontend/src/app/admin/usuarios/page.tsx` — 810 linhas, 4 mudanças recentes.
- `hospital-reunioes/frontend/src/app/reunioes/page.tsx` — paginação nova.
- `hospital-reunioes/frontend/src/app/reunioes/[id]/page.tsx` — 2086 linhas (foco em mudanças, não no arquivo todo).
- `hospital-reunioes/frontend/src/app/pendencias/page.tsx` — `limit: 200` no fetch.
- `hospital-reunioes/frontend/src/components/configuracoes/UsersSection.tsx`
- `hospital-reunioes/frontend/src/components/layout/Sidebar.tsx` — link `/participantes` removido.
- `.github/workflows/ci.yml` — adicionar `pytest` step.
- `.gitignore` — adicionar `atas-migracao-*.json`.
- `blueprint/DEPLOY.md` — UUIDs do Coolify a preencher.

---

## Verificação (como saber que o pente fino terminou)

Pente fino conclui quando:

1. ✅ Working tree limpo ou com commits temáticos prontos.
2. ✅ 4 relatórios `.md` lidos (`revisao-code.md`, `revisao-simplify.md`, `revisao-seguranca.md`, `revisao-ui.md`) e:
   - Todos os achados **BLOCKER/MAJOR** aplicados ou explicitamente declinados (com nota).
   - Achados **MINOR/NIT** mais relevantes aplicados; resto vira backlog.
3. ✅ CI atualizado (`.github/workflows/ci.yml` com `pytest`) e PR de teste local passa:
   ```bash
   cd hospital-reunioes/backend && uv run ruff check . && uv run ruff format --check . && uv run pytest --maxfail=3 -q
   cd hospital-reunioes/frontend && pnpm lint && pnpm exec tsc --noEmit
   ```
4. ✅ `blueprint/DEPLOY.md` com 4 UUIDs preenchidos (não mais `<preencher>`).
5. ✅ Hook post-commit ativo (`git config --get core.hooksPath` = `.githooks`).
6. ✅ `/deploy` rodado, gates verdes, backend `/api/health` 200, frontend home carrega, `status` e `historico` atualizados em `DEPLOY.md`.

Após o ship, recomendo deletar os 4 arquivos `revisao-*.md` (já estão fora do git pela regra `/*.md`).

---

## Próximos passos depois do primeiro deploy (backlog)

Não fazem parte deste pente fino, mas devem ser registrados via `/gsd-add-backlog`:

1. Setup Vitest + Testing Library no frontend (5-8 testes-chave).
2. Coverage threshold no pytest (`--cov-fail-under=70` por exemplo).
3. Refactor de `frontend/src/app/reunioes/[id]/page.tsx` (2086 linhas, candidato a quebra em sub-componentes).
4. Rate limiting em endpoints públicos (`/api/auth/*`, `/api/signup/*`).
5. Adicionar `prettier` no frontend para padronizar formato.
6. Monitoramento pós-deploy: Sentry ou equivalente para erros de produção.
