# Deploy `2c95e23` — 🟢 healthy

- **Data**: 2026-05-08 04:35 -0300
- **SHA**: `2c95e23`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Ajustes no chat de correção (preserva plano entre turnos) + limpeza de tabelas órfãs.

## Serviços tocados

- backend
- frontend

## Migrations aplicadas

- `034_drop_facilitador_prompts.sql`

## Notas

Chat de correção agora preserva plano entre turnos via current_plan + fallback OpenAI direto se OpenRouter falhar. Migration 034 dropa tabelas experimentais facilitador_prompts e facilitador_prompt_versoes. Health pós: api 200 67ms, app 200 305ms. Backend 28s, frontend 92s.

---
_Gerado pelo `/deploy ship`._
