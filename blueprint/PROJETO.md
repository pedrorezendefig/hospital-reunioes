# Hospital Reuniões

> Atualizado em 2026-05-11 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.hospitalsaomatheus.cloud | 🟢 healthy | c64f290 · 11/05 |
| frontend | app.hospitalsaomatheus.cloud | 🟢 healthy | c64f290 · 11/05 |
| supabase | studio.hospitalsaomatheus.cloud | 🟢 healthy | c64f290 · 27/04 |

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
- ✅ NEXT_PUBLIC_SUPABASE_URL (presente)
- ✅ NEXT_PUBLIC_SUPABASE_ANON_KEY (presente)
- ✅ NEXT_PUBLIC_API_URL (presente)
- ✅ NEXT_PUBLIC_ENVIRONMENT (presente)

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
- ✅ Deploy c64f290 saudável — Limpeza de código morto: removidos 6 componentes duplicados em src/components/reunioes/, 10 unused imports/vars no frontend, função is_super_user deprecated e schema RegistrarParticipanteRequest no backend, 3 testes manuais legados da raiz do backend. Build backend 42s, frontend 127s. Health: api 200 em 1530ms, app 200 em 1621ms.
- 🔵 Limpar SIGNUP_* obsoletas em produção (Coolify) — SIGNUP_ENCRYPTION_KEY e SIGNUP_PASSE seguem cadastradas no backend em produção, mas a aplicação não usa mais (removidas do Settings via migration 031 e do .env.example agora). Pode deletar pelo painel do Coolify para reduzir superfície de secrets. Também vale tirar do project.json (runtime_required + secrets_auto_generated).
- 🔵 Validar PDF de ATA com nova tipografia e paleta — Gerar uma ATA assinada e conferir HP Simplified + paleta navy (#2B2E7E) no PDF. Bloqueio nenhum, só checkpoint visual depois do redesign.
- 🔵 Revisão ortográfica em massa via SQL — Aplicar planos/sql/revisao-ortografica-20260427.sql no Supabase remoto quando puder agendar janela curta.

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

- 11/05 `c64f290` — Limpeza de código morto (frontend + backend) e arquivos órfãos da raiz — 🟢 healthy → [`mudancas/🟢-2026-05-11-1522-c64f290-remove-codigo-morto-unused-imports-e-arquivos.md`](mudancas/🟢-2026-05-11-1522-c64f290-remove-codigo-morto-unused-imports-e-arquivos.md)
- 11/05 `09d948b` — Chat de correção colapsável, refresh automático após aplicar e remoção da seção  — 🟢 healthy → [`mudancas/🟢-2026-05-11-1226-09d948b-ata-chat-correcao-colapsavel-refresh-automatico-e.md`](mudancas/🟢-2026-05-11-1226-09d948b-ata-chat-correcao-colapsavel-refresh-automatico-e.md)
- 08/05 `44c53c8` — Super admin troca facilitador da reunião por outro super admin. — 🟢 healthy → [`mudancas/🟢-2026-05-08-1635-44c53c8-reunioes-super-admin-troca-facilitador-da-reuniao.md`](mudancas/🟢-2026-05-08-1635-44c53c8-reunioes-super-admin-troca-facilitador-da-reuniao.md)
- 08/05 `c5abfde` — Sidebar com Calendário top-level e Importar ATA embaixo do Admin. — 🟢 healthy → [`mudancas/🟢-2026-05-08-1622-c5abfde-frontend-calendario-direto-importar-ata-no-admin.md`](mudancas/🟢-2026-05-08-1622-c5abfde-frontend-calendario-direto-importar-ata-no-admin.md)
- 08/05 `04ece04` — Combobox de cargo/setor agora mostra todas as opções ao abrir o dropdown. — 🟢 healthy → [`mudancas/🟢-2026-05-08-0938-04ece04-frontend-cargo-setor-mostram-todas-opcoes-ao-abrir.md`](mudancas/🟢-2026-05-08-0938-04ece04-frontend-cargo-setor-mostram-todas-opcoes-ao-abrir.md)

**Commits do mês**: nenhum agregado ainda — rode `/blueprint historico`

## Como mexer

- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos

- [`mudancas/🟡-2026-05-11-1530-blueprint-mudancas-com-cores.md`](mudancas/🟡-2026-05-11-1530-blueprint-mudancas-com-cores.md) — Plano: Unificar blueprint/mudancas/ com cores 🟡 / 🟢 / 🔴
- [`mudancas/🟡-2026-05-08-0203-redesign-proposta-pj.md`](mudancas/🟡-2026-05-08-0203-redesign-proposta-pj.md) — Redesign da proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`mudancas/🟡-2026-05-01-1939-skill-clone-banco-sql.md`](mudancas/🟡-2026-05-01-1939-skill-clone-banco-sql.md) — Plano — Refatorar /clone-banco para gerar SQLs numerados (clone manual assistido)
- [`mudancas/🟡-2026-04-29-0327-proposta-pj-hospital-sao-mateus.md`](mudancas/🟡-2026-04-29-0327-proposta-pj-hospital-sao-mateus.md) — Proposta PJ — Pedro Figueiredo × Hospital São Mateus
- [`mudancas/🟡-2026-04-28-1230-clonagem-banco-vps-novo.md`](mudancas/🟡-2026-04-28-1230-clonagem-banco-vps-novo.md) — Plano — Cópia rápida do banco de produção para VPS novo
- [`mudancas/🟡-2026-04-29-1515-migracao-openrouter-gpt54mini.md`](mudancas/🟡-2026-04-29-1515-migracao-openrouter-gpt54mini.md) — Migração de LLM: OpenAI direto → OpenRouter (gpt-5.4-mini), com OpenAI como fallback
- [`mudancas/🟡-2026-04-27-1800-pdf-fonte-hp-simplified.md`](mudancas/🟡-2026-04-27-1800-pdf-fonte-hp-simplified.md) — Plano — PDF da ATA com fonte HP Simplified e visual refinado
- [`mudancas/🟡-2026-04-27-0506-filtro-por-facilitador.md`](mudancas/🟡-2026-04-27-0506-filtro-por-facilitador.md) — Plano — Filtro por Facilitador (Calendário, Pendências Lista e Kanban)
- [`mudancas/🟡-2026-04-27-0503-bordas-menos-arredondadas.md`](mudancas/🟡-2026-04-27-0503-bordas-menos-arredondadas.md) — Bordas menos arredondadas — sistema todo
- [`mudancas/🟡-2026-04-27-0437-reversao-ana-versao-beta-limpa.md`](mudancas/🟡-2026-04-27-0437-reversao-ana-versao-beta-limpa.md) — Plano — Reversão completa do agente Ana (versão beta sem resquício)
