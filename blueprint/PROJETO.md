# Hospital Reuniões

> Atualizado em 2026-05-08 — Regere com `/blueprint update`

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação → transcrição por IA → geração de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam — só recebem emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.hospitalsaomatheus.cloud | 🟢 healthy | 2c95e23 · 08/05 |
| frontend | app.hospitalsaomatheus.cloud | 🟢 healthy | 2c95e23 · 08/05 |
| supabase | studio.hospitalsaomatheus.cloud | 🟢 healthy | 2c95e23 · 27/04 |

## Variáveis críticas

**backend** (fastapi):
- ⚪ {'name': 'ENVIRONMENT', 'purpose': 'Modo de execução (production / development)'} (não verificado)
- ⚪ {'name': 'DEBUG', 'purpose': 'Liga CORS aberto e API docs (false em produção)'} (não verificado)
- ⚪ {'name': 'SUPABASE_URL', 'purpose': 'Endpoint do Postgres/Auth do Supabase'} (não verificado)
- ⚪ {'name': 'SUPABASE_SERVICE_ROLE_KEY', 'purpose': 'Chave admin do Supabase (bypass RLS, server-side)'} (não verificado)
- ⚪ {'name': 'SUPABASE_ANON_KEY', 'purpose': 'Chave pública do Supabase (uso em redirects/auth)'} (não verificado)
- ⚪ {'name': 'OPENROUTER_API_KEY', 'purpose': 'Chave do OpenRouter (LLM primário)'} (não verificado)
- ⚪ {'name': 'LLM_MODEL', 'purpose': 'Modelo LLM via OpenRouter (default: openai/gpt-5.4-mini)'} (não verificado)
- ⚪ {'name': 'OPENAI_API_KEY', 'purpose': 'Fallback OpenAI direto se OpenRouter indisponível'} (não verificado)
- ⚪ {'name': 'LLM_FALLBACK_MODEL', 'purpose': 'Modelo no caminho fallback OpenAI (default: gpt-4o-mini)'} (não verificado)
- ⚪ {'name': 'CLICKSIGN_API_KEY', 'purpose': 'Token da ClickSign para assinatura digital de atas'} (não verificado)
- ⚪ {'name': 'CLICKSIGN_BASE_URL', 'purpose': 'URL base da ClickSign (sandbox em dev, app em prod)'} (não verificado)
- ⚪ {'name': 'CLICKSIGN_WEBHOOK_SECRET', 'purpose': 'HMAC que valida callbacks de assinatura ClickSign'} (não verificado)
- ⚪ {'name': 'RESEND_API_KEY', 'purpose': 'Chave do Resend para emails transacionais'} (não verificado)
- ⚪ {'name': 'RESEND_FROM_EMAIL', 'purpose': 'Endereço remetente padrão (noreply@…)'} (não verificado)
- ⚪ {'name': 'SIGNUP_ENCRYPTION_KEY', 'purpose': 'Fernet key para criptografar dados sensíveis no signup'} (não verificado)
- ⚪ {'name': 'SIGNUP_PASSE', 'purpose': 'Senha extra exigida no fluxo de cadastro inicial'} (não verificado)
- ⚪ {'name': 'ENABLE_BYPASS_ENDPOINTS', 'purpose': 'Liga endpoints de debug (deve ser false em produção)'} (não verificado)

**supabase** (supabase):
- ⚪ {'name': 'GOTRUE_SITE_URL', 'purpose': 'URL do app usada pelo Auth para gerar redirects'} (não verificado)
- ⚪ {'name': 'ADDITIONAL_REDIRECT_URLS', 'purpose': 'Redirects válidos pós-login (recovery, callback)'} (não verificado)
- ⚪ {'name': 'API_EXTERNAL_URL', 'purpose': 'URL pública do Studio/PostgREST exposta ao Auth'} (não verificado)
- ⚪ {'name': 'SMTP_HOST', 'purpose': 'Host SMTP usado pelo Supabase (smtp.resend.com)'} (não verificado)
- ⚪ {'name': 'SMTP_PORT', 'purpose': 'Porta SMTP (465 com SSL)'} (não verificado)
- ⚪ {'name': 'SMTP_USER', 'purpose': 'Usuário SMTP (resend)'} (não verificado)
- ⚪ {'name': 'SMTP_ADMIN_EMAIL', 'purpose': 'Remetente técnico (noreply@hospitalsaomatheus.cloud)'} (não verificado)
- ⚪ {'name': 'SMTP_SENDER_NAME', 'purpose': 'Nome humano que aparece como remetente nos emails'} (não verificado)
- ⚪ {'name': 'MAILER_TEMPLATES_RECOVERY', 'purpose': 'URL do template HTML de recuperação de senha'} (não verificado)
- ⚪ {'name': 'MAILER_TEMPLATES_CONFIRMATION', 'purpose': 'URL do template HTML de confirmação de email'} (não verificado)
- ⚪ {'name': 'MAILER_TEMPLATES_MAGIC_LINK', 'purpose': 'URL do template HTML do magic link'} (não verificado)
- ⚪ {'name': 'MAILER_TEMPLATES_INVITE', 'purpose': 'URL do template HTML de convite'} (não verificado)
- ⚪ {'name': 'MAILER_SUBJECTS_RECOVERY', 'purpose': 'Assunto do email de recuperação de senha'} (não verificado)
- ⚪ {'name': 'MAILER_SUBJECTS_CONFIRMATION', 'purpose': 'Assunto do email de confirmação'} (não verificado)
- ⚪ {'name': 'MAILER_SUBJECTS_MAGIC_LINK', 'purpose': 'Assunto do email com magic link'} (não verificado)
- ⚪ {'name': 'MAILER_SUBJECTS_INVITE', 'purpose': 'Assunto do email de convite'} (não verificado)

