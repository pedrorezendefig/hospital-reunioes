# ESTRUTURA.md
<!-- parcialmente gerado por /snapshot — blocos <!-- curated:start --> são humanos -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Visão geral das pastas do projeto Hospital Reuniões. Top-level apenas — pra detalhe, abra o código.

## Backend (FastAPI · Python 3.12 · uv · Uvicorn)

Localização: `hospital-reunioes/backend/`

```
app/
├── routers/         # endpoints HTTP — 1 arquivo por área (auth, participantes, reunioes, pendencias, comentarios, notificacoes, configuracoes, perfil, importacao, webhooks, health, admin/*)
├── services/        # lógica de negócio (audit_log, email, notificacao, auth_provisioning, cargo_mapping)
├── models/          # schemas Pydantic (schemas.py, admin_schemas.py)
├── pipeline/        # pipeline de IA (transcrição → resumo → ata → correção)
├── middleware/      # middleware ASGI (auth, request logging, request_id)
├── cron/            # jobs agendados (lembrete_24h, alerta_prazo, reprocessamento)
├── scripts/         # utilities (importação legada, backfill, scripts pontuais)
├── utils/           # helpers (parsing de query params, PostgREST filters)
├── prompts/         # templates de prompt pra IA (correção, extração)
├── static/          # assets estáticos
├── templates/       # templates de email
├── dependencies.py  # dependências FastAPI (auth, supabase client, RLS helpers)
├── config.py        # Settings (env vars validadas via Pydantic)
├── limiter.py       # rate limiting (slowapi)
└── main.py          # FastAPI app entry point + CORS + middleware setup
tests/               # pytest (test_admin_usuarios, test_pipeline, etc)
```

<!-- curated:start -->
**Notas humanas:**
- A pasta `pipeline/` é o coração: pega áudio/transcrição, passa por LLM em N etapas (extração de fala → resumo → estruturação em JSON → geração de ata em PT → revisão), e cospe `json_ata` que é renderizado como PDF via WeasyPrint.
- `routers/admin/` exige `is_super_admin=true` no JWT — apenas Pedro hoje, mas o middleware suporta múltiplos super admins.
- `cron/lembrete_24h.py` roda a cada hora, busca reuniões com `data` exatamente 24h no futuro e `lembrete_24h_enviado=false`.
- `cron/alerta_prazo.py` roda diariamente; marca pendências vencidas como `ATRASADO` e notifica responsável + facilitador.
- `config.py:validate_debug_prod()` é um **hard-fail**: se `DEBUG=true` chegar em produção, o container não sobe.
- `main.py` tem CORS travado no domínio do frontend (`app.hospitalsaomatheus.cloud`, via `frontend_url`) + `localhost:3000` em dev. O gate `cors_audit` no `project.json` impede regressão.
<!-- curated:end -->

## Frontend (Next.js 15 App Router · pnpm · TypeScript)

Localização: `hospital-reunioes/frontend/`

```
src/
├── app/             # App Router (layout.tsx, page.tsx, auth/, dashboard/, admin/, reunioes/, pendencias/)
├── components/      # UI reutilizável (kanban, tables, forms, modals, calendar, navbar, footer)
├── hooks/           # custom hooks (useUser, usePendencias, useNotificacoes, useReunioes)
├── lib/             # utilities (api client com TanStack Query, formatting, validation, supabase client)
├── types/           # TypeScript types (User, Reuniao, Pendencia, Notificacao — espelham backend schemas)
└── constants/       # constantes (cargo_mapping, setor_mapping, status_labels, role_labels)
public/              # assets estáticos (logos, favicon, fontes)
```

<!-- curated:start -->
**Notas humanas:**
- Stack: **shadcn/ui** + **Tailwind CSS** + **Zustand** (estado global) + **TanStack Query** (HTTP + cache).
- Páginas principais: `/dashboard` (kanban de pendências por status), `/reunioes` (calendário + lista), `/admin/usuarios` (CRUD super_admin), `/perfil` (stats pessoais).
- Variáveis `NEXT_PUBLIC_*` viram build args do Docker — declaradas em `project.json.services[].build.build_args_from_env_keys`.
- Fonte tipográfica: **HP Simplified** (variável CSS `--font-hp`), paleta primária `#2B2E7E` (indigo escuro).
- App é SPA-like dentro do Next: maioria das rotas são client-rendered, só `/login` é SSR.
<!-- curated:end -->

