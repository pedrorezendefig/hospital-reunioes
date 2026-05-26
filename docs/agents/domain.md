# Docs de domínio

Como as skills de engenharia devem consumir a documentação deste repo ao explorar o código.

## Antes de explorar, leia

- **`CONTEXT.md`** (na raiz) — glossário do domínio. Use a terminologia daqui em títulos de issue, hipóteses, nomes de teste e propostas de refactor. Não derive para sinônimos que o glossário pede para evitar.
- **`docs/adr/`** — leia os ADRs que tocam a área em que vai trabalhar. Decisões arquiteturais irreversíveis e "surpreendentes" vivem aqui.
- **`docs/spec/snapshots/`** — referência **factual e mecânica** da app, gerada do código a cada deploy: `ROTAS.md` (endpoints), `ENTIDADES.md` / `SCHEMA.md` (tabelas, FKs), `MIGRATIONS.md`, `INTEGRACOES.md`. Quando precisar saber "qual rota/tabela existe hoje", olhe aqui — não adivinhe.

Se algum desses arquivos não existir, **siga em silêncio**. Não sinalize a ausência nem sugira criá-los de antemão — `CONTEXT.md` e ADRs nascem sob demanda no `/grill-with-docs` quando um termo ou decisão de fato se resolve.

> **Distinção importante:** `CONTEXT.md` responde *"o que os termos do domínio significam"* (curado por humano, muda raro). Os snapshots respondem *"qual o estado mecânico da app agora"* (gerado por máquina, muda a cada deploy). São complementares — nenhum substitui o outro.

## Layout

**Single-context** (este repo): um `CONTEXT.md` + `docs/adr/` na raiz/`docs`. Não há `CONTEXT-MAP.md`.

```
/
├── CONTEXT.md
├── docs/
│   ├── adr/
│   │   ├── 0001-supabase-self-hosted-coolify.md
│   │   └── 0002-controle-acesso-aplicacao-service-role.md
│   ├── agents/        ← este diretório (config das skills)
│   └── spec/snapshots/ ← referência factual da app
└── hospital-reunioes/  ← backend (FastAPI) + frontend (Next.js) + supabase
```

## Conflito com ADR

Se o que você vai propor contradiz um ADR existente, **explicite** em vez de sobrescrever em silêncio:

> _Contradiz o ADR-0001 (Supabase self-hosted) — mas vale reabrir porque…_
