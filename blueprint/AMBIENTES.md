# Ambientes — Hospital Reuniões

Diferenças concretas entre **LOCAL** (desenvolvimento) e **PRODUÇÃO** (Coolify na VPS Hostinger). Toda decisão que muda entre os dois ambientes está aqui.

---

## Comparação side-by-side

| Dimensão | LOCAL | PRODUÇÃO |
|---|---|---|
| Backend | `hr-backend` no `docker-compose.yml`, uvicorn com `--reload` | Coolify app `q11fubn3ezlszvwph695d9oh`, uvicorn sem reload |
| Frontend | `hr-frontend` no `docker-compose.yml`, Next.js dev | Coolify app `n5omtnv1u8u268zprvwu7902`, Next.js build `standalone` |
| Supabase | Docker local (`host.docker.internal:54351`) | Self-hosted no Coolify (`studio.mala-ia.cloud`) |
| Backend URL (frontend → backend) | `http://hr-backend:8000/api` (Docker DNS) | `https://api.mala-ia.cloud/api` |
| Frontend URL | `http://localhost:3000` | `https://app.mala-ia.cloud` |
| SSL | Sem (HTTP) | Traefik + Let's Encrypt |
| Hot-reload | Volume mounts: `/app/src`, `/app/app` | Imagem imutável |
| Banco: migrations | Aplicadas via Supabase CLI local | Aplicadas via `/deploy` (auto) ou Coolify Terminal + psql |
| Banco: dados | Mocados (tabelas populadas manualmente) | Vazio até primeiro deploy |
| Observabilidade | Logs do docker-compose | Coolify Logs tab + MCP `application_logs` |

---

## Email — Resend x SMTP x Mock

Definido em `app/services/email_service.py`. Escolha em cascata, por env var:

1. **`RESEND_API_KEY` configurado** → usa **Resend** (prioritário)
2. Senão se **`SMTP_HOST` configurado** → usa **SMTP** (Gmail ou outro)
3. Senão → **mock** (apenas log — emails não saem)

| Ambiente | `RESEND_API_KEY` | `SMTP_HOST` | Comportamento |
|---|---|---|---|
| LOCAL (default) | vazio | `smtp.gmail.com` (opcional) | Gmail SMTP, ou mock se SMTP não configurado |
| LOCAL (teste com Resend real) | configurado | — | Resend |
| PRODUÇÃO | **obrigatório** | fallback | Resend primário, SMTP se Resend cair |

**`RESEND_FROM_EMAIL`** define o remetente (ex: `noreply@hospitalsaomatheus.com.br` em prod).

---

## ClickSign — Sandbox x Produção

Definido pela var `CLICKSIGN_BASE_URL`. Valor **errado em produção quebra o fluxo silenciosamente** (envelopes criados em sandbox não chegam a lugar nenhum real).

| Ambiente | `CLICKSIGN_BASE_URL` | `CLICKSIGN_API_KEY` |
|---|---|---|
| LOCAL | `https://sandbox.clicksign.com` | Token do sandbox |
| PRODUÇÃO | **`https://app.clicksign.com`** | Token de produção |

A skill `/deploy` valida automaticamente no pre-flight que `CLICKSIGN_BASE_URL` em produção é exatamente `https://app.clicksign.com` — qualquer divergência aborta o deploy.

---

## Env vars backend (referência)

### Fonte de verdade: `.env.example` + `config.py`

A skill `/deploy` valida no pre-flight que os dois estão sincronizados (mesmo conjunto de chaves).

### Lista agrupada

**Ambiente**
- `ENVIRONMENT` — `development` local, `production` em prod
- `DEBUG` — `true` local, **obrigatoriamente `false`** em prod
- `ENABLE_BYPASS_ENDPOINTS` — pode ser `true` local, **obrigatoriamente `false`** em prod (pre-flight valida)

**Supabase**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

**OpenAI**
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (opcional, default `gpt-4o-mini`)

**ClickSign**
- `CLICKSIGN_API_KEY`
- `CLICKSIGN_BASE_URL` (ver tabela acima)
- `CLICKSIGN_WEBHOOK_SECRET` — auto-gerado

**Email**
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `SMTP_HOST` (fallback)
- `SMTP_PORT` (fallback)
- `SMTP_USER` (fallback)
- `SMTP_PASSWORD` (fallback)

