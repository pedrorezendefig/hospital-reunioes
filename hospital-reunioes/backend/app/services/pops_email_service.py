"""Emails do contexto POPs — gatilhos imediatos de transição (PRD #76).

Todos os envios passam pelo email_service._enviar_email, que já resolve
Resend → SMTP → mock. Falha de email nunca quebra a ação que a disparou.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.services.email_service import _enviar_email, jinja_env

logger = logging.getLogger(__name__)


def send_pop_criado_notification(supabase, pop: dict, setor: dict, criador_nome: str | None = None) -> bool:
    """Notifica o Elaborador designado que um POP nasceu para ele, com link.

    Best-effort: qualquer falha (Elaborador sem email, template, envio) loga
    warning e retorna False — a criação do POP nunca é desfeita por email.
    """
    try:
        from app.services.email_constants import get_logo_data_uri

        elab = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("id", pop["elaborador_id"])
            .limit(1)
            .execute()
        )
        elaborador = elab.data[0] if elab.data else None
        if not elaborador or not elaborador.get("email"):
            logger.warning(f"[pop_criado] Elaborador {pop.get('elaborador_id')} sem email — notificação pulada")
            return False

        link = f"{settings.frontend_url}/pops"
        template = jinja_env.get_template("email_pop_criado.html")
        html = template.render(
            elaborador_nome=elaborador.get("nome_completo") or "Elaborador",
            criador_nome=criador_nome or "A equipe",
            codigo=pop["codigo"],
            nome=pop["nome"],
            setor_nome=setor.get("nome") or "",
            prazo_elaboracao_dias=pop.get("prazo_elaboracao_dias"),
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = (
            f"Você foi designado Elaborador do POP {pop['codigo']} — {pop['nome']}.\n"
            f"Setor: {setor.get('nome') or ''}. Prazo de elaboração: {pop.get('prazo_elaboracao_dias')} dias úteis.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"Novo POP para elaborar: {pop['codigo']} — {pop['nome']}"
        return _enviar_email(elaborador["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 — email nunca quebra a criação
        logger.warning(f"[pop_criado] Falha ao notificar Elaborador do POP {pop.get('codigo')}: {e}")
        return False


def send_elaboracao_concluida_notification(
    supabase, pop: dict, setor: dict, elaborador_nome: str | None = None
) -> bool:
    """Notifica o Revisor designado que a Versão chegou à Revisão (issue #83):
    "Aprovar versão final" do Elaborador → EM_REVISAO → este email, com link e
    o prazo de revisão do cadastro do POP.

    Best-effort como os demais: falha de email nunca desfaz a transição.
    """
    try:
        from app.services.email_constants import get_logo_data_uri

        rev = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("id", pop["revisor_id"])
            .limit(1)
            .execute()
        )
        revisor = rev.data[0] if rev.data else None
        if not revisor or not revisor.get("email"):
            logger.warning(f"[pop_revisao] Revisor {pop.get('revisor_id')} sem email — notificação pulada")
            return False

        link = f"{settings.frontend_url}/pops"
        template = jinja_env.get_template("email_pop_revisao.html")
        html = template.render(
            revisor_nome=revisor.get("nome_completo") or "Revisor",
            elaborador_nome=elaborador_nome or "O Elaborador",
            codigo=pop["codigo"],
            nome=pop["nome"],
            setor_nome=setor.get("nome") or "",
            prazo_revisao_dias=pop.get("prazo_revisao_dias"),
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = (
            f"A versão final do POP {pop['codigo']} — {pop['nome']} foi aprovada pelo Elaborador "
            f"e aguarda a sua revisão.\n"
            f"Setor: {setor.get('nome') or ''}. Prazo de revisão: {pop.get('prazo_revisao_dias')} dias.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"POP aguardando sua revisão: {pop['codigo']} — {pop['nome']}"
        return _enviar_email(revisor["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 — email nunca quebra a transição
        logger.warning(f"[pop_revisao] Falha ao notificar Revisor do POP {pop.get('codigo')}: {e}")
        return False
