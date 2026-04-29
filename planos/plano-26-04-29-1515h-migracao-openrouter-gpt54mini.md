# Migração de LLM: OpenAI direto → OpenRouter (gpt-5.4-mini), com OpenAI como fallback

## Context

**Estado atual descoberto:**
- Pedro **já tem `OPENROUTER_API_KEY` configurada** em `hospital-reunioes/.env`, mas o backend **nunca lê essa variável**.
- O backend hoje só usa OpenAI direto: `OpenAI(api_key=settings.openai_api_key)` apontando para `api.openai.com`, com modelo `gpt-4o-mini`.
- São **4 chamadas LLM**, todas centralizadas em `hospital-reunioes/backend/app/services/ai_processor.py`:
  - `process_transcricao` (l. 89, 121) — extrai JSON estruturado da transcrição
  - `process_ata_migrada` (l. 186, 201) — normaliza ATAs antigas migradas
  - `process_correcao` (l. 334, 347) — aplica correção em ata gerada
  - `chat_correcao` (l. 382, 400) — chat leve de correção
- Há também 1 log com texto literal `"Modelo: gpt-4o-mini"` em `app/pipeline/orchestrator.py`.
- Não há outras chamadas LLM em `scripts/` nem em outros módulos do backend; o frontend não tem SDK de IA.

**Resposta direta à pergunta do Pedro:**
> "Verifica se eu já estou usando OpenRouter."

**Não.** A `OPENROUTER_API_KEY` está no `.env`, mas o código nunca a referencia. O sistema chama OpenAI direto.

**Decisões alinhadas com o usuário:**
1. **Manter `OPENAI_API_KEY` como fallback opcional** — se OpenRouter cair ou a chave não estiver setada, o sistema usa OpenAI direto com `gpt-4o-mini`. Sem fallback, qualquer indisponibilidade do OpenRouter quebra o pipeline.
2. **Modelo configurável via env** — `LLM_MODEL=openai/gpt-5.4-mini` para OpenRouter, `LLM_FALLBACK_MODEL=gpt-4o-mini` para OpenAI direto.

**Outcome esperado:** todas as 4 chamadas LLM passam por OpenRouter usando `openai/gpt-5.4-mini` por padrão; se `OPENROUTER_API_KEY` estiver vazia, cai para OpenAI direto com `gpt-4o-mini`; se ambas vazias, modo mock para dev.

---

## Plano

### 1. Config — `hospital-reunioes/backend/app/config.py`

Substituir o bloco `# OpenAI` (linhas 27-28) por:

```python
# LLM (OpenRouter primário, OpenAI direto como fallback)
openrouter_api_key: str = ""
openrouter_base_url: str = "https://openrouter.ai/api/v1"
llm_model: str = "openai/gpt-5.4-mini"  # usado quando OpenRouter está ativo
openai_api_key: str = ""  # fallback se OpenRouter indisponível
llm_fallback_model: str = "gpt-4o-mini"  # usado no fallback OpenAI direto
```

### 2. Helpers de cliente LLM — `hospital-reunioes/backend/app/services/ai_processor.py`

Adicionar no topo do arquivo (após imports):

```python
_OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://hospitalsaomatheus.com.br",
    "X-Title": "Hospital Reuniões",
}


def _llm_provider() -> str:
    """Retorna 'openrouter', 'openai' ou 'mock' conforme chaves disponíveis."""
    if settings.openrouter_api_key and settings.openrouter_api_key != "your-openrouter-key":
        return "openrouter"
    if settings.openai_api_key and settings.openai_api_key != "your-openai-key":
        return "openai"
    return "mock"


def _get_llm() -> tuple[OpenAI, str, dict]:
    """Retorna (client, model, extra_kwargs) conforme provedor ativo.

    OpenRouter é primário. OpenAI direto é fallback. Caller decide o que fazer
    em modo mock chamando _llm_provider() == 'mock' antes.
    """
    provider = _llm_provider()
    if provider == "openrouter":
        client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        return client, settings.llm_model, {"extra_headers": _OPENROUTER_HEADERS}
    # provider == "openai" (fallback)
    client = OpenAI(api_key=settings.openai_api_key)
    return client, settings.llm_fallback_model, {}
```

