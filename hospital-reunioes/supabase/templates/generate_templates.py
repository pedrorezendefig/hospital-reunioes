#!/usr/bin/env python3
"""
Gera os templates HTML de email do Supabase Auth com logo base64 embutida.
Executar a partir da raiz do projeto: python3 supabase/templates/generate_templates.py
"""

import base64
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent

# Logo embutida como data URI base64 para funcionar sem depender de URL pública.
# Fonte: backend/app/static/images/logo_hospital_email.png
# Suportado por Gmail (web/mobile), Apple Mail, Outlook 2019+ e clientes modernos.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "backend" / "app" / "static" / "images" / "logo_hospital_email.png"
logo_b64 = "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")

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
# Usa token_hash + verifyOtp em vez de ConfirmationURL para ir DIRETO para a
# tela de redefinir senha sem passar pelo /auth/v1/verify do GoTrue (que usa
# implicit flow com tokens no hash, incompatível com route handler server-side).
_recovery_link = "{{ .SiteURL }}/reset-password/update?token_hash={{ .TokenHash }}&type=recovery"
recovery_body = f"""
  <h1 style="color:#1e293b;font-size:22px;font-weight:700;margin:0 0 8px;">
    Redefinir sua senha
  </h1>
  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">
    Recebemos uma solicitação para redefinir a senha da sua conta no Hospital São Matheus.
    Clique no botão abaixo para criar uma nova senha.
  </p>
  {btn("Redefinir minha Senha", _recovery_link)}
  {info_box([
      "<strong style='color:#1e293b;'>Validade do link:</strong> 1 hora a partir do envio.",
      "<strong style='color:#1e293b;'>Não solicitou isso?</strong> Ignore este email. Sua senha permanece a mesma.",
  ])}
  {fallback_link(_recovery_link)}
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
