# Fix — Email de "esqueci minha senha" não chegava em produção

## Plano

### Contexto

Ao usar `/reset-password` em `https://app.mala-ia.cloud`, o email com link para redefinir a senha nunca chegava. Frontend mostrava "Verifique seu email" normalmente — falso positivo.

### Causa raiz (confirmada)

O reset de senha é fluxo **100% Supabase Auth (GoTrue)** — o frontend chama `supabase.auth.resetPasswordForEmail(email)` em `hospital-reunioes/frontend/src/app/reset-password/page.tsx:25`, sem passar pelo backend FastAPI nem pelo Resend SDK que estão no app.

E o GoTrue do Supabase self-hosted no Coolify (service UUID `o10ajq7525ch5vsa0a3yzoxt`) estava com o mailer **completamente vazio**:

```
SMTP_HOST=               (vazio)
SMTP_USER=               (vazio)
SMTP_PASS=               (vazio)
SMTP_ADMIN_EMAIL=        (vazio)
SMTP_SENDER_NAME=        (vazio)
GOTRUE_SITE_URL=${SERVICE_URL_SUPABASEKONG}   → studio.mala-ia.cloud (errado)
ADDITIONAL_REDIRECT_URLS=  (vazio)
```

GoTrue retorna 200 mesmo sem provider SMTP configurado (anti-enumeration). Logo o frontend pensa que enviou. Bônus: mesmo com SMTP, `GOTRUE_SITE_URL` apontaria o link do email para Studio em vez do app.

O Resend já estava configurado no backend FastAPI (`RESEND_API_KEY=re_W3ckr1AE_…`, `RESEND_FROM_EMAIL=noreply@auth.mala-ia.cloud`), mas só era usado para email de confirmação de cadastro — não tocava no reset de senha.

### Mudança aplicada

8 env vars do service `hospital-supabase` (Coolify) — sem alteração de código:

| Var | Valor |
|---|---|
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_PORT` | `465` (SSL) |
| `SMTP_USER` | `resend` (literal) |
| `SMTP_PASS` | `re_W3ckr1AE_AseVLUSZ8UyRv7ifvBj6DDKK` (mesma `RESEND_API_KEY` do backend) |
| `SMTP_ADMIN_EMAIL` | `noreply@auth.mala-ia.cloud` |
| `SMTP_SENDER_NAME` | `Hospital São Matheus` |
| `GOTRUE_SITE_URL` | `https://app.mala-ia.cloud` |
| `ADDITIONAL_REDIRECT_URLS` | `https://app.mala-ia.cloud,https://app.mala-ia.cloud/reset-password/update,https://app.mala-ia.cloud/auth/callback` |

### Critérios de sucesso

1. `/reset-password` em prod recebe email "Redefinir sua senha — Hospital São Matheus" no destinatário em até ~30s.
2. Link no email aponta para `https://app.mala-ia.cloud/reset-password/update?token_hash=…&type=recovery` (não Studio).
3. Clique no link abre o formulário, permite trocar senha, redireciona para `/login`, login com nova senha funciona.

### Riscos

- **Baixo.** Mudança puramente env-var num serviço que não estava enviando email hoje. Pior caso: GoTrue não sobe e Studio fica fora do ar — mitigado pelo snapshot de rollback abaixo.
- **Templates default em inglês**: GoTrue não usa `supabase/templates/recovery.html` em prod (esses só valem para CLI local). Tema separado, fora deste fix.

### Snapshot de rollback (env vars antes do fix)

| Key | Valor original |
|-----|----------------|
| `SMTP_HOST` | (vazio) |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | (vazio) |
| `SMTP_PASS` | (vazio) |
| `SMTP_ADMIN_EMAIL` | (vazio) |
| `SMTP_SENDER_NAME` | (vazio) |
| `GOTRUE_SITE_URL` | `${SERVICE_URL_SUPABASEKONG}` |
| `ADDITIONAL_REDIRECT_URLS` | (vazio) |

## Execução / Resultados

### Linha do tempo (UTC -3)