Em cada uma das 4 funções (`process_transcricao`, `process_ata_migrada`, `process_correcao`, `chat_correcao`):

- Substituir o check inicial `if not settings.openai_api_key or settings.openai_api_key == "your-openai-key":` por:
  ```python
  if _llm_provider() == "mock":
      logger.warning("Nenhuma chave LLM configurada — ativando modo mock")
      return _mock_ata(...)  # ou retorno equivalente em cada função
  ```
- Substituir `client = OpenAI(api_key=settings.openai_api_key)` por:
  ```python
  client, model, extra = _get_llm()
  ```
- Substituir `model="gpt-4o-mini"` por `model=model`.
- Adicionar `**extra` na chamada `client.chat.completions.create(...)` para injetar `extra_headers` quando OpenRouter.
- Atualizar o log mascarado de chave (linhas 86-87 e 183-184): mostrar `provider` (openrouter/openai) junto, ex.:
  ```python
  provider = _llm_provider()
  key_used = settings.openrouter_api_key if provider == "openrouter" else settings.openai_api_key
  masked = f"{key_used[:8]}...{key_used[-4:]}"
  logger.info(f"Chamando LLM via {provider} (modelo={model}, chave={masked})")
  ```
- Atualizar logs literais `"OpenAI processou"`, `"chamar OpenAI"` (linhas 146, 154, 222, 232, 358, 411) para `"LLM"` ou `f"{provider}"` neutro.
- Atualizar mensagem mock em `_mock_ata_migrada` linha 295: trocar `"Executar a importação com OPENAI_API_KEY configurada"` por `"Executar a importação com OPENROUTER_API_KEY (ou OPENAI_API_KEY) configurada"`.

### 3. Log do pipeline — `hospital-reunioes/backend/app/pipeline/orchestrator.py`

Trocar string literal `"[Pipeline][Step 2] Enviando transcricao para a OpenAI (Modelo: gpt-4o-mini)"` por algo dinâmico que reflete provedor + modelo. Ex.: importar `_llm_provider`/`_get_llm` ou simplesmente:

```python
logger.info(f"[Pipeline][Step 2] Enviando transcricao para LLM (modelo configurado: {settings.llm_model})")
```

### 4. `.env` files

**`hospital-reunioes/.env`** (manual, fora do git):
- Manter `OPENAI_API_KEY=...` (fallback)
- Confirmar `OPENROUTER_API_KEY=...` (primário)
- Adicionar `LLM_MODEL=openai/gpt-5.4-mini`
- Adicionar `LLM_FALLBACK_MODEL=gpt-4o-mini` (opcional — já tem default no config)

**`hospital-reunioes/.env.example`** e **`hospital-reunioes/backend/.env.example`**:
- Adicionar:
  ```
  # LLM (OpenRouter primário; OpenAI como fallback)
  OPENROUTER_API_KEY=your-openrouter-key
  LLM_MODEL=openai/gpt-5.4-mini
  OPENAI_API_KEY=  # opcional, usado se OpenRouter indisponível
  LLM_FALLBACK_MODEL=gpt-4o-mini
  ```

### 5. Testes — `hospital-reunioes/backend/tests/test_ai_processor_ata_migrada.py`

Verificar se o teste hoje monkey-patcha `settings.openai_api_key` para forçar mocks. Se sim, manter compat: o teste pode setar tanto `openrouter_api_key` quanto `openai_api_key`. Se houver fixture específica, ajustar. O `MagicMock()` do `client.chat.completions.create` continua válido.

### 6. Coolify (produção) — manual antes do ship

Pedro precisa, na UI do Coolify (ou via blueprint), **antes** de rodar `/deploy ship`:
- Adicionar `OPENROUTER_API_KEY=<chave-real>`
- Adicionar `LLM_MODEL=openai/gpt-5.4-mini`
- **Manter `OPENAI_API_KEY`** (continua válida como fallback)

Se OPENROUTER_API_KEY não for adicionada no Coolify, o backend de produção segue funcionando com OpenAI direto + gpt-4o-mini (estado atual). Sem risco de quebra no boot.

### 7. Blueprint do projeto

