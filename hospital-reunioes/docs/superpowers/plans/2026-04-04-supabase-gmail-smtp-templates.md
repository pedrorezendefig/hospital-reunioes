# Supabase Auth — Gmail SMTP + Templates Branded Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configurar o Supabase local para enviar emails reais via Gmail SMTP e criar templates HTML com identidade visual do Hospital São Matheus para todos os emails de autenticação.

**Architecture:** O Supabase Auth suporta SMTP customizado via `[auth.email.smtp]` em `config.toml`, lendo credenciais de variáveis de ambiente. Os templates são arquivos HTML standalone com variáveis Go template (`{{ .ConfirmationURL }}`, etc.), criados em `supabase/templates/`. A logo é embutida como data URI base64 gerada a partir do PNG existente em `backend/app/static/images/logo_hospital.png`.

**Tech Stack:** Supabase CLI, Gmail SMTP (App Password), HTML inline styles (email-safe), Go templates (Supabase), Python 3 (geração dos templates).

---

## Arquivos que serão criados/modificados

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `supabase/config.toml` | Modificar | Habilitar SMTP Gmail + registrar 4 templates |
| `supabase/.env` | Modificar | Adicionar SMTP_USER e SMTP_PASSWORD |
| `supabase/templates/generate_templates.py` | Criar | Script que gera os 4 HTMLs com logo base64 embutida |
| `supabase/templates/recovery.html` | Gerado pelo script | Template reset de senha |
| `supabase/templates/confirmation.html` | Gerado pelo script | Template confirmação de email |
| `supabase/templates/magic_link.html` | Gerado pelo script | Template magic link (login sem senha) |
| `supabase/templates/invite.html` | Gerado pelo script | Template convite de usuário |

---

## Task 1: Configurar SMTP no `supabase/config.toml`

**Files:**
- Modify: `supabase/config.toml` (linhas 215-234)

- [ ] **Step 1: Substituir o bloco SMTP comentado**

Localizar o bloco:
```toml
# Use a production-ready SMTP server
# [auth.email.smtp]
# enabled = true
# host = "smtp.sendgrid.net"
# port = 587
# user = "apikey"
# pass = "env(SENDGRID_API_KEY)"
# admin_email = "admin@email.com"
# sender_name = "Admin"
```

Substituir por:
```toml
# Use a production-ready SMTP server
[auth.email.smtp]
enabled = true
host = "smtp.gmail.com"
port = 587
user = "env(SMTP_USER)"
pass = "env(SMTP_PASSWORD)"
admin_email = "env(SMTP_USER)"
sender_name = "Hospital São Matheus"
```

- [ ] **Step 2: Adicionar registro dos 4 templates após o bloco SMTP**

Logo após a seção SMTP (após `sender_name`), adicionar:

```toml
# Templates de email customizados
[auth.email.template.recovery]
subject = "Redefinir sua senha — Hospital São Matheus"
content_path = "./supabase/templates/recovery.html"

[auth.email.template.confirmation]
subject = "Confirme seu email — Hospital São Matheus"
content_path = "./supabase/templates/confirmation.html"

[auth.email.template.magic_link]
subject = "Seu link de acesso — Hospital São Matheus"
content_path = "./supabase/templates/magic_link.html"

[auth.email.template.invite]
subject = "Você foi convidado — Hospital São Matheus"
content_path = "./supabase/templates/invite.html"
```

- [ ] **Step 3: Remover (ou comentar) o bloco `[auth.email.template.invite]` antigo**

Verificar se ainda existe o bloco comentado antigo:
```toml
# [auth.email.template.invite]
# subject = "You have been invited"
# content_path = "./supabase/templates/invite.html"
```
Se existir, apagar — o novo bloco já substitui.

---

## Task 2: Adicionar credenciais SMTP ao `supabase/.env`

**Files:**
- Modify: `supabase/.env`

- [ ] **Step 1: Adicionar variáveis SMTP ao arquivo**

O arquivo atual tem apenas as credenciais do Google OAuth. Adicionar ao final:

```
SMTP_USER=pmrdef@gmail.com
SMTP_PASSWORD=bsox umfo ttwb rrko
```

Arquivo completo resultante:
```
GOOGLE_CLIENT_ID=974789707702-qlddhf606oaomtj3nq09kcggdlfo6tah.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
SMTP_USER=pmrdef@gmail.com
SMTP_PASSWORD=bsox umfo ttwb rrko
```

---

## Task 3: Criar script gerador de templates

**Files:**
- Create: `supabase/templates/generate_templates.py`

O Supabase Auth usa variáveis Go template (não Jinja2). Os templates são HTML puro com `{{ .ConfirmationURL }}`, `{{ .Email }}`, etc. A logo precisa ser embutida como data URI base64 (emails do Gmail bloqueiam imagens externas por padrão).

- [ ] **Step 1: Criar o diretório de templates**

```bash
mkdir -p hospital-reunioes/supabase/templates
```

- [ ] **Step 2: Criar o script `generate_templates.py`**