## Integrações externas

- 🟢 OpenRouter — LLM primário — geração de ata e correções via openai/gpt-5.4-mini (configurável via LLM_MODEL) (via `OPENROUTER_API_KEY`)
- 🟢 OpenAI — Fallback automático se OpenRouter indisponível — usa LLM_FALLBACK_MODEL (gpt-4o-mini) (via `OPENAI_API_KEY`)
- 🟢 ClickSign — Assinatura digital de atas (sandbox em dev, app em prod) (via `CLICKSIGN_API_KEY`)
- 🟢 Resend — Emails transacionais e SMTP do Supabase Auth (via `RESEND_API_KEY`)
- 🟢 Fireflies — Sync de transcrições via webhook (via `FIREFLIES_API_KEY`)

## Próximas ações & alertas

- 🔵 Tudo verde — Deploy 890b149 saudável (frontend 2m43s, backend 1m14s após retry OOM)
- 🔵 Validar PDF de ATA com nova tipografia HP Simplified e paleta DESIGN.md (#2B2E7E)
- 🔵 Aplicar revisão ortográfica em massa no Supabase remoto via planos/sql/revisao-ortografica-20260427.sql
- 🔵 Ajustar expected_body_regex em project.json (regex desatualizada vs /api/health real)
- 🟡 **Token Coolify revogado** — MCP do Coolify retornou 401 Unauthenticated. Pedro precisa gerar novo token em https://coolify.mala-ia.cloud/security/api-tokens e atualizar via 'claude mcp remove coolify -s user && claude mcp add coolify -s user -- npx -y @masonator/coolify-mcp -e COOLIFY_ACCESS_TOKEN=<novo> -e COOLIFY_BASE_URL=https://coolify.mala-ia.cloud'.
- 🟡 **CI vermelho por motivos não bloqueantes** — Backend pytest falha porque Settings exige SUPABASE_URL/SERVICE_ROLE_KEY (precisa conftest.py mockando ou secrets no Actions). Frontend lint falha porque .github/workflows/ci.yml usa node-version: 20 + pnpm latest (pnpm 11+ requer node 22.13+). Não bloqueia deploy real (Coolify usa Dockerfile, alinhado com node:22-alpine + pnpm@9).
- 🔵 **DNS coolify.hospitalsaomatheus.cloud não criado** — UI do Coolify continua acessível em https://coolify.mala-ia.cloud (DNS legado ainda resolve no IP 31.97.29.32). Se quiser migrar painel também, criar registro A coolify.hospitalsaomatheus.cloud → 31.97.29.32.
- 🟡 **expected_body_regex desatualizado** — project.json espera ^{"status":"ok"}$ mas /api/health retorna {"status":"healthy",...}. Body OK na prática, mas regex precisa ser ajustada.

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

- 08/05 `2c95e23` — Ajustes no chat de correção (preserva plano entre turnos) + limpeza de tabelas órfãs. — 🟢 healthy
- 08/05 `7457c69` — Aplica ruff format em pdf_generator.py + ship dos 5 commits da migração de domínio. — 🟢 healthy
- 01/05 `3c627ee` — Migra LLM de OpenAI direto para OpenRouter (gpt-5.4-mini). — 🟢 healthy
- 27/04 `85f7f88` — Migra blueprint para PROJETO.md (skill /blueprint global) — 🟢 healthy
- 27/04 `890b149` — Data-fix: revisão ortográfica em massa replicada em PROD (147 UPDATEs). — 🟢 healthy

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
