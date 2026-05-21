# FLUXOGRAMAS.md
<!-- mantido manualmente — /snapshot só alerta se rota/estado novo apareceu sem fluxo correspondente -->
<!-- last_human_update: 2026-05-21 -->

Diagramas de máquina de estado e fluxos críticos da aplicação Hospital Reuniões. Mermaid renderiza nativo no GitHub e no GitHub Mobile.

## Ciclo de vida de uma Reunião

<!-- curated:start -->
```mermaid
stateDiagram-v2
    [*] --> PROGRAMADA: usuario cria reuniao com data futura
    PROGRAMADA --> PROCESSANDO: anexar-transcricao (manual ou webhook Fireflies)
    PROCESSANDO --> AGUARDANDO_RESOLUCAO: pipeline IA detecta participantes nao reconhecidos
    PROCESSANDO --> AGUARDANDO_VALIDACAO: pipeline IA termina sem ambiguidades
    PROCESSANDO --> ERRO: pipeline IA falha (timeout, LLM down)
    ERRO --> PROCESSANDO: reprocessar (POST /reunioes/{id}/reprocessar)
    AGUARDANDO_RESOLUCAO --> AGUARDANDO_VALIDACAO: resolver-participantes ou pular-resolucao
    AGUARDANDO_VALIDACAO --> CORRIGINDO: chat-correcao (iteracao com IA)
    CORRIGINDO --> AGUARDANDO_VALIDACAO: aplicar correcoes (POST /reunioes/{id}/corrigir)
    AGUARDANDO_VALIDACAO --> AGUARDANDO_ASSINATURA: aprovar (POST /reunioes/{id}/aprovar)
    AGUARDANDO_VALIDACAO --> AGUARDANDO_ASSINATURA: aprovar-bypass (debug, super_admin)
    AGUARDANDO_ASSINATURA --> ASSINADA: webhook ClickSign (todos assinaram)
    AGUARDANDO_ASSINATURA --> CANCELADA: timeout 7 dias sem assinar
    ASSINADA --> [*]
    CANCELADA --> [*]
```

**Estados explicados (para leigo):**
- **PROGRAMADA** — reunião marcada na agenda, ainda não aconteceu (ou aconteceu e ainda não foi processada).
- **PROCESSANDO** — IA está gerando ata a partir da transcrição (~30s a 2min).
- **AGUARDANDO_RESOLUCAO** — IA achou nomes na transcrição que não casam com nenhum participante cadastrado. Pede resolução manual.
- **AGUARDANDO_VALIDACAO** — ata pronta, esperando facilitador conferir e aprovar.
- **CORRIGINDO** — facilitador pediu uma correção via chat. IA reescrevendo.
- **AGUARDANDO_ASSINATURA** — ata aprovada, enviada pra ClickSign, esperando todos assinarem.
- **ASSINADA** — ciclo fechado. PDF assinado disponível.
- **CANCELADA** — abandonada por timeout ou ação manual.
- **ERRO** — falha técnica recuperável via reprocessamento.
<!-- curated:end -->

---

## Ciclo de vida de uma Pendência

<!-- curated:start -->
```mermaid
stateDiagram-v2
    [*] --> PENDENTE: criada quando reuniao vira ASSINADA com acoes
    PENDENTE --> EM_PROGRESSO: responsavel inicia
    PENDENTE --> ATRASADO: passa do prazo sem mexer
    EM_PROGRESSO --> ATRASADO: passa do prazo enquanto em progresso
    EM_PROGRESSO --> CONCLUIDO: responsavel marca como feito
    ATRASADO --> EM_PROGRESSO: responsavel retoma
    ATRASADO --> CONCLUIDO: responsavel marca como feito (atrasado)
    PENDENTE --> REPACTUADA: facilitador remarca prazo
    EM_PROGRESSO --> REPACTUADA: facilitador remarca prazo
    ATRASADO --> REPACTUADA: facilitador remarca prazo (caso mais comum)
    REPACTUADA --> PENDENTE: nova pendencia eh criada (mantem original em historico)
    PENDENTE --> CANCELADO: facilitador cancela
    EM_PROGRESSO --> CANCELADO: facilitador cancela
    CONCLUIDO --> [*]
    CANCELADO --> [*]
```

**Cron jobs envolvidos:**
- `cron/alerta_prazo.py`: roda diariamente, marca como `ATRASADO` quem passou do prazo e notifica responsável + facilitador.
- `cron/notificacao_prazo_proximo.py`: notifica 24h antes do prazo (in-app via `notificacoes`).
<!-- curated:end -->

---

