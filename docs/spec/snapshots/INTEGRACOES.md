# INTEGRACOES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-10-05T20:08-0300 -->

Serviços externos usados pelo Hospital Reuniões. Secrets configurados no Coolify (não no git).

## OpenRouter
**Pra que serve:** LLM único — atas, correções, extração e transcrição via openai/gpt-5.4-mini (configurável via LLM_MODEL)
**Secret/env primária:** `OPENROUTER_API_KEY`

## ClickSign
**Pra que serve:** Assinatura digital de atas (sandbox em dev, app em prod)
**Secret/env primária:** `CLICKSIGN_API_KEY`
**Variáveis relacionadas:** `CLICKSIGN_BASE_URL`, `CLICKSIGN_WEBHOOK_SECRET`

## Resend
**Pra que serve:** Emails transacionais e SMTP do Supabase Auth
**Secret/env primária:** `RESEND_API_KEY`
**Variáveis relacionadas:** `RESEND_FROM_EMAIL`, `RESEND_INBOUND_API_KEY`, `RESEND_INBOUND_BASE_URL`, `RESEND_WEBHOOK_SECRET`

## Fireflies
**Pra que serve:** Sync de transcrições via webhook
**Secret/env primária:** `FIREFLIES_API_KEY`

---
**Resumo:** 4 integrações externas.