## Supabase (self-hosted · PostgreSQL 15)

Localização: `hospital-reunioes/supabase/`

```
supabase/
├── migrations/      # 38 SQL files (ordem cronológica 001-038)
├── functions/       # Edge Functions (se houver — atualmente vazio ou raro)
├── templates/       # HTML de email (recovery, confirmation, magic_link, invite)
└── snippets/        # SQL helpers/snippets
```

<!-- curated:start -->
**Notas humanas:**
- Auth: tabela `auth.users` é gerenciada pelo próprio Supabase, referenciada por `participantes.auth_user_id` (FK).
- RLS habilitada em todas as tabelas operacionais (migration 009). Backend usa `SERVICE_ROLE_KEY` pra bypass e aplica controle de acesso na camada de aplicação.
- Storage: 3 buckets — `audios`, `transcricoes`, `atas-pdf` (migration 006). URLs públicas assinadas via Supabase SDK.
- SMTP do Auth: usa Resend via variáveis `SMTP_HOST=smtp.resend.com`, `SMTP_PORT=465`, `SMTP_USER=resend`, `SMTP_PASSWORD=<RESEND_API_KEY>`.
- Templates de email do Auth são HTML hospedados em URLs externas, referenciados por `MAILER_TEMPLATES_*` env vars.
<!-- curated:end -->

## Infraestrutura

Localização: raiz do repo + Coolify (`coolify.mala-ia.cloud`)

```
Dockerfile           # backend (multi-stage uv → uvicorn)
Dockerfile.frontend  # frontend (multi-stage pnpm build → Next standalone)
docker-compose.yml   # ambiente local (backend + frontend + supabase + traefik)
.github/workflows/   # CI (lint backend + frontend, type check, build)
docs/spec/           # spec viva (este arquivo, deploy/, snapshots/, CHANGELOG)
.claude/skills/      # skills locais do time (/grill-with-docs, /to-prd, /to-issues, /pegar-issue, /tdd, /ship, /deploy, /snapshot, /atualizar-app)
```

<!-- curated:start -->
**Notas humanas:**
- Produção: 3 containers no Coolify (backend porta 8000, frontend porta 3000, supabase stack inteira).
- Domínios: `app.hospitalsaomatheus.cloud` (frontend), `api.hospitalsaomatheus.cloud` (backend), `studio.hospitalsaomatheus.cloud` (Supabase Studio).
- VPS: Hostinger 16GB com Coolify gerenciando Docker + Traefik (TLS automático via Let's Encrypt).
- Deploy é triggered por push no `main` via GitHub App do Coolify (UUID em `project.json`).
- `docker-compose.yml` na raiz é só pra dev local (não é usado em produção). Em produção, cada service é app/serviço independente no Coolify.
<!-- curated:end -->

## Docs e o que fica fora do git (ADR 0044)

```
CONTEXT.md / CONTEXT-MAP.md   # glossários (Reuniões; mapa Reuniões × POPs × Ouvidoria)
docs/adr/                     # decisões (consuma só status: accepted)
docs/agents/                  # protocolo do agente (issue tracker, labels, domínio)
docs/onboarding/              # setup de máquina e fluxo do dia a dia
docs/spec/                    # deploy/*.json, snapshots/, CHANGELOG, VERSIONING
docs/pops/                    # glossário POPs + materiais reais de referência
docs/comunicacao/             # material do diretor: percepcao/ (vídeos), divulgacao/ (Vercel), _assets/ (fonte + logo únicos)
docs/manual/                  # manual do usuário (Vercel)
local/                        # FORA DO GIT: PDFs, transcrições, rascunhos, dumps (cada máquina cria a sua)
tokens/.env                   # FORA DO GIT: chaves da máquina (molde em tokens/.env.example)
```

---

**Resumo:** 1 monorepo · 3 services em produção (backend FastAPI, frontend Next.js, Supabase stack) · ~90 endpoints · 14 tabelas operacionais · 6 integrações externas.

**Pra começar a desenvolver localmente:** ver `docs/onboarding/dev.md`.
