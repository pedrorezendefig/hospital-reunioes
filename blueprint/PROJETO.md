# Hospital Reuniões

> Atualizado em 2026-04-27 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `mala-ia.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.mala-ia.cloud | 🟢 healthy | 85f7f88 · 27/04 |
| frontend | app.mala-ia.cloud | 🟢 healthy | 85f7f88 · 27/04 |
| supabase | studio.mala-ia.cloud | 🟢 healthy | — · 27/04 |

## Variáveis críticas

**backend** (FastAPI):
- ✅ ENVIRONMENT=`production`
- ✅ DEBUG=`false`
- ✅ ENABLE_BYPASS_ENDPOINTS=`false`
- ✅ CLICKSIGN_BASE_URL=`https://app.clicksign.com`
- ✅ SUPABASE_URL (presente)
- ✅ SUPABASE_SERVICE_ROLE_KEY (presente)
- ✅ SUPABASE_ANON_KEY (presente)
- ✅ OPENAI_API_KEY (presente)
- ✅ CLICKSIGN_API_KEY (presente)
- ✅ CLICKSIGN_WEBHOOK_SECRET (presente, auto-gerado)
- ✅ RESEND_API_KEY (presente)
- ✅ RESEND_FROM_EMAIL (presente)
- ✅ SIGNUP_ENCRYPTION_KEY (presente, auto-gerado)
- ✅ SIGNUP_PASSE (presente, auto-gerado)

**frontend** (Next.js, build-time):
- ✅ NEXT_PUBLIC_SUPABASE_URL (presente)
- ✅ NEXT_PUBLIC_SUPABASE_ANON_KEY (presente)
- ✅ NEXT_PUBLIC_API_URL (presente)
- ✅ NEXT_PUBLIC_ENVIRONMENT (presente)

**supabase** (mailer/SMTP — 16 vars):
- ✅ Todas as 16 presentes (GOTRUE_SITE_URL, ADDITIONAL_REDIRECT_URLS, API_EXTERNAL_URL, SMTP_*, MAILER_*)

## Integrações externas

- 🟢 **OpenAI** — Transcrição de áudio e geração de ata via gpt-4o-mini (via `OPENAI_API_KEY`)
- 🟢 **ClickSign** — Assinatura digital de atas (sandbox em dev, app em prod) (via `CLICKSIGN_API_KEY`)
- 🟢 **Resend** — Emails transacionais e SMTP do Supabase Auth (via `RESEND_API_KEY`)
- 🟢 **Fireflies** — Sync de transcrições via webhook (via `FIREFLIES_API_KEY`)

## Próximas ações & alertas

- ✅ Tudo verde — Deploy 890b149 saudável (frontend 2m43s, backend 1m14s após retry OOM)
- 🔵 Validar PDF de ATA com nova tipografia HP Simplified e paleta DESIGN.md (#2B2E7E)
- 🔵 Aplicar revisão ortográfica em massa no Supabase remoto via planos/sql/revisao-ortografica-20260427.sql
- 🟡 Ajustar `expected_body_regex` em project.json (regex desatualizada vs `/api/health` real)

## Stack

- **Backend**: FastAPI (Python 3.12) + uv + Uvicorn
- **Frontend**: Next.js 15 (App Router) + pnpm
- **Database**: Supabase self-hosted
- **Infra**: Coolify em VPS Hostinger 16GB + Traefik/Let's Encrypt
- **Pdf**: WeasyPrint + Jinja2

## Coolify

- **VPS**: 31.97.29.32 (Hostinger 16GB)
- **Painel**: https://coolify.mala-ia.cloud
- **Domínio raiz**: mala-ia.cloud
- **UUIDs**: project=`gvkd16jzoq8dzlpep2txqgo3`, server=`uy6j3f0nmevsvwkknmmpfgqc`, github_app=`r10gjb55dd6zamdx0vquuau4`

## Histórico recente

**Últimos 5 deploys** (de `history.json` — sem campos voláteis tipo build_duration_seconds):

- 27/04 `85f7f88` — Migra blueprint para PROJETO.md (skill /blueprint global) — 🟢 healthy → [implementacoes/2026-04-27-1952-85f7f88-healthy.md](implementacoes/2026-04-27-1952-85f7f88-healthy.md)
- 27/04 `890b149` — Data-fix: revisão ortográfica em massa replicada em PROD (147 UPDATEs) — 🟢 healthy
- 27/04 `890b149` — PDF de ATA com fonte HP Simplified e paleta refinada + revisão ortográfica do banco — 🟢 healthy
- 27/04 `d36f1de` — Lote de melhorias: transcrição multi-formato, drop coluna `local`, filtro por facilitador — 🟢 healthy
- 25/04 `9d0d198` — Remoção do auto-cadastro via passe + PWA mobile no app — 🟢 healthy

**Commits do mês**: ver [`historico/2026-04.md`](historico/2026-04.md)

## Como mexer

- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos

- [`planos/plano-26-04-27-1929h-revisao-ortografica-banco.md`](../planos/plano-26-04-27-1929h-revisao-ortografica-banco.md) — Revisão ortográfica em massa do banco
- [`planos/plano-26-04-27-1730h-skill-blueprint-md.md`](../planos/plano-26-04-27-1730h-skill-blueprint-md.md) — Skill `/blueprint` global (substitui `/blueprint-sync`, remove HTML)
- [`planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md`](../planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md) — PDF da ATA com fonte HP Simplified e visual refinado
- [`planos/plano-26-04-27-0506h-filtro-por-facilitador.md`](../planos/plano-26-04-27-0506h-filtro-por-facilitador.md) — Filtro por Facilitador (Calendário, Pendências Lista e Kanban)
- [`planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md`](../planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md) — Bordas menos arredondadas — sistema todo
- [`planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md`](../planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md) — Reversão completa do agente Ana (versão beta sem resquício)
- [`planos/plano-26-04-27-0227h-redesign-lista-pendencias.md`](../planos/plano-26-04-27-0227h-redesign-lista-pendencias.md) — Redesign da lista de Ações/Tarefas (Pendências)
- [`planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md`](../planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md) — Remover campo "Local" e renomear "Objetivo" → "Pauta" (só UI)
- [`planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md`](../planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md) — Calendário como página única de Reuniões + Transcrição multi-formato
- [`planos/plano-26-04-25-0210h-template-email-pt-br.md`](../planos/plano-26-04-25-0210h-template-email-pt-br.md) — Email de auth em produção — template pt-BR servido pelo frontend
