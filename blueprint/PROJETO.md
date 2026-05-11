# Hospital Reuniões

> Atualizado em 2026-05-11 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.hospitalsaomatheus.cloud | 🟢 healthy | 09d948b · 11/05 |
| frontend | app.hospitalsaomatheus.cloud | 🟢 healthy | 09d948b · 11/05 |
| supabase | studio.hospitalsaomatheus.cloud | 🟢 healthy | — |

## Variáveis críticas

**backend** (fastapi):
- ✅ ENVIRONMENT (presente)
- ✅ DEBUG (presente)
- ✅ SUPABASE_URL (presente)
- ✅ SUPABASE_SERVICE_ROLE_KEY (presente)
- ✅ SUPABASE_ANON_KEY (presente)
- ✅ OPENROUTER_API_KEY (presente)
- ✅ LLM_MODEL (presente)
- ✅ OPENAI_API_KEY (presente)
- ✅ LLM_FALLBACK_MODEL (presente)
- ✅ CLICKSIGN_API_KEY (presente)
- ✅ CLICKSIGN_BASE_URL (presente)
- ✅ CLICKSIGN_WEBHOOK_SECRET (presente)
- ✅ RESEND_API_KEY (presente)
- ✅ RESEND_FROM_EMAIL (presente)
- ✅ SIGNUP_ENCRYPTION_KEY (presente)
- ✅ SIGNUP_PASSE (presente)
- ✅ ENABLE_BYPASS_ENDPOINTS (presente)

**frontend** (nextjs):
- 🟡 NEXT_PUBLIC_SUPABASE_URL (presente, mas sem flag is_build_time)
- 🟡 NEXT_PUBLIC_SUPABASE_ANON_KEY (presente, mas sem flag is_build_time)
- 🟡 NEXT_PUBLIC_API_URL (presente, mas sem flag is_build_time)
- 🟡 NEXT_PUBLIC_ENVIRONMENT (presente, mas sem flag is_build_time)

**supabase** (supabase):
- ✅ GOTRUE_SITE_URL (presente)
- ✅ ADDITIONAL_REDIRECT_URLS (presente)
- ✅ API_EXTERNAL_URL (presente)
- ✅ SMTP_HOST (presente)
- ✅ SMTP_PORT (presente)
- ✅ SMTP_USER (presente)
- ✅ SMTP_ADMIN_EMAIL (presente)
- ✅ SMTP_SENDER_NAME (presente)
- ✅ MAILER_TEMPLATES_RECOVERY (presente)
- ✅ MAILER_TEMPLATES_CONFIRMATION (presente)
- ✅ MAILER_TEMPLATES_MAGIC_LINK (presente)
- ✅ MAILER_TEMPLATES_INVITE (presente)
- ✅ MAILER_SUBJECTS_RECOVERY (presente)
- ✅ MAILER_SUBJECTS_CONFIRMATION (presente)
- ✅ MAILER_SUBJECTS_MAGIC_LINK (presente)
- ✅ MAILER_SUBJECTS_INVITE (presente)

## Integrações externas

- 🟢 OpenRouter — LLM primário — geração de ata e correções via openai/gpt-5.4-mini (configurável via LLM_MODEL) (via `OPENROUTER_API_KEY`)
- 🟢 OpenAI — Fallback automático se OpenRouter indisponível — usa LLM_FALLBACK_MODEL (gpt-4o-mini) (via `OPENAI_API_KEY`)
- 🟢 ClickSign — Assinatura digital de atas (sandbox em dev, app em prod) (via `CLICKSIGN_API_KEY`)
- 🟢 Resend — Emails transacionais e SMTP do Supabase Auth (via `RESEND_API_KEY`)
- 🟢 Fireflies — Sync de transcrições via webhook (via `FIREFLIES_API_KEY`)

## Próximas ações & alertas

