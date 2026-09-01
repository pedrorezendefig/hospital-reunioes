# INTEGRACOES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-09-01T01:09-0300 -->

Serviços externos usados pelo Hospital Reuniões. Secrets configurados no Coolify (não no git).

## OpenRouter
**Pra que serve:** LLM único — atas, correções, extração e transcrição via openai/gpt-5.4-mini (configurável via LLM_MODEL)
**Onde aparece no código:** `app/services/ai_processor.py`, `app/services/transcricao_service.py`
**Secret/env primária:** `OPENROUTER_API_KEY`

## ClickSign
**Pra que serve:** Assinatura digital de atas (sandbox em dev, app em prod)
**Onde aparece no código:** `app/routers/pops/assinatura.py`, `app/routers/pops/revisao.py`, `app/routers/admin/legacy.py`
**Secret/env primária:** `CLICKSIGN_API_KEY`
**Variáveis relacionadas:** `CLICKSIGN_BASE_URL`, `CLICKSIGN_WEBHOOK_SECRET`

## Resend
**Pra que serve:** Emails transacionais e SMTP do Supabase Auth
**Onde aparece no código:** `app/config.py`, `app/services/email_service.py`
**Secret/env primária:** `RESEND_API_KEY`
**Variáveis relacionadas:** `RESEND_FROM_EMAIL`

## Fireflies
**Pra que serve:** Sync de transcrições via webhook
**Onde aparece no código:** `app/routers/admin/legacy.py`, `app/config.py`
**Secret/env primária:** `FIREFLIES_API_KEY`

---
**Resumo:** 4 integrações externas.
