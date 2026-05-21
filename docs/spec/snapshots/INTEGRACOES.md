# INTEGRACOES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T20:24-0300 -->

Serviços externos usados pelo Hospital Reuniões. Secrets configurados no Coolify (não no git).

## OpenRouter
**Pra que serve:** LLM primário — geração de ata e correções via openai/gpt-5.4-mini (configurável via LLM_MODEL)
**Onde aparece no código:** `app/services/ai_processor.py`
**Secret/env primária:** `OPENROUTER_API_KEY`

## OpenAI
**Pra que serve:** Fallback automático se OpenRouter indisponível — usa LLM_FALLBACK_MODEL (gpt-4o-mini)
**Onde aparece no código:** `app/services/ai_processor.py`
**Secret/env primária:** `OPENAI_API_KEY`

## ClickSign
**Pra que serve:** Assinatura digital de atas (sandbox em dev, app em prod)
**Onde aparece no código:** `app/routers/importacao.py`, `app/routers/admin/legacy.py`, `app/routers/webhooks.py`
**Secret/env primária:** `CLICKSIGN_API_KEY`
**Variáveis relacionadas:** `CLICKSIGN_BASE_URL`, `CLICKSIGN_WEBHOOK_SECRET`

## Resend
**Pra que serve:** Emails transacionais e SMTP do Supabase Auth
**Onde aparece no código:** `app/services/email_service.py`
**Secret/env primária:** `RESEND_API_KEY`
**Variáveis relacionadas:** `RESEND_FROM_EMAIL`

## Fireflies
**Pra que serve:** Sync de transcrições via webhook
**Onde aparece no código:** `app/routers/admin/legacy.py`, `app/config.py`
**Secret/env primária:** `FIREFLIES_API_KEY`

---
**Resumo:** 5 integrações externas.