Atualizar `blueprint/deploy/project.json` para refletir nova integração:
- Em `integrations`, registrar `openrouter` (primário, modelo `openai/gpt-5.4-mini`)
- Manter `openai` listada como fallback

(O `/blueprint update` automático após o `/deploy ship` regenera `PROJETO.md` a partir disso.)

---

## Arquivos críticos a modificar

| Arquivo | Mudança |
|---|---|
| `hospital-reunioes/backend/app/config.py` | adicionar `openrouter_api_key`, `openrouter_base_url`, `llm_model`, `llm_fallback_model`; manter `openai_api_key` |
| `hospital-reunioes/backend/app/services/ai_processor.py` | adicionar `_llm_provider()` + `_get_llm()`; substituir 4 chamadas |
| `hospital-reunioes/backend/app/pipeline/orchestrator.py` | atualizar string de log |
| `hospital-reunioes/.env` | adicionar OPENROUTER_API_KEY (já presente) + LLM_MODEL; manter OPENAI_API_KEY |
| `hospital-reunioes/.env.example` | adicionar bloco LLM |
| `hospital-reunioes/backend/.env.example` | adicionar bloco LLM |
| `hospital-reunioes/backend/tests/test_ai_processor_ata_migrada.py` | ajuste se houver referência direta a `openai_api_key` (provavelmente não) |
| `blueprint/deploy/project.json` | adicionar OpenRouter em integrations, marcar OpenAI como fallback |

---

## Verificação end-to-end

### Local (dev) — caminho OpenRouter

1. `/atualizar-app` — rebuild da stack docker-compose com o código novo.
2. `docker compose logs -f backend | grep -i "llm\|openrouter\|gpt-5"` — confirmar boot sem erro.
3. **Smoke test pipeline normal:** subir uma transcrição de teste pela UI em `localhost:3000` e checar:
   - Log do orchestrator mostra `"modelo configurado: openai/gpt-5.4-mini"`
   - Log do `ai_processor` mostra `"Chamando LLM via openrouter"`
   - JSON estruturado volta com 6 seções HSM válidas
   - PDF gerado é coerente com transcrição
4. **Smoke test correção:** abrir uma ata e enviar instrução de correção via chat — verificar resposta.
5. **Smoke test ATA migrada:** rodar `/migrar-atas` em modo dry-run com 1 PDF — confirmar que IA responde via OpenRouter.
6. `cd hospital-reunioes/backend && pytest tests/test_ai_processor_ata_migrada.py -v` — verde.
7. **Audit (opcional):** confirmar no painel da OpenRouter que houve consumo da chave e do modelo `openai/gpt-5.4-mini`.

### Local (dev) — caminho fallback OpenAI

8. Esvaziar `OPENROUTER_API_KEY` no `.env` (ou comentar a linha) → `/atualizar-app` → repetir smoke test 3.
9. Confirmar log: `"Chamando LLM via openai"` e `"modelo=gpt-4o-mini"`. Pipeline segue funcional.
10. Restaurar `OPENROUTER_API_KEY` no `.env`.

### Produção

11. Atualizar variáveis no Coolify (passo 6 acima).
12. `/deploy ship` — promove para prod.
13. Subir 1 reunião real pelo app de produção e validar a ATA gerada.

---

## Riscos e ressalvas

- **Custo ~5× maior:** `gpt-5.4-mini` é $0,75/M input + $4,50/M output, contra ~$0,15/$0,60 do `gpt-4o-mini`. Pedro precisa ter ciência. Volume hoje é baixo, então o impacto absoluto deve ser pequeno.
- **Variação de output:** prompts foram calibrados em `gpt-4o-mini`. Modelo novo pode gerar JSON com estilo ligeiramente diferente. Por isso o smoke test E2E acima é crítico.
- **JSON mode:** OpenRouter suporta `response_format={"type": "json_object"}` para modelos OpenAI; nada muda aí.
- **Fallback automático "silencioso":** se `OPENROUTER_API_KEY` for esvaziada por engano em prod, o sistema cai para OpenAI direto sem alarme. Mitigação: log explícito `"Chamando LLM via openai"` no boot do primeiro request — se vir isso em prod sem ter mexido, é sinal de incidente.
- **Modo mock continua útil:** sem nenhuma chave, dev local segue funcionando com fixtures fake.

