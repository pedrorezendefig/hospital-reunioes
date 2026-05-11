# Email de auth em produção — template pt-BR servido pelo frontend

## Plano

### Contexto

Após o `plano-0129h` destravar o envio de email de reset de senha via Resend, o conteúdo do email continuava chegando no template default do GoTrue **em inglês** ("Reset Your Password" / "Follow this link to reset the password for your user" / "Alternatively, enter the code: …"). Remetente, SMTP, link e fluxo PKCE já estavam corretos — faltava só o template HTML refletir a marca.

O repo já tinha os 4 templates pt-BR prontos em `hospital-reunioes/supabase/templates/` (recovery, confirmation, magic_link, invite), mas o GoTrue self-hosted no Coolify **não lê filesystem do container** — só busca templates por HTTP via env var `MAILER_TEMPLATES_*`. Esse follow-up estava registrado em `plano-0129h` linha 96.

### Mudanças aplicadas

#### Código (commit `fe9cfbc`)

| Arquivo | Mudança |
|---|---|
| `supabase/templates/generate_templates.py` | Logo trocada de base64 inline (~150KB) por URL pública (`https://app.mala-ia.cloud/email-templates/logo-email.png`). Loop final escreve em **dois destinos**: `supabase/templates/` (CLI local) e `frontend/public/email-templates/` (prod). |
| `supabase/templates/{recovery,confirmation,magic_link,invite}.html` | Regenerados — logo agora é `<img src="https://...logo-email.png">` em vez de data URI. |
| `frontend/public/email-templates/{recovery,confirmation,magic_link,invite}.html` | Novos — versionados como assets do Next.js. |
| `frontend/public/email-templates/logo-email.png` | Cópia de `backend/app/static/images/logo_hospital_email.png` (32KB, 320×180 RGBA). |

#### Coolify — service `hospital-supabase` (UUID `o10ajq7525ch5vsa0a3yzoxt`)

8 env vars novas (delete + create por var, porque `update` em `resource=service` não é suportado pelo MCP):

| Var | Valor |
|---|---|
| `MAILER_TEMPLATES_RECOVERY` | `https://app.mala-ia.cloud/email-templates/recovery.html` |
| `MAILER_SUBJECTS_RECOVERY` | `Redefinir sua senha — Hospital São Matheus` |
| `MAILER_TEMPLATES_CONFIRMATION` | `https://app.mala-ia.cloud/email-templates/confirmation.html` |
| `MAILER_SUBJECTS_CONFIRMATION` | `Confirme seu email — Hospital São Matheus` |
| `MAILER_TEMPLATES_MAGIC_LINK` | `https://app.mala-ia.cloud/email-templates/magic_link.html` |
| `MAILER_SUBJECTS_MAGIC_LINK` | `Seu link de acesso — Hospital São Matheus` |
| `MAILER_TEMPLATES_INVITE` | `https://app.mala-ia.cloud/email-templates/invite.html` |
| `MAILER_SUBJECTS_INVITE` | `Você foi convidado — Hospital São Matheus` |

Restart do service depois.

### Critérios de sucesso

1. `curl -I https://app.mala-ia.cloud/email-templates/recovery.html` retorna 200, idem confirmation, magic_link, invite e `logo-email.png`.
2. Solicitar `/reset-password` em prod → email chega com:
   - Subject `Redefinir sua senha — Hospital São Matheus`
   - Logo carregada via URL pública
   - Texto pt-BR ("Recebemos uma solicitação para redefinir a senha…")
   - Botão azul "Redefinir minha Senha"
   - Footer "Hospital São Matheus — Sistema de Gestão de Reuniões"
   - Sem clipping "View entire message" no Gmail
3. Clique no botão → `app.mala-ia.cloud/reset-password/update?token_hash=…&type=recovery` → form aparece → trocar senha → login com nova senha funciona.
4. 2º teste 5 min depois pra eliminar intermitência.

### Riscos

- **Baixo.** Templates são públicos por design, sem segredos. Frontend já estava deployado. As 8 vars `MAILER_*` no service Supabase já existiam com valor `null` — só recebi novo valor.
- **Rollback:** delete das 8 vars + restart → GoTrue volta ao default em inglês imediatamente. Frontend não precisa rollback.

### Snapshot de rollback

As 8 env vars `MAILER_TEMPLATES_*` e `MAILER_SUBJECTS_*` existiam no service `hospital-supabase` antes do fix com valor `"null"`. Para reverter: delete por `env_uuid` no MCP Coolify + create vazio (ou simplesmente delete + restart).

