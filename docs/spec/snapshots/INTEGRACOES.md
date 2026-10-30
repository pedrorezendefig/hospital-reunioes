# INTEGRACOES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-10-30T17:07+0000 -->

Serviços externos usados pelo Hospital Reuniões. Secrets configurados no Coolify (não no git).

## Anthropic
**Pra que serve:** IA de texto do app inteiro desde a issue #1302 (Atas, POP, Ouvidoria, Assistente de Tecnologia, Contas médicas), pelo LLM_MODEL e pelos CM_IA_MODELO_PASSO_A/B, todos claude-sonnet-5-5. Retenção padrão da API (até 30 dias, sem treino), sem ZDR (ADR 0074)
**Onde aparece no código:** `app/services/ai_processor.py`, `app/services/contas_medicas/ia.py`
**Secret/env primária:** `ANTHROPIC_API_KEY`

## OpenRouter
**Pra que serve:** Só a transcrição de voz, pelo TRANSCRICAO_MODEL (default: openai/gpt-4o-mini-transcribe)
**Onde aparece no código:** `app/services/transcricao_service.py`
**Secret/env primária:** `OPENROUTER_API_KEY`

## ClickSign
**Pra que serve:** Assinatura digital de atas (sandbox em dev, app em prod)
**Onde aparece no código:** `app/routers/pops/revisao.py`, `app/routers/pops/assinatura.py`, `app/routers/admin/legacy.py`
**Secret/env primária:** `CLICKSIGN_API_KEY`
**Variáveis relacionadas:** `CLICKSIGN_BASE_URL`, `CLICKSIGN_WEBHOOK_SECRET`

## Resend
**Pra que serve:** Emails transacionais e SMTP do Supabase Auth
**Onde aparece no código:** `app/config.py`, `app/services/tecnologia_email.py`, `app/services/email_service.py`
**Secret/env primária:** `RESEND_API_KEY`
**Variáveis relacionadas:** `RESEND_FROM_EMAIL`, `RESEND_INBOUND_API_KEY`, `RESEND_INBOUND_BASE_URL`, `RESEND_WEBHOOK_SECRET`

## Fireflies
**Pra que serve:** Sync de transcrições via webhook
**Onde aparece no código:** `app/routers/admin/legacy.py`, `app/config.py`
**Secret/env primária:** `FIREFLIES_API_KEY`

---
**Resumo:** 5 integrações externas.