**Signup**
- `SIGNUP_ENCRYPTION_KEY` — auto-gerado (Fernet)
- `SIGNUP_PASSE` — auto-gerado (token_urlsafe)

**Fireflies** (em integração)
- `FIREFLIES_WEBHOOK_SECRET`

---

## Env vars frontend

Todas `NEXT_PUBLIC_*` — **build-time** (ficam embutidas no bundle). No Coolify precisam ter `is_build_time: true`.

| Var | LOCAL | PRODUÇÃO |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | `http://host.docker.internal:54351` | `https://studio.mala-ia.cloud` ou URL pública |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon key local | anon key produção |
| `NEXT_PUBLIC_API_URL` | `http://hr-backend:8000/api` | `https://api.mala-ia.cloud/api` |
| `NEXT_PUBLIC_ENVIRONMENT` | `development` | `production` |

**Importante:** mudar qualquer `NEXT_PUBLIC_*` no Coolify exige **rebuild** do frontend (não só restart). A skill `/deploy` orienta isso automaticamente.

---

## Secrets auto-gerados (não copiar entre ambientes)

Gerados localmente pela skill, setados via MCP no Coolify, **nunca persistidos** em arquivo/log. Rotacionar invalida fluxos em andamento.

| Var | Serviço | Gerador | Impacto se rotacionar |
|---|---|---|---|
| `SIGNUP_ENCRYPTION_KEY` | backend | `Fernet.generate_key()` | Cadastros pendentes ficam inválidos (senha cifrada não descriptografa) |
| `CLICKSIGN_WEBHOOK_SECRET` | backend | `secrets.token_urlsafe(32)` | Atualizar no painel ClickSign também — senão webhooks passam a falhar HMAC |
| `SIGNUP_PASSE` | backend | `secrets.token_urlsafe(24)` | Depende do fluxo que usa — ver `app/routers/signup.py` |

---

## Supabase — Docker local vs self-hosted

### Local (Docker)

Sobe via `supabase start` (CLI) ou `docker-compose` da raiz. Hostname `host.docker.internal:54351` acessa do container backend.

- Studio: `http://localhost:54323`
- Postgres: `localhost:54322`
- Auth/API: `localhost:54321`
- Storage: idem

Migrations aplicadas via `supabase db reset` ou `supabase migration up`.

### Produção (Coolify)

Self-hosted como **Service** tipo `supabase` no Coolify. Containers:
- `supabase-studio-*`
- `supabase-db-*` (Postgres)
- `supabase-kong-*` (gateway)
- `supabase-storage-*`
- `supabase-auth-*`

Domínio `studio.mala-ia.cloud` resolve para o Studio.

**Migrations em produção:**
- Caminho 1 (recomendado): a skill `/deploy` aplica automaticamente via MCP ou `docker exec supabase-db-* psql` — só pede confirmação para DDL destrutivo.
- Caminho 2 (manual): Coolify → Terminal → `supabase-db-*` → `psql -U postgres -d postgres` → colar SQL.

**Storage local vs prod:**
- Local: filesystem do container (reset perde tudo).
- Prod: filesystem do container também — **backup manual necessário** (ou configurar S3 compatível no futuro).

---

## Matriz de diferenças críticas

Quando alguma destas estiver errada em produção → fluxo quebra silenciosamente. A skill `/deploy` valida todas no pre-flight.

| Var | Valor obrigatório em PROD |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `ENABLE_BYPASS_ENDPOINTS` | `false` |
| `CLICKSIGN_BASE_URL` | `https://app.clicksign.com` |
| `RESEND_API_KEY` | presente e não vazio |
| `SIGNUP_ENCRYPTION_KEY` | presente e não vazio (auto-gerado) |
| `NEXT_PUBLIC_*` | todas com `is_build_time: true` |

---

## DNS

Subdomínios de `mala-ia.cloud` (DNS gerenciado pelo Hostinger, registros A apontando para VPS `31.97.29.32`):

| Subdomínio | Destino |
|---|---|
| `app.mala-ia.cloud` | Frontend (Coolify → Traefik) |
| `api.mala-ia.cloud` | Backend (Coolify → Traefik) |
| `studio.mala-ia.cloud` | Supabase Studio (Coolify → Traefik) |
| `coolify.mala-ia.cloud` | Painel do Coolify |

**Cloudflare Proxy:** desligado (nuvem cinza — DNS only). Traefik faz SSL direto com Let's Encrypt.