- ✅ Tudo verde — Deploy 890b149 saudável (frontend 2m43s, backend 1m14s após retry OOM)
- 🔵 Validar PDF de ATA com nova tipografia HP Simplified e paleta DESIGN.md (#2B2E7E)
- 🔵 Aplicar revisão ortográfica em massa no Supabase remoto via planos/sql/revisao-ortografica-20260427.sql
- 🟡 Ajustar expected_body_regex em project.json (regex desatualizada vs /api/health real)
- ✅ Bugfixes no fluxo de correção de ATA: chat com painel de correções pendentes colapsável, refresh automático após aplicar correção (sem reload manual), polling de status reduzido de 15s pra 4s, e remoção total da seção 'Referências externas mencionadas' (UI, PDF e prompts da IA). Health: api 200 1134ms, app 200 122ms.
- 🔵 Abrir uma ATA em AGUARDANDO_VALIDACAO, entrar em modo correção, empilhar 5+ apontamentos e confirmar que o painel começa colapsado e o botão verde de aplicar fica sempre visível. Em seguida, aplicar uma correção e confirmar que a página entra em PROCESSANDO e volta pra AGUARDANDO_VALIDACAO sozinha em ~4-5s após a IA terminar.
- 🟡 Faltando: API_PREFIX, APP_NAME, APP_VERSION, OPENROUTER_BASE_URL. Sobrando: SIGNUP_ENCRYPTION_KEY, SIGNUP_PASSE (existem no Settings via Field). Cosmético: não bloqueia deploy mas deixa exemplo desatualizado.
- 🟡 diagnose_app reporta is_build_time=false nas 4 NEXT_PUBLIC_* do frontend. Build funciona via Dockerfile ARG. Fix: marcar via mcp__coolify__bulk_env_update.
- 🟡 project.json espera ^{"status":"ok"}$ mas /api/health retorna {"status":"healthy",...}. Body_ok continua true (regex no script é diferente do project.json).

## Stack

- **Backend**: FastAPI (Python 3.12) + uv + Uvicorn
- **Frontend**: Next.js 15 (App Router) + pnpm
- **Database**: Supabase self-hosted
- **Infra**: Coolify em VPS Hostinger 16GB + Traefik/Let's Encrypt
- **Pdf**: WeasyPrint + Jinja2

## Coolify

- **VPS**: 31.97.29.32 (Hostinger 16GB)
- **Painel**: https://coolify.hospitalsaomatheus.cloud
- **Domínio raiz**: hospitalsaomatheus.cloud
- **UUIDs**: project=`gvkd16jzoq8dzlpep2txqgo3`, server=`uy6j3f0nmevsvwkknmmpfgqc`, github_app=`r10gjb55dd6zamdx0vquuau4`

## Histórico recente

**Últimos 5 deploys** (de `history.json`):

- 11/05 `09d948b` — Chat de correção colapsável, refresh automático após aplicar e remoção da seção 'Referências externa — 🟢 healthy
- 08/05 `44c53c8` — Super admin troca facilitador da reunião por outro super admin. — 🟢 healthy
- 08/05 `c5abfde` — Sidebar com Calendário top-level e Importar ATA embaixo do Admin. — 🟢 healthy
- 08/05 `04ece04` — Combobox de cargo/setor agora mostra todas as opções ao abrir o dropdown. — 🟢 healthy
- 08/05 `2c95e23` — Ajustes no chat de correção (preserva plano entre turnos) + limpeza de tabelas órfãs. — 🟢 healthy

**Commits do mês**: nenhum agregado ainda — rode `/blueprint historico`

## Como mexer

- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos

- [`planos/plano-26-05-08-0203h-redesign-proposta-pj.md`](planos/plano-26-05-08-0203h-redesign-proposta-pj.md) — Redesign da proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`planos/plano-26-05-01-1939h-skill-clone-banco-sql.md`](planos/plano-26-05-01-1939h-skill-clone-banco-sql.md) — Plano — Refatorar /clone-banco para gerar SQLs numerados (clone manual assistido)
- [`planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md`](planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md) — Proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md`](planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md) — Plano — Cópia rápida do banco de produção para VPS novo
- [`planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md`](planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md) — Migração de LLM: OpenAI direto → OpenRouter (gpt-5.4-mini), com OpenAI como fallback
- [`planos/plano-26-04-27-1929h-revisao-ortografica-banco.md`](planos/plano-26-04-27-1929h-revisao-ortografica-banco.md) — Plano — Revisão ortográfica em massa do banco (Hospital Reuniões)
- [`planos/plano-26-04-27-1730h-skill-blueprint-md.md`](planos/plano-26-04-27-1730h-skill-blueprint-md.md) — Skill `/blueprint` global (substitui `/blueprint-sync`, remove HTML)
- [`planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md`](planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md) — Plano — PDF da ATA com fonte HP Simplified e visual refinado
- [`planos/plano-26-04-27-0506h-filtro-por-facilitador.md`](planos/plano-26-04-27-0506h-filtro-por-facilitador.md) — Plano — Filtro por Facilitador (Calendário, Pendências Lista e Kanban)
- [`planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md`](planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md) — Bordas menos arredondadas — sistema todo
