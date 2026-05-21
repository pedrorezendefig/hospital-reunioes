# INTEGRACOES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Serviços externos usados pela aplicação Hospital Reuniões. Variáveis sensíveis configuradas no Coolify (não no git).

## OpenRouter
**Pra que serve:** LLM primário do pipeline de IA — gera a ata estruturada e roda correções iterativas.
**Modelo padrão:** `openai/gpt-5.4-mini` (configurável via `LLM_MODEL`).
**Onde aparece no código:** `app/pipeline/llm_client.py`, `app/pipeline/correcao.py`.
**Secret no Coolify:** `OPENROUTER_API_KEY`.
**Variáveis relacionadas:** `LLM_MODEL`.
**Fallback:** OpenAI (transição automática se OpenRouter responder erro).

## OpenAI
**Pra que serve:** Fallback automático se OpenRouter cair. Usa modelo mais barato (`gpt-4o-mini` por padrão).
**Onde aparece:** `app/pipeline/llm_client.py:fallback_to_openai()`.
**Secret:** `OPENAI_API_KEY`.
**Variáveis:** `LLM_FALLBACK_MODEL`.

## ClickSign
**Pra que serve:** Assinatura digital da ata pelos participantes. Backend envia o PDF preliminar, ClickSign coleta assinaturas por email, e dispara webhook quando todos assinaram.
**Onde aparece no código:** `app/services/clicksign_service.py` (cliente), `app/routers/webhooks.py:POST /webhooks/clicksign` (callback).
**Secret:** `CLICKSIGN_API_KEY`, `CLICKSIGN_WEBHOOK_SECRET` (HMAC).
**Variáveis:** `CLICKSIGN_BASE_URL` — `https://sandbox.clicksign.com` em dev, `https://app.clicksign.com` em prod (gate `prod_only_assertions` no `project.json`).
**Fluxo:** ver `FLUXOGRAMAS.md` > "Assinatura ClickSign".

## Resend
**Pra que serve:** Envio de emails transacionais (notificação de pendência, validação de ata, lembrete 24h) + SMTP do Supabase Auth (recovery, magic link, confirmation, invite).
**Onde aparece no código:** `app/services/email_service.py`, `app/services/reuniao_email_service.py`. Em Supabase, configurado em vars `SMTP_*`.
**Secret:** `RESEND_API_KEY`.
**Variáveis:** `RESEND_FROM_EMAIL` (geralmente `noreply@hospitalsaomatheus.cloud`).
**Templates Supabase:** vivem em URLs externas, configuradas via `MAILER_TEMPLATES_*` (4 templates: recovery, confirmation, magic_link, invite).

## Fireflies
**Pra que serve:** Sync de transcrições de reuniões via webhook. Quando o time grava reunião pelo Fireflies, ele dispara webhook pro backend, que cria reunião no estado PROCESSANDO e roda o pipeline de IA.
**Onde aparece no código:** `app/routers/webhooks.py` (webhook handler).
**Secret:** `FIREFLIES_API_KEY` (autenticação do webhook).
**Variáveis:** —

## Supabase (self-hosted)
**Pra que serve:** Banco Postgres + Auth + Storage. Roda como container no próprio servidor Coolify.
**Onde aparece:** Backend usa `SUPABASE_SERVICE_ROLE_KEY` (bypass RLS) em `app/dependencies.py:get_supabase_client()`. Frontend usa `SUPABASE_ANON_KEY` só pra login (`src/lib/supabase.ts`).
**Secrets:** `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
**Domínio admin:** `https://studio.hospitalsaomatheus.cloud` (Supabase Studio).

## Coolify (PaaS)
**Pra que serve:** Plataforma de deploy. Hospeda 3 services: backend, frontend, supabase. Faz build automático via GitHub App quando há push no main.
**Onde aparece no código:** Não — Coolify é externo. Configuração via UI + via MCP server `mcp__coolify__*` pelo `/deploy`.
**Domínio admin:** `https://coolify.hospitalsaomatheus.cloud`.
**Webhook:** GitHub → Coolify (configurado via GitHub App, UUID em `project.json`).

---

**Notas operacionais:**
- Secrets auto-gerados (3): `SIGNUP_ENCRYPTION_KEY` (Fernet), `CLICKSIGN_WEBHOOK_SECRET` (URL-safe 32 bytes), `SIGNUP_PASSE` (URL-safe 24 bytes). Geração via comando declarado em `project.json.secrets_auto_generated[]`.
- Em produção: `CLICKSIGN_BASE_URL` precisa ser exatamente `https://app.clicksign.com` (gate trava deploy se divergir).
- Variável `ENABLE_BYPASS_ENDPOINTS` precisa ser `false` em produção (gate hard-fail no `config.py`).
- Variável `DEBUG` precisa ser `false` em produção (gate hard-fail).

**Resumo:** 6 integrações externas · 3 secrets auto-gerados · 2 webhooks recebidos (ClickSign, Fireflies) · 1 webhook saindo (GitHub → Coolify).