UUIDs originais (antes do delete+create deste fix):

```
MAILER_TEMPLATES_RECOVERY      l55acgwznxctvfrfok1pa40o
MAILER_SUBJECTS_RECOVERY       p56n36savb998mzj1p3yp0f5
MAILER_TEMPLATES_CONFIRMATION  q29a7u2qw793s40kezjjp5sm
MAILER_SUBJECTS_CONFIRMATION   wnrwyl80gtha7zzdsauctuxu
MAILER_TEMPLATES_MAGIC_LINK    g1ap3a44r24a50mt90lqhn7s
MAILER_SUBJECTS_MAGIC_LINK     ydyjdmai1ab2uag99u87b39y
MAILER_TEMPLATES_INVITE        jwo9ks5ij50f44i3lr7x626v
MAILER_SUBJECTS_INVITE         w12ryudjaatoy0fm0r1eppk3
```

(Os UUIDs novos pós-create estão no histórico do MCP Coolify; não impactam rollback porque rollback se faz por `key`/listar+delete.)

## Execução / Resultados

### Linha do tempo (UTC -3)

| Hora | O que aconteceu |
|---|---|
| 01:58 | `generate_templates.py` editado — logo migra de base64 pra URL pública; loop final escreve em `supabase/templates/` + `frontend/public/email-templates/`. Logo PNG copiada pra `frontend/public/email-templates/logo-email.png`. |
| 01:59 | Script rodado 3× — md5 dos 8 outputs (4 HTMLs × 2 destinos) idênticos entre runs (idempotência confirmada). HTMLs ~3.6KB cada vs ~150KB com base64. Eyeball do `recovery.html` local: logo carrega via URL pública, layout/copy ok. |
| 01:59 | Commit `fe9cfbc` em `main` — `feat(auth-email): templates pt-BR servidos via frontend/public/`. 10 arquivos, +342/-15 linhas. |
| 02:01 | Deploy do frontend disparado automaticamente via webhook GitHub App (deployment `uh812u8lpua1us2fwg7tfgbi`). Build ~2min. |
| 02:02 | URLs validadas com `curl`: 5 endpoints (4 HTMLs + logo PNG) retornam 200 com content-type correto, recovery.html=3815B, logo=32846B. |
| 02:03 | 8 env vars `MAILER_TEMPLATES_*` / `MAILER_SUBJECTS_*` criadas via delete+create no service `hospital-supabase` (descoberto que as 8 já existiam com `value="null"` desde o setup inicial — não precisaram ser criadas do zero, mas precisaram ser substituídas porque MCP Coolify não suporta `update` em `resource=service`). |
| 02:03 | Restart do service Supabase queued. |
| 02:04 | (em andamento) Aguardando GoTrue voltar — todos os 14 containers do stack ficaram `exited` no momento do restart. |
| pendente | Teste end-to-end final do Pedro — solicitar reset, conferir email, clicar no link, definir nova senha, logar com a nova. |

### Recursos tocados

- **Repo:** 10 arquivos no commit `fe9cfbc` (1 script Python modificado, 4 HTMLs em `supabase/templates/` regenerados, 5 novos em `frontend/public/email-templates/` incluindo a logo PNG).
- **App Coolify** `okt237kwgu5x48qqbd57ntvz` (hospital-frontend): 1 deploy via webhook GitHub.
- **Service Coolify** `o10ajq7525ch5vsa0a3yzoxt` (hospital-supabase): 8 env vars `MAILER_*` recriadas. 1 restart + 1 start (precisei explicitamente após restart deixar containers em `exited`).
- **Doc:** `blueprint/DEPLOY.md` (subseção "Supabase service — auth/mailer" em `config-env`, status atualizado, entrada no histórico).

## Itens de follow-up

- Considerar configurar `MAILER_TEMPLATES_EMAIL_CHANGE` / `MAILER_SUBJECTS_EMAIL_CHANGE` quando o fluxo de "alterar email" for habilitado no app (template ainda não gerado pelo `generate_templates.py`).
- Avaliar adicionar `?v=YYYYMMDD` no `MAILER_TEMPLATES_*` quando atualizar templates — burlar cache caso Cloudflare entre na frente do `app.mala-ia.cloud` no futuro.
- Restart de service no Coolify (`mcp__coolify__control restart resource=service`) deixou os 14 containers em `exited`; foi necessário disparar `start` explícito depois. Investigar se é bug do MCP/Coolify ou comportamento esperado e documentar em `blueprint/DEPLOY.md` se for recorrente.
