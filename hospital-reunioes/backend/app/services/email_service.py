import base64
import logging
import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
# autoescape: variáveis renderizadas nos emails são texto puro vindo de input
# de usuário (ex.: nome do POP) — mesmo padrão do reuniao_email_service.
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def _resend_configurado() -> bool:
    return bool(settings.resend_api_key)


def _smtp_configurado() -> bool:
    return bool(settings.smtp_user) and "your-email" not in settings.smtp_user


def transporte_configurado() -> bool:
    """Existe transporte REAL de email nesta máquina (Resend ou SMTP)?

    `False` é o modo mock do desenvolvimento, e o detalhe que importa é o
    retorno de `_enviar_email` nele: `True`, sem nada ter saído. Quem lê esse
    `True` como entrega e PERSISTE estado a partir dele carimba "entregue" em
    cima de um email que ninguém recebeu.

    Em produção isso não é hipótese de laboratório: basta a chave do Resend ser
    rotacionada para vazio e todo envio do app vira sucesso silencioso (issue
    #435). O relatório da Ouvidoria pergunta aqui antes de carimbar; quem só
    loga o resultado não precisa.

    O processador externo em si (Resend, fora do Brasil) está registrado no
    ADR 0039."""
    return _resend_configurado() or _smtp_configurado()


# Anexo: (nome do arquivo, bytes). O tipo sai do nome, como no resto do mundo
# do email. Chega até aqui porque o relatório da Ouvidoria viaja em PDF
# (issue #345); antes dela, nenhum email do app levava arquivo.
Anexo = tuple[str, bytes]


def _tipo_do_anexo(nome: str) -> tuple[str, str]:
    tipo, _ = mimetypes.guess_type(nome)
    principal, _, secundario = (tipo or "application/octet-stream").partition("/")
    return principal, secundario or "octet-stream"


def _enviar_via_resend(
    destinatario: str, assunto: str, html_content: str, texto_fallback: str, anexos: list[Anexo] | None = None
) -> bool:
    resend.api_key = settings.resend_api_key
    payload = {
        "from": settings.resend_from_email,
        "to": [destinatario],
        "subject": assunto,
        "html": html_content,
        "text": texto_fallback,
    }
    if anexos:
        # `content` em base64: é a forma que a API documenta, e cabe na
        # requisição sem virar uma lista de milhares de inteiros.
        payload["attachments"] = [
            {
                "filename": nome,
                "content": base64.b64encode(conteudo).decode("ascii"),
                "content_type": "/".join(_tipo_do_anexo(nome)),
            }
            for nome, conteudo in anexos
        ]
    try:
        resend.Emails.send(payload)
        logger.info(f"Email enviado via Resend para {destinatario} | Assunto: {assunto}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email via Resend: {e}")
        return False


def _enviar_via_smtp(
    destinatario: str, assunto: str, html_content: str, texto_fallback: str, anexos: list[Anexo] | None = None
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = destinatario
    msg.set_content(texto_fallback)
    msg.add_alternative(html_content, subtype="html")
    for nome, conteudo in anexos or []:
        principal, secundario = _tipo_do_anexo(nome)
        msg.add_attachment(conteudo, maintype=principal, subtype=secundario, filename=nome)
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


def _enviar_email(
    destinatario: str, assunto: str, html_content: str, texto_fallback: str, anexos: list[Anexo] | None = None
) -> bool:
    """
    Tenta enviar email via Resend (primário). Se não configurado, tenta SMTP.
    Se nenhum configurado, loga em modo mock (desenvolvimento).
    """
    if _resend_configurado():
        return _enviar_via_resend(destinatario, assunto, html_content, texto_fallback, anexos)

    if _smtp_configurado():
        return _enviar_via_smtp(destinatario, assunto, html_content, texto_fallback, anexos)

    anexados = ", ".join(f"{nome} ({len(conteudo)} bytes)" for nome, conteudo in anexos or []) or "nenhum"
    logger.warning(
        f"\n\n[MOCK EMAIL] Para: {destinatario} | Assunto: {assunto} | Anexos: {anexados}\n"
        f"{texto_fallback}\n"
        f"--- Configure RESEND_API_KEY no .env para enviar emails reais ---\n"
    )
    return True


def enviar_com_anexo(
    destinatario: str, assunto: str, html_content: str, texto_fallback: str, anexos: list[Anexo]
) -> bool:
    """A porta pública do envio com arquivo junto. Mesmo caminho de sempre
    (Resend primeiro, SMTP como reserva), só que carregando o anexo."""
    return _enviar_email(destinatario, assunto, html_content, texto_fallback, anexos)


def send_meeting_scheduled_notification(
    supabase,
    id_reuniao: str,
    facilitador_id: str,
    criador_id: str,
) -> bool:
    """Notifica o facilitador quando outra pessoa (ex: secretária) agendou uma reunião pra ele.

    Busca os dados da reunião, do facilitador (destinatário) e do criador,
    renderiza o template `email_reuniao_agendada.html` e dispara via _enviar_email.
    Idempotente do ponto de vista do banco (não persiste nada além do log).
    """
    from app.services.email_constants import get_logo_data_uri

    try:
        r = (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, data, hora_inicio, hora_fim, objetivo")
            .eq("id_reuniao", id_reuniao)
            .limit(1)
            .execute()
        )
        if not r.data:
            logger.warning(f"[meeting_scheduled] reunião {id_reuniao} não encontrada, abortando email")
            return False
        reuniao = r.data[0]

        fac = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("id", facilitador_id)
            .limit(1)
            .execute()
        )
        if not fac.data:
            logger.warning(f"[meeting_scheduled] facilitador {facilitador_id} não encontrado")
            return False
        facilitador = fac.data[0]
        if not facilitador.get("email"):
            logger.warning(f"[meeting_scheduled] facilitador {facilitador_id} sem email, pulando notificação")
            return False

        cr = supabase.table("participantes").select("id, nome_completo").eq("id", criador_id).limit(1).execute()
        criador_nome = cr.data[0].get("nome_completo") if cr.data else "Equipe da secretaria"

        template = jinja_env.get_template("email_reuniao_agendada.html")
        html = template.render(
            facilitador_nome=facilitador.get("nome_completo") or "Facilitador",
            criador_nome=criador_nome,
            id_reuniao=reuniao.get("id_reuniao"),
            titulo=reuniao.get("titulo") or "Sem título",
            data=reuniao.get("data") or "A definir",
            hora_inicio=reuniao.get("hora_inicio"),
            hora_fim=reuniao.get("hora_fim"),
            objetivo=reuniao.get("objetivo"),
            frontend_url=settings.frontend_url,
            logo_base64=get_logo_data_uri(),
        )
        texto_fallback = (
            f"Olá {facilitador.get('nome_completo')},\n\n"
            f"{criador_nome} agendou uma nova reunião pra você:\n"
            f"- Título: {reuniao.get('titulo')}\n"
            f"- Data: {reuniao.get('data')}\n"
            f"- Horário: {reuniao.get('hora_inicio') or 'A definir'}\n"
            f"Acesse o sistema em {settings.frontend_url}/reunioes\n"
        )

        return _enviar_email(
            destinatario=facilitador["email"],
            assunto=f"Nova reunião agendada: {reuniao.get('titulo') or id_reuniao}",
            html_content=html,
            texto_fallback=texto_fallback,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[meeting_scheduled] Falha ao enviar email pra facilitador {facilitador_id}: {e}")
        return False
