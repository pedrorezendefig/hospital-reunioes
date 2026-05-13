# Hospital Reuniões

> Atualizado em 2026-05-13 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.hospitalsaomatheus.cloud | 🟢 healthy | c64f290 · 11/05 |
| frontend | app.hospitalsaomatheus.cloud | 🟢 healthy | ef704d9 · 12/05 |
| supabase | studio.hospitalsaomatheus.cloud | 🟢 healthy | ef704d9 · 27/04 |

## Variáveis críticas

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
- 🔵 Auditoria de tipagem TypeScript (P0). Sincroniza UserRole (adiciona 'presidente' faltante no @/types), remove 3 `any` explícitos, substitui 4 `reuniao!` por guards e cria lib/errors.ts com getErrorMessage(unknown) consolidando 6 catches. Type-check `tsc --noEmit` limpo, lint sem regressões. Build frontend 170s; backend não tocado. Relatório completo em blueprint/mudancas/.
- 🔵 P1 (~1h total): tipar funções de status (getStatusColor, getStatusColorWeek, formatStatus) no calendario, tipar KpiDefinition em KpiCards, deletar isSuperUser deprecated, documentar interface vs type, padronizar opcional vs nullable. P2 (refactor maior): discriminated union para Reuniao, Zod nas boundaries, codegen via openapi-typescript, ativar noUncheckedIndexedAccess. Detalhes no relatório.
- 🔵 SIGNUP_ENCRYPTION_KEY e SIGNUP_PASSE seguem cadastradas no backend em produção, mas a aplicação não usa mais (removidas do Settings via migration 031 e do .env.example). Pode deletar pelo painel do Coolify para reduzir superfície de secrets. Também vale tirar do project.json (runtime_required + secrets_auto_generated).
- 🔵 Gerar uma ATA assinada e conferir HP Simplified + paleta navy (#2B2E7E) no PDF.
- 🔵 Aplicar planos/sql/revisao-ortografica-20260427.sql no Supabase remoto quando puder agendar janela curta.

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

- 12/05 `ef704d9` — Auditoria de tipagem TypeScript (P0): sincroniza UserRole, remove any explícito  — 🟢 healthy
- 11/05 `c64f290` — Limpeza de código morto (frontend + backend) e arquivos órfãos da raiz — 🟢 healthy → [`mudancas/🟢-2026-05-11-1522-c64f290-remove-codigo-morto-unused-imports-e-arquivos.md`](mudancas/🟢-2026-05-11-1522-c64f290-remove-codigo-morto-unused-imports-e-arquivos.md)
- 11/05 `09d948b` — Chat de correção colapsável, refresh automático após aplicar e remoção da seção  — 🟢 healthy → [`mudancas/🟢-2026-05-11-1226-09d948b-ata-chat-correcao-colapsavel-refresh-automatico-e.md`](mudancas/🟢-2026-05-11-1226-09d948b-ata-chat-correcao-colapsavel-refresh-automatico-e.md)
- 08/05 `44c53c8` — Super admin troca facilitador da reunião por outro super admin. — 🟢 healthy → [`mudancas/🟢-2026-05-08-1635-44c53c8-reunioes-super-admin-troca-facilitador-da-reuniao.md`](mudancas/🟢-2026-05-08-1635-44c53c8-reunioes-super-admin-troca-facilitador-da-reuniao.md)
- 08/05 `c5abfde` — Sidebar com Calendário top-level e Importar ATA embaixo do Admin. — 🟢 healthy → [`mudancas/🟢-2026-05-08-1622-c5abfde-frontend-calendario-direto-importar-ata-no-admin.md`](mudancas/🟢-2026-05-08-1622-c5abfde-frontend-calendario-direto-importar-ata-no-admin.md)

**Commits do mês**: nenhum agregado ainda — rode `/blueprint historico`

## Como mexer

- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos

- [`mudancas/🟡-2026-05-12-2323-auditoria-tipagem-typescript.md`](mudancas/🟡-2026-05-12-2323-auditoria-tipagem-typescript.md) — Plano: Auditoria de tipagem TypeScript do frontend
- [`mudancas/🟡-2026-05-11-1530-blueprint-mudancas-com-cores.md`](mudancas/🟡-2026-05-11-1530-blueprint-mudancas-com-cores.md) — Plano: Unificar blueprint/mudancas/ com cores 🟡 / 🟢 / 🔴
