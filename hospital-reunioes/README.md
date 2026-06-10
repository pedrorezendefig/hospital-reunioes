# Hospital Reuniões — Sistema de Gestão de Reuniões Hospitalares

Sistema automatizado de gestão do ciclo de vida de reuniões corporativas em hospital de alta complexidade.

**Da gravação à assinatura eletrônica da ata**, com acompanhamento automático de pendências.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI (Python) |
| Frontend | Next.js 15 (React) |
| Banco de Dados | Supabase (PostgreSQL) |
| IA | OpenRouter (GPT-5 Mini) |
| PDF | WeasyPrint + Jinja2 |
| Assinatura | ClickSign |
| Deploy | Docker + Coolify |

## Setup Local

```bash
# Backend
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend
cd frontend
pnpm install
pnpm dev
```

## Docker

```bash
cp .env.example .env
# Preencha as variáveis no .env
docker compose up -d
```

## Estrutura

```
├── backend/     # FastAPI — API + Pipeline
├── frontend/    # Next.js — Painel Web
├── supabase/    # Migrations SQL
└── docker-compose.yml
```
