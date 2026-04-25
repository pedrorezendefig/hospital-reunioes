# Variáveis de ambiente

> Apenas **nomes**. Valores nunca aparecem no repositório, ficam no Coolify.

## Backend — obrigatórias no Coolify

```
ENVIRONMENT
DEBUG
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
OPENAI_API_KEY
CLICKSIGN_API_KEY
CLICKSIGN_BASE_URL
CLICKSIGN_WEBHOOK_SECRET
RESEND_API_KEY
RESEND_FROM_EMAIL
SIGNUP_ENCRYPTION_KEY
SIGNUP_PASSE
ENABLE_BYPASS_ENDPOINTS
```

## Backend — prod-only (skill valida valor exato)

| Var | Valor obrigatório |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `ENABLE_BYPASS_ENDPOINTS` | `false` |
| `CLICKSIGN_BASE_URL` | `https://app.clicksign.com` |

## Frontend — build-time (skill valida `is_build_time=true`)

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_ENVIRONMENT
```

## Supabase service — auth/mailer (UUID `o10ajq7525ch5vsa0a3yzoxt`)

```
GOTRUE_SITE_URL=https://app.mala-ia.cloud
ADDITIONAL_REDIRECT_URLS=https://app.mala-ia.cloud,https://app.mala-ia.cloud/reset-password/update,https://app.mala-ia.cloud/auth/callback
API_EXTERNAL_URL=https://studio.mala-ia.cloud
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASS=<RESEND_API_KEY>
SMTP_ADMIN_EMAIL=noreply@auth.mala-ia.cloud
SMTP_SENDER_NAME=Hospital São Matheus
MAILER_TEMPLATES_RECOVERY=https://app.mala-ia.cloud/email-templates/recovery.html
MAILER_TEMPLATES_CONFIRMATION=https://app.mala-ia.cloud/email-templates/confirmation.html
MAILER_TEMPLATES_MAGIC_LINK=https://app.mala-ia.cloud/email-templates/magic_link.html
MAILER_TEMPLATES_INVITE=https://app.mala-ia.cloud/email-templates/invite.html
MAILER_SUBJECTS_RECOVERY=Redefinir sua senha — Hospital São Matheus
MAILER_SUBJECTS_CONFIRMATION=Confirme seu email — Hospital São Matheus
MAILER_SUBJECTS_MAGIC_LINK=Seu link de acesso — Hospital São Matheus
MAILER_SUBJECTS_INVITE=Você foi convidado — Hospital São Matheus
```

Templates HTML são servidos como assets estáticos do Next.js (`frontend/public/email-templates/`). Para alterar o conteúdo dos emails: editar `supabase/templates/generate_templates.py`, rodar `python3 supabase/templates/generate_templates.py`, commit + push (rebuild do frontend). As 8 vars `MAILER_*` no service Supabase só apontam para as URLs; só precisam mudar se o caminho do asset mudar.

`update` em `resource=service` não é suportado pelo MCP Coolify; quando precisar editar uma var existente no service Supabase, fazer `delete` (com `env_uuid`) seguido de `create`.
