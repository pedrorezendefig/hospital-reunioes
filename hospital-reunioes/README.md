# Hospital Reuniões

Aplicação interna do Hospital São Matheus. Um app, três contextos de domínio (ver [`CONTEXT-MAP.md`](../CONTEXT-MAP.md)):

| Contexto | O que faz | Glossário |
|---|---|---|
| **Reuniões** | Gravação → transcrição por IA → Ata → assinatura digital → acompanhamento de Pendências | [`CONTEXT.md`](../CONTEXT.md) |
| **POPs** | Ciclo de vida dos Procedimentos Operacionais Padrão: elaboração assistida por IA, revisão, validação, assinatura, Biblioteca | [`docs/pops/CONTEXT.md`](../docs/pops/CONTEXT.md) |
| **Ouvidoria** | Manifestações com tramitação por Dossiê, prazos com consequência, portal do setor, relatórios | ADRs 0034 a 0042 |

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI (Python 3.12, uv) |
| Frontend | Next.js 15 (App Router, pnpm) |
| Banco | Supabase self-hosted (PostgreSQL 17, RLS default-deny) |
| IA | OpenRouter (modelo em `LLM_MODEL`; prod usa Gemini) |
| PDF | WeasyPrint + Jinja2 |
| Assinatura | ClickSign |
| E-mail | Resend (SMTP como fallback local) |
| Deploy | Docker + Coolify (VPS Hostinger), auto-deploy por webhook no push da `main` |

## Rodar local

O caminho normal é o docker-compose, pela skill `/atualizar-app` do Claude Code. À mão:

```bash
cp .env.example .env        # preencha as chaves; o backend lê ESTE arquivo
docker compose up -d        # backend :8000, frontend :3000
```

Sem Docker:

```bash
# Backend (lê hospital-reunioes/.env)
cd backend && uv sync --extra dev && uv run uvicorn app.main:app --reload

# Frontend (lê frontend/.env.local; molde em frontend/.env.example)
cd frontend && corepack pnpm@9 install && pnpm dev
```

Testes: `cd backend && uv run python -m pytest` · `cd frontend && pnpm test`. Lint: `ruff check . && ruff format --check .` · `pnpm lint && pnpm exec tsc --noEmit`.

Setup completo de máquina (Claude Code, CLI do Coolify, tokens): [`docs/onboarding/claude-setup.md`](../docs/onboarding/claude-setup.md). Fluxo do dia a dia: [`docs/onboarding/dev.md`](../docs/onboarding/dev.md).

## Estrutura

```
backend/
  app/            # FastAPI: routers, services, pipeline de IA, cron, templates de e-mail e PDF
  scripts/        # scripts de operação (imports, backfills, seeds); fora da imagem de produção
  tests/          # pytest
frontend/
  src/            # Next.js App Router
  public/         # assets; email-templates/ é gerado por supabase/templates/generate_templates.py
                  # e servido em produção para o GoTrue (MAILER_TEMPLATES_*), não editar à mão
supabase/
  migrations/     # SQL numerado (001..NNN); aplicado à mão no Studio de produção
  templates/      # fonte dos e-mails do Auth (gera a cópia em frontend/public/email-templates/)
  snippets/       # queries de diagnóstico
docker-compose.yml
```

Scripts de operação rodam de dentro de `backend/`: `uv run python -m scripts.<nome>`.

Mapa factual da aplicação (rotas, entidades, schema, migrations, integrações): [`docs/spec/snapshots/`](../docs/spec/snapshots/). Arquitetura em uma página: [`docs/ARQUITETURA.md`](../docs/ARQUITETURA.md).