Criar `hospital-reunioes/supabase/templates/generate_templates.py`:

```python
#!/usr/bin/env python3
"""
Gera os templates HTML de email do Supabase Auth com logo base64 embutida.
Executar a partir da raiz do projeto: python3 supabase/templates/generate_templates.py
"""

import base64
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = ROOT / "backend/app/static/images/logo_hospital.png"
TEMPLATES_DIR = Path(__file__).parent

with open(LOGO_PATH, "rb") as f:
    logo_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()

BRAND_PRIMARY = "#2B2E7E"
BRAND_SECONDARY = "#2558A0"
BRAND_ACCENT = "#3b82f6"


def base_html(title: str, subtitle: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#edf2f7;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#edf2f7;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.10);">

          <!-- Faixa gradiente no topo -->
          <tr>
            <td style="background:linear-gradient(90deg,{BRAND_PRIMARY} 0%,{BRAND_SECONDARY} 60%,{BRAND_ACCENT} 100%);height:5px;font-size:0;line-height:0;">&nbsp;</td>
          </tr>

          <!-- Header com logo -->
          <tr>
            <td style="background:#ffffff;padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e8edf5;">
              <img src="{logo_b64}" alt="Hospital São Matheus" width="160" style="max-width:160px;height:auto;display:block;margin:0 auto;" />
              <p style="color:#64748b;margin:10px 0 0;font-size:12px;font-weight:500;letter-spacing:.8px;text-transform:uppercase;">
                {subtitle}
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px 32px;background:#ffffff;">
              {body}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;border-top:1px solid #e8edf5;padding:20px 40px;text-align:center;">
              <p style="color:#94a3b8;font-size:12px;margin:0;line-height:1.6;">
                Hospital São Matheus — Sistema de Gestão de Reuniões<br/>
                Este email foi enviado automaticamente. Por favor, não responda.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def btn(text: str, url: str) -> str:
    return f"""<table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:8px 0 32px;">
        <a href="{url}"
           style="display:inline-block;background:linear-gradient(135deg,{BRAND_PRIMARY},{BRAND_SECONDARY});color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;padding:16px 40px;border-radius:12px;letter-spacing:.2px;">
          {text}
        </a>
      </td>
    </tr>
  </table>"""


def info_box(lines: list[str]) -> str:
    items = "".join(
        f'<p style="color:#475569;font-size:13px;margin:0 0 {"8" if i < len(lines)-1 else "0"}px;">{line}</p>'
        for i, line in enumerate(lines)
    )
    return f"""<table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:20px 24px;">
        {items}
      </td>
    </tr>
  </table>"""


def fallback_link(url: str) -> str:
    return f"""<p style="color:#94a3b8;font-size:12px;margin:20px 0 0;line-height:1.5;">
    Se o botão não funcionar, copie e cole este link no navegador:<br/>
    <a href="{url}" style="color:{BRAND_SECONDARY};word-break:break-all;">{url}</a>
  </p>"""


# ── recovery.html ────────────────────────────────────────────────────────────
recovery_body = f"""
  <h1 style="color:#1e293b;font-size:22px;font-weight:700;margin:0 0 8px;">
    Redefinir sua senha
  </h1>
  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">
    Recebemos uma solicitação para redefinir a senha da sua conta no Hospital São Matheus.
    Clique no botão abaixo para criar uma nova senha.
  </p>
  {btn("Redefinir minha Senha", "{{ .ConfirmationURL }}")}
  {info_box([
      "<strong style='color:#1e293b;'>Validade do link:</strong> 1 hora a partir do envio.",
      "<strong style='color:#1e293b;'>Não solicitou isso?</strong> Ignore este email. Sua senha permanece a mesma.",
  ])}
  {fallback_link("{{ .ConfirmationURL }}")}
"""

# ── confirmation.html ────────────────────────────────────────────────────────
confirmation_body = f"""
  <h1 style="color:#1e293b;font-size:22px;font-weight:700;margin:0 0 8px;">
    Confirme seu endereço de email
  </h1>
  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">
    Clique no botão abaixo para confirmar seu email e ativar o acesso à plataforma
    de gestão de reuniões do Hospital São Matheus.
  </p>
  {btn("Confirmar meu Email", "{{ .ConfirmationURL }}")}
  {info_box([
      "<strong style='color:#1e293b;'>Validade do link:</strong> 24 horas a partir do cadastro.",
      "<strong style='color:#1e293b;'>Não solicitou o cadastro?</strong> Ignore este email. Nenhuma conta será criada.",
  ])}
  {fallback_link("{{ .ConfirmationURL }}")}
"""

# ── magic_link.html ───────────────────────────────────────────────────────────
magic_link_body = f"""
  <h1 style="color:#1e293b;font-size:22px;font-weight:700;margin:0 0 8px;">
    Seu link de acesso
  </h1>
  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">
    Clique no botão abaixo para entrar na plataforma sem precisar de senha.
    O link é de uso único e expira em 1 hora.
  </p>
  {btn("Entrar na Plataforma", "{{ .ConfirmationURL }}")}
  {info_box([
      "<strong style='color:#1e293b;'>Uso único:</strong> Este link funciona apenas uma vez.",
      "<strong style='color:#1e293b;'>Não solicitou?</strong> Ignore este email. Sua conta está segura.",
  ])}
  {fallback_link("{{ .ConfirmationURL }}")}
"""

# ── invite.html ───────────────────────────────────────────────────────────────
invite_body = f"""
  <h1 style="color:#1e293b;font-size:22px;font-weight:700;margin:0 0 8px;">
    Você foi convidado
  </h1>
  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">
    Você recebeu um convite para acessar a plataforma de gestão de reuniões
    do Hospital São Matheus. Clique no botão abaixo para criar sua conta e entrar.
  </p>
  {btn("Aceitar Convite e Criar Conta", "{{ .ConfirmationURL }}")}
  {info_box([
      "<strong style='color:#1e293b;'>Validade do convite:</strong> 24 horas.",
      "<strong style='color:#1e293b;'>Não esperava este convite?</strong> Ignore este email com segurança.",
  ])}
  {fallback_link("{{ .ConfirmationURL }}")}
"""

templates = {
    "recovery.html": base_html(
        "Redefinir senha — Hospital São Matheus",
        "Segurança da Conta",
        recovery_body,
    ),
    "confirmation.html": base_html(
        "Confirme seu email — Hospital São Matheus",
        "Confirmação de Email",
        confirmation_body,
    ),
    "magic_link.html": base_html(
        "Seu link de acesso — Hospital São Matheus",
        "Acesso à Plataforma",
        magic_link_body,
    ),
    "invite.html": base_html(
        "Você foi convidado — Hospital São Matheus",
        "Convite de Acesso",
        invite_body,
    ),
}

for filename, content in templates.items():
    path = TEMPLATES_DIR / filename
    path.write_text(content, encoding="utf-8")
    print(f"✓ {filename} gerado ({len(content)} bytes)")

print("\nTodos os templates gerados com sucesso!")
```