---

## Após aprovação

Mover este arquivo para o repo conforme regra global do CLAUDE.md:

```bash
mkdir -p planos
mv ~/.claude/plans/image-1-tenho-uma-hazy-dolphin.md \
   planos/plano-26-04-29-HHMMh-migracao-openrouter-gpt54mini.md
```

(timestamp da última atualização no nome do arquivo).

## Execução / Resultados

**Executado em 2026-04-29 às 15:15h** (uma sessão).

### Mudanças aplicadas

- `hospital-reunioes/backend/app/config.py` — adicionados `openrouter_api_key`, `openrouter_base_url`, `llm_model` (default `openai/gpt-5.4-mini`), `llm_fallback_model` (default `gpt-4o-mini`); `openai_api_key` mantido como fallback.
- `hospital-reunioes/backend/app/services/ai_processor.py` — adicionados helpers `_llm_provider()`, `_get_llm()`, `_log_llm_call()`. Substituídas as 4 chamadas (`process_transcricao`, `process_ata_migrada`, `process_correcao`, `chat_correcao`). Logs atualizados de "OpenAI" para "LLM ({provider})".
- `hospital-reunioes/backend/app/pipeline/orchestrator.py` — log do Step 2 agora usa `settings.llm_model` dinamicamente.
- `hospital-reunioes/.env` — `LLM_MODEL=openai/gpt-5.4-mini` adicionado; bloco renomeado para "LLM (OpenRouter primário)".
- `hospital-reunioes/.env.example` e `hospital-reunioes/backend/.env.example` — refletem a nova convenção.
- `hospital-reunioes/backend/tests/test_ai_processor_ata_migrada.py` — testes ajustados para mockar tanto `openrouter_api_key` quanto `openai_api_key`; teste do caminho feliz renomeado para `test_process_chama_llm_via_openrouter_quando_key_presente`.
- `blueprint/deploy/project.json` — OpenRouter listado como primário; OpenAI marcada como fallback; novas envs `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL` em `runtime_required`.

### Verificação

- **pytest:** 168/168 verdes (`hospital-reunioes/backend && pytest`).
- **Sanity de import:** `from app.services import ai_processor` ok, helpers expostos.
- **`/atualizar-app`:** rebuild da stack em 6s, healthcheck backend 200, frontend 200.
- **Smoke E2E real:**
  ```
  Provider chamado: openrouter
  Modelo retornado: openai/gpt-5.4-mini-20260317
  Resposta: 'OK'
  Tokens: prompt=12 completion=5
  ```
  Roteado pelo OpenRouter para o provider Azure. Confirma que `OPENROUTER_API_KEY`, `LLM_MODEL`, `base_url` e `extra_headers` estão funcionando.

### Bug colateral encontrado e corrigido

- O header `X-Title="Hospital Reuniões"` quebrava com `UnicodeEncodeError` porque o `httpx` (via OpenAI SDK) força ASCII em headers HTTP. Corrigido para `"Hospital Reunioes"` (só identificação interna no painel da OpenRouter, sem impacto funcional).

### Pendente — manual

1. **Smoke test pela UI** — Pedro deve subir uma transcrição de teste em `localhost:3000`, conferir que a ATA é gerada corretamente com `gpt-5.4-mini` (modelo novo, prompts foram afinados em `gpt-4o-mini` — atenção a variações sutis de output).
2. **Coolify (produção)** — antes de `/deploy ship`:
   - Adicionar `OPENROUTER_API_KEY=<chave-real>` na app backend
   - Adicionar `LLM_MODEL=openai/gpt-5.4-mini`
   - Manter `OPENAI_API_KEY` (fallback)
3. **Commit** — todas as mudanças seguem unstaged. Pedro decide se quer commitar/PR ou continuar testando antes.

### Observação de custo

`openai/gpt-5.4-mini` é ~5× mais caro que `gpt-4o-mini` ($0,75/M input + $4,50/M output vs ~$0,15/$0,60). Volume hoje é baixo, então o impacto absoluto deve ser pequeno, mas vale acompanhar nas primeiras semanas.
