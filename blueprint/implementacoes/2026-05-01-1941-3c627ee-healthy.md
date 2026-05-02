# Deploy `3c627ee`: 🟢 healthy

- **Data**: 2026-05-01 19:41 -03:00
- **SHA**: `3c627ee`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Migra LLM de OpenAI direto para OpenRouter (gpt-5.4-mini).

## Serviços tocados

- backend

## Mudanças de variáveis

- backend: create `OPENROUTER_API_KEY, LLM_MODEL, LLM_FALLBACK_MODEL`

## Notas

OpenRouter passa a ser o provedor primário do LLM (`openai/gpt-5.4-mini`). OpenAI direto continua disponível como fallback automático (`gpt-4o-mini`) quando `OPENROUTER_API_KEY` estiver vazia.

**Validação antes do deploy:**
- 168 testes pytest verdes no backend.
- Smoke E2E real local: `process_transcricao()` chamou OpenRouter com transcrição fictícia; gpt-5.4-mini gerou JSON HSM completo (3 participantes, 3 tópicos de discussão, 2 atribuições com prazos normalizados, divergência capturada).
- `/atualizar-app` validou que a stack docker-compose local roda sem erro.

**Métricas do deploy:**
- Build: 1m53s (113s).
- Health check: HTTP 200, 88ms, body `{"status":"healthy",...}`.
- 3 vars LLM criadas no Coolify via MCP antes do build (uuid backend `jo6zt7h4chu7w38s4ojyuepu`).

**Observação de custo:**
gpt-5.4-mini é cerca de 5x mais caro que gpt-4o-mini (US$0,75/M input + US$4,50/M output vs US$0,15/US$0,60). Volume atual é baixo, mas vale acompanhar consumo no painel da OpenRouter na primeira semana.

**Plano de referência:** `planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md`.

---
_Gerado pelo `/deploy ship` (Passo 9.4)._