## Assinatura ClickSign (webhook)

<!-- curated:start -->
```mermaid
sequenceDiagram
    participant App as Reuniao (backend)
    participant CS as ClickSign API
    participant P as Participante (email)
    participant WH as Webhook (/webhooks/clicksign)
    participant DB as Postgres
    participant R as Resend (email)

    App->>CS: POST /api/v1/envelopes (PDF + lista de signatarios)
    CS-->>App: envelope_key
    App->>DB: UPDATE reunioes SET envelope_key_clicksign, status=AGUARDANDO_ASSINATURA
    CS->>P: email com link para assinar
    P->>CS: assina via web (drag-drop signature)
    CS->>WH: POST com event=auto_close (HMAC signed)
    WH->>WH: valida HMAC com CLICKSIGN_WEBHOOK_SECRET
    WH->>DB: UPDATE reunioes SET status=ASSINADA, url_pdf_assinado, data_assinatura
    WH->>R: dispara email "ata assinada" pro facilitador e todos participantes
```
<!-- curated:end -->

---

## Autenticação (Supabase Auth + JWT)

<!-- curated:start -->
```mermaid
sequenceDiagram
    participant U as Usuario (browser)
    participant FE as Frontend (Next.js)
    participant SA as Supabase Auth
    participant BE as Backend (FastAPI)
    participant DB as Postgres

    U->>FE: clica login com email + senha
    FE->>SA: POST /auth/v1/token?grant_type=password
    SA-->>FE: access_token (JWT) + refresh_token
    FE->>FE: armazena JWT em cookie httpOnly (server action)
    U->>FE: navega para /dashboard
    FE->>BE: GET /api/pendencias (Authorization: Bearer <JWT>)
    BE->>SA: gotrue.verify_token(JWT)
    SA-->>BE: payload com user.id + email
    BE->>DB: SELECT * FROM participantes WHERE auth_user_id = <user.id>
    DB-->>BE: participante (com role, access_profile, is_super_admin)
    BE->>DB: query com SERVICE_ROLE_KEY (bypass RLS) + filtros aplicados em Python
    DB-->>BE: dados filtrados
    BE-->>FE: response JSON
    FE-->>U: renderiza UI
```

**Observação:** O Hospital Reuniões NÃO usa RLS direto do frontend. Backend FastAPI faz tudo via `SERVICE_ROLE_KEY` e aplica controle de acesso na camada de aplicação. Isso simplifica policies do Supabase mas exige disciplina em cada endpoint.
<!-- curated:end -->

---

## Pipeline de IA (transcrição → ata)

<!-- curated:start -->
```mermaid
flowchart TD
    A[Transcricao TXT] --> B[Extrair fala estruturada<br/>LLM call #1]
    B --> C[Identificar participantes mencionados<br/>regex + fuzzy match]
    C --> D{Todos os nomes<br/>casados com<br/>participantes do banco?}
    D -- nao --> E[status=AGUARDANDO_RESOLUCAO]
    D -- sim --> F[Resumir cada bloco<br/>LLM call #2]
    E --> G[Usuario resolve<br/>POST /reunioes/id/resolver-participantes]
    G --> F
    F --> H[Estruturar em JSON<br/>topicos + acoes + decisoes<br/>LLM call #3]
    H --> I[Gerar ata em portugues<br/>LLM call #4]
    I --> J[Salvar json_ata em reunioes]
    J --> K[Renderizar PDF via WeasyPrint]
    K --> L[Salvar url_pdf_preliminar]
    L --> M[status=AGUARDANDO_VALIDACAO]
```

**Configuração:** primary LLM = OpenRouter (`openai/gpt-5.4-mini`). Fallback automático para OpenAI se OpenRouter cair (`LLM_FALLBACK_MODEL`, default `gpt-4o-mini`).
<!-- curated:end -->

---

## Alertas automáticos do `/snapshot`

`/snapshot` faz pré-check de **gaps de fluxograma** ao regenerar os outros 6 arquivos. Se uma rota nova foi adicionada em `ROTAS.md` ou um estado novo apareceu em `ENTIDADES.md` (enum changed) sem fluxograma correspondente aqui, a skill imprime aviso pra você considerar adicionar.

Exemplos:
- Rota nova `POST /pendencias/{id}/repactuar` → aviso "considere adicionar transição REPACTUADA no fluxograma de Pendência".
- Estado novo no enum `status_ata` → aviso "estado X aparece em ENTIDADES.md mas não no fluxograma de Reunião".

A regeneração dos diagramas continua **manual** (curadoria humana). A skill só alerta.
