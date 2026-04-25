import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _resend_configurado() -> bool:
    return bool(settings.resend_api_key)


def _smtp_configurado() -> bool:
    return bool(settings.smtp_user) and "your-email" not in settings.smtp_user


def _enviar_via_resend(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": [destinatario],
                "subject": assunto,
                "html": html_content,
                "text": texto_fallback,
            }
        )
        logger.info(f"Email enviado via Resend para {destinatario} | Assunto: {assunto}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email via Resend: {e}")
        return False


def _enviar_via_smtp(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = destinatario
    msg.set_content(texto_fallback)
    msg.add_alternative(html_content, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Email enviado via SMTP para {destinatario} | Assunto: {assunto}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email via SMTP: {e}")
        return False


def _enviar_email(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
    """
    Tenta enviar email via Resend (primário). Se não configurado, tenta SMTP.
    Se nenhum configurado, loga em modo mock (desenvolvimento).
    """
    if _resend_configurado():
        return _enviar_via_resend(destinatario, assunto, html_content, texto_fallback)

    if _smtp_configurado():
        return _enviar_via_smtp(destinatario, assunto, html_content, texto_fallback)

    logger.warning(
        f"\n\n[MOCK EMAIL] Para: {destinatario} | Assunto: {assunto}\n"
        f"{texto_fallback}\n"
        f"--- Configure RESEND_API_KEY no .env para enviar emails reais ---\n"
    )
    return True