- [ ] **Step 3: Executar o script para gerar os templates**

```bash
cd /Users/pedrorezende/PedroDev/Hospital/hospital-reunioes
python3 supabase/templates/generate_templates.py
```

Saída esperada:
```
✓ recovery.html gerado (XXXXX bytes)
✓ confirmation.html gerado (XXXXX bytes)
✓ magic_link.html gerado (XXXXX bytes)
✓ invite.html gerado (XXXXX bytes)

Todos os templates gerados com sucesso!
```

- [ ] **Step 4: Verificar que os 4 arquivos foram criados**

```bash
ls -la hospital-reunioes/supabase/templates/
```

Esperado: `generate_templates.py`, `recovery.html`, `confirmation.html`, `magic_link.html`, `invite.html`.

---

## Task 4: Reiniciar o Supabase e testar

**Files:** nenhum (apenas operações de serviço)

- [ ] **Step 1: Parar o Supabase local**

```bash
cd hospital-reunioes
supabase stop
```

Aguardar confirmação de parada.

- [ ] **Step 2: Iniciar o Supabase com as novas configurações**

```bash
supabase start
```

Aguardar o output `Started supabase local development setup.` Verificar que não há erros de configuração SMTP na saída.

- [ ] **Step 3: Testar o envio de email de reset de senha via curl**

```bash
curl -s -X POST http://127.0.0.1:54321/auth/v1/recover \
  -H "Content-Type: application/json" \
  -H "apikey: sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH" \
  -d '{"email": "pmrdef@gmail.com"}'
```

Saída esperada: `{}` (corpo vazio, status 200 — o Supabase não confirma se o email existe por segurança).

- [ ] **Step 4: Verificar no Gmail**

Abrir `gmail.com` e verificar se chegou um email de "Hospital São Matheus" com:
- Remetente: `pmrdef@gmail.com`
- Assunto: "Redefinir sua senha — Hospital São Matheus"
- Template visual com logo, gradiente azul e botão "Redefinir minha Senha"

- [ ] **Step 5: Testar o fluxo completo na UI**

1. Acessar `http://localhost:3000/login`
2. Clicar em "Esqueci minha senha"
3. Inserir `pmrdef@gmail.com`
4. Verificar que o email chegou no Gmail com o template branded
5. Clicar no botão "Redefinir minha Senha"
6. Confirmar que redireciona para `localhost:3000/reset-password/update`
7. Inserir nova senha e verificar que o reset funciona

---

## Verificação final

- [ ] Email de reset chega no Gmail (não fica no Mailpit/Inbucket)
- [ ] Template tem logo do hospital, faixa gradiente azul, botão com gradiente da marca
- [ ] Link no email redireciona corretamente para `localhost:3000/reset-password/update`
- [ ] Após clicar no link, o fluxo de nova senha funciona end-to-end
- [ ] Os outros emails do backend (cadastro via Resend) continuam funcionando normalmente