| Hora | O que aconteceu |
|---|---|
| 00:23 | 8 env vars SMTP/SiteURL/RedirectURLs aplicadas no service Supabase (`o10ajq7525ch5vsa0a3yzoxt`) via `delete + create` no MCP Coolify (`update` em `resource=service` não é suportado — workaround). |
| 00:24 | `mcp__coolify__control restart` no service Supabase. GoTrue voltou ao ar (HTTP 200/401 em `/auth/v1/*`). |
| 00:50 | Pedro testou: email **chegou** via Resend (`Hospital São Matheus <noreply@auth.mala-ia.cloud>`). ✅ SMTP via Resend OK. |
| 00:50 | **2º problema descoberto** — link no email apontava para `supabase-kong:8000/auth/v1/verify?…` (nome interno do container, DNS não resolve). |
| 01:05 | Causa: env `API_EXTERNAL_URL=http://supabase-kong:8000`. Corrigido para `https://studio.mala-ia.cloud` (Kong público) via `delete + create` + `restart` do service. |
| 01:18 | Pedro testou: link agora caiu em `https://app.mala-ia.cloud/?code=…` — a raiz pública (`app/page.tsx`), que não trata `?code=…`. **3º problema** — fluxo PKCE não estava conectado. |
| 01:24 | Editado `hospital-reunioes/frontend/src/app/reset-password/page.tsx`: passa `redirectTo: '${origin}/auth/callback?next=/reset-password/update'`. Aproveita o `/auth/callback/route.ts` que já existia (faz `exchangeCodeForSession` e cria cookies sb-*). A página `update/page.tsx` linha 40-43 já trata o caso "sessão ativa, sem token_hash" → mostra o form de nova senha direto. Zero alteração em `update/page.tsx`. |
| 01:23 | Commit `9b2a55f` em `main` — `fix(reset-senha): passa redirectTo /auth/callback para fluxo PKCE`. |
| 01:28 | Deploy do frontend concluído via webhook GitHub App → Coolify. Build 4m31s. Health check: frontend HTTP 200, backend `/api/health` 200 (94ms), Supabase running:healthy. Histórico atualizado em `blueprint/DEPLOY.md`. |
| pendente | **Teste end-to-end final do Pedro** — solicitar reset, clicar no link, definir nova senha, logar com a nova. |

### Recursos tocados

- Service Coolify `o10ajq7525ch5vsa0a3yzoxt` (hospital-supabase): 9 env vars criadas/recriadas (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_ADMIN_EMAIL`, `SMTP_SENDER_NAME`, `GOTRUE_SITE_URL`, `ADDITIONAL_REDIRECT_URLS`, `API_EXTERNAL_URL`). 2 restarts.
- App Coolify `okt237kwgu5x48qqbd57ntvz` (hospital-frontend): 1 deploy via webhook (commit `9b2a55f`).
- Código: 1 arquivo (`frontend/src/app/reset-password/page.tsx`), 6 insertions / 3 deletions.
- Doc: `blueprint/DEPLOY.md` (status + histórico).

## Itens de follow-up

- Adicionar `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_ADMIN_EMAIL`, `SMTP_SENDER_NAME`, `GOTRUE_SITE_URL`, `ADDITIONAL_REDIRECT_URLS`, `API_EXTERNAL_URL` à seção `config-env` (subseção do **service Supabase**) em `blueprint/DEPLOY.md`. Hoje a seção só lista vars do backend; o service Supabase tem suas próprias obrigatórias e elas não estão documentadas.
- Atualizar `hospital-reunioes/.env.example` para refletir o domínio efetivo em prod (`noreply@auth.mala-ia.cloud`) em `RESEND_FROM_EMAIL`. Hoje aponta `noreply@hospitalsaomatheus.com.br`.
- Considerar templates customizados em PT-BR. `supabase/templates/recovery.html` existe no repo mas só é aplicado pelo CLI local. Para usar em prod, precisa publicar em URL pública (ex: servir pelo backend FastAPI ou GitHub raw) e setar `MAILER_TEMPLATES_RECOVERY` + `MAILER_SUBJECTS_RECOVERY` no service Supabase. Default em inglês ("Reset Your Password") funciona.
