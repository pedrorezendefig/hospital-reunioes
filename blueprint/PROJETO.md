# Hospital Reuniões

> Atualizado em 2026-05-11 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | https://api.hospitalsaomatheus.cloud | 🟢 healthy | `c64f290` · 11/05 |
| frontend | https://app.hospitalsaomatheus.cloud | 🟢 healthy | `c64f290` · 11/05 |
| supabase | https://studio.hospitalsaomatheus.cloud | 🟢 healthy | `—` · 27/04 |

## Variáveis críticas

**backend** (17 required, 0 faltando):
- ✅ `ENVIRONMENT`
- ✅ `DEBUG`
- ✅ `SUPABASE_URL`
- ✅ `SUPABASE_SERVICE_ROLE_KEY`
- ✅ `SUPABASE_ANON_KEY`
- ✅ `OPENROUTER_API_KEY`
- ✅ `LLM_MODEL`
- ✅ `OPENAI_API_KEY`
- ✅ `LLM_FALLBACK_MODEL`
- ✅ `CLICKSIGN_API_KEY`
- ✅ `CLICKSIGN_BASE_URL`
- ✅ `CLICKSIGN_WEBHOOK_SECRET`
- ✅ `RESEND_API_KEY`
- ✅ `RESEND_FROM_EMAIL`
- ✅ `SIGNUP_ENCRYPTION_KEY`
- ✅ `SIGNUP_PASSE`
- ✅ `ENABLE_BYPASS_ENDPOINTS`

**frontend** (4 build-time):
- ✅ `NEXT_PUBLIC_SUPABASE_URL` (build-time)
- ✅ `NEXT_PUBLIC_SUPABASE_ANON_KEY` (build-time)
- ✅ `NEXT_PUBLIC_API_URL` (build-time)
- ✅ `NEXT_PUBLIC_ENVIRONMENT` (build-time)

**supabase** (16 mailer keys configuradas):
- ✅ presentes via `mcp__coolify__env_vars`

## Integrações externas

- 🟢 **OpenRouter** — LLM primário — geração de ata e correções via openai/gpt-5.4-mini (configurável via LLM_MODEL) (via `OPENROUTER_API_KEY`)
- 🟢 **OpenAI** — Fallback automático se OpenRouter indisponível — usa LLM_FALLBACK_MODEL (gpt-4o-mini) (via `OPENAI_API_KEY`)
- 🟢 **ClickSign** — Assinatura digital de atas (sandbox em dev, app em prod) (via `CLICKSIGN_API_KEY`)
- 🟢 **Resend** — Emails transacionais e SMTP do Supabase Auth (via `RESEND_API_KEY`)
- 🟢 **Fireflies** — Sync de transcrições via webhook (via `FIREFLIES_API_KEY`)

## Próximas ações & alertas

- ✅ Tudo verde — Deploy 890b149 saudável (frontend 2m43s, backend 1m14s após retry OOM)
- 🔵 Validar PDF de ATA com nova tipografia HP Simplified e paleta DESIGN.md (#2B2E7E)
- 🔵 Aplicar revisão ortográfica em massa no Supabase remoto via planos/sql/revisao-ortografica-20260427.sql
- 🟡 Ajustar expected_body_regex em project.json (regex desatualizada vs /api/health real)
- ✅ **Deploy c64f290 saudável** — Limpeza de código morto: removidos 6 componentes duplicados em src/components/reunioes/, 10 unused imports/vars no frontend, função is_super_user deprecated e schema RegistrarParticipanteRequest no backend, 3 testes manuais legados da raiz do backend. Build backend 42s, frontend 127s. Health: api 200 em 1530ms, app 200 em 1621ms.
- 🔵 **Limpar SIGNUP_* obsoletas em produção (Coolify)** — SIGNUP_ENCRYPTION_KEY e SIGNUP_PASSE seguem cadastradas no backend em produção, mas a aplicação não usa mais (removidas do Settings via migration 031 e do .env.example agora). Pode deletar pelo painel do Coolify para reduzir superfície de secrets. Também vale tirar do project.json (runtime_required + secrets_auto_generated).
- 🔵 **Validar PDF de ATA com nova tipografia e paleta** — Gerar uma ATA assinada e conferir HP Simplified + paleta navy (#2B2E7E) no PDF. Bloqueio nenhum, só checkpoint visual depois do redesign.
- 🔵 **Revisão ortográfica em massa via SQL** — Aplicar planos/sql/revisao-ortografica-20260427.sql no Supabase remoto quando puder agendar janela curta.

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

- 11/05 `c64f290` — Limpeza de código morto (frontend + backend) e arquivos órfãos da raiz — 🟢 healthy
- 11/05 `09d948b` — Chat de correção colapsável, refresh automático após aplicar e remoção da seção 'Referênci — 🟢 healthy
- 08/05 `44c53c8` — Super admin troca facilitador da reunião por outro super admin. — 🟢 healthy
- 08/05 `c5abfde` — Sidebar com Calendário top-level e Importar ATA embaixo do Admin. — 🟢 healthy
- 08/05 `04ece04` — Combobox de cargo/setor agora mostra todas as opções ao abrir o dropdown. — 🟢 healthy

**Commits do mês**: nenhum agregado ainda — rode `/blueprint historico`

## Como mexer

- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos

- [`planos/plano-26-05-11-1530h-blueprint-implementacoes-slug-e-ci.md`](planos/plano-26-05-11-1530h-blueprint-implementacoes-slug-e-ci.md) — Plano: Slug nos arquivos de implementação + conserto do CI
- [`planos/plano-26-05-08-0203h-redesign-proposta-pj.md`](planos/plano-26-05-08-0203h-redesign-proposta-pj.md) — Redesign da proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`planos/plano-26-05-01-1939h-skill-clone-banco-sql.md`](planos/plano-26-05-01-1939h-skill-clone-banco-sql.md) — Plano — Refatorar /clone-banco para gerar SQLs numerados (clone manual assistido)
- [`planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md`](planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md) — Proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md`](planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md) — Plano — Cópia rápida do banco de produção para VPS novo
- [`planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md`](planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md) — Migração de LLM: OpenAI direto → OpenRouter (gpt-5.4-mini), com OpenAI como fallback
- [`planos/plano-26-04-27-1929h-revisao-ortografica-banco.md`](planos/plano-26-04-27-1929h-revisao-ortografica-banco.md) — Plano — Revisão ortográfica em massa do banco (Hospital Reuniões)
- [`planos/plano-26-04-27-1730h-skill-blueprint-md.md`](planos/plano-26-04-27-1730h-skill-blueprint-md.md) — Skill `/blueprint` global (substitui `/blueprint-sync`, remove HTML)
- [`planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md`](planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md) — Plano — PDF da ATA com fonte HP Simplified e visual refinado
- [`planos/plano-26-04-27-0506h-filtro-por-facilitador.md`](planos/plano-26-04-27-0506h-filtro-por-facilitador.md) — Plano — Filtro por Facilitador (Calendário, Pendências Lista e Kanban)
