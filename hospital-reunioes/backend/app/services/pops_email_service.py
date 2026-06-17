"""Emails do contexto POPs: gatilhos imediatos de transição (PRD #76).

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
    warning e retorna False: a criação do POP nunca é desfeita por email.
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
            logger.warning(f"[pop_criado] Elaborador {pop.get('elaborador_id')} sem email: notificação pulada")
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
            f"Você foi designado Elaborador do POP {pop['codigo']} ({pop['nome']}).\n"
            f"Setor: {setor.get('nome') or ''}. Prazo de elaboração: {pop.get('prazo_elaboracao_dias')} dias úteis.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"Novo POP para elaborar: {pop['codigo']} ({pop['nome']})"
        return _enviar_email(elaborador["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 (email nunca quebra a criação)
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
            logger.warning(f"[pop_revisao] Revisor {pop.get('revisor_id')} sem email: notificação pulada")
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
            f"A versão final do POP {pop['codigo']} ({pop['nome']}) foi aprovada pelo Elaborador "
            f"e aguarda a sua revisão.\n"
            f"Setor: {setor.get('nome') or ''}. Prazo de revisão: {pop.get('prazo_revisao_dias')} dias.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"POP aguardando sua revisão: {pop['codigo']} ({pop['nome']})"
        return _enviar_email(revisor["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 (email nunca quebra a transição)
        logger.warning(f"[pop_revisao] Falha ao notificar Revisor do POP {pop.get('codigo')}: {e}")
        return False


def send_validacao_pendente_notification(supabase, pop: dict, setor: dict, remetente_nome: str | None = None) -> bool:
    """Notifica o Validador designado que a Versão chegou à Validação (issue
    #85): tanto pela aprovação do Revisor quanto pelo reenvio direto após uma
    Devolução do Validador (retorno direto a quem devolveu).

    Best-effort como os demais: falha de email nunca desfaz a transição.
    """
    try:
        from app.services.email_constants import get_logo_data_uri

        val = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("id", pop["validador_id"])
            .limit(1)
            .execute()
        )
        validador = val.data[0] if val.data else None
        if not validador or not validador.get("email"):
            logger.warning(f"[pop_validacao] Validador {pop.get('validador_id')} sem email: notificação pulada")
            return False

        link = f"{settings.frontend_url}/pops/{pop['id']}/versao"
        template = jinja_env.get_template("email_pop_validacao.html")
        html = template.render(
            validador_nome=validador.get("nome_completo") or "Validador",
            remetente_nome=remetente_nome or "A equipe",
            codigo=pop["codigo"],
            nome=pop["nome"],
            setor_nome=setor.get("nome") or "",
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = (
            f"A Versão do POP {pop['codigo']} ({pop['nome']}) chegou à Validação e aguarda a sua aprovação final.\n"
            f"Setor: {setor.get('nome') or ''}.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"POP aguardando sua validação: {pop['codigo']} ({pop['nome']})"
        return _enviar_email(validador["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 (email nunca quebra a transição)
        logger.warning(f"[pop_validacao] Falha ao notificar Validador do POP {pop.get('codigo')}: {e}")
        return False


def send_devolucao_notification(
    supabase, pop: dict, setor: dict, *, comentarios: str, autor_nome: str | None, etapa_label: str
) -> bool:
    """Notifica o Elaborador de uma Devolução (issue #85), com os comentários
    de quem devolveu no corpo e link direto para a elaboração.

    Best-effort como os demais: falha de email nunca desfaz a transição.
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
            logger.warning(f"[pop_devolucao] Elaborador {pop.get('elaborador_id')} sem email: notificação pulada")
            return False

        link = f"{settings.frontend_url}/pops/{pop['id']}/elaboracao"
        template = jinja_env.get_template("email_pop_devolucao.html")
        html = template.render(
            elaborador_nome=elaborador.get("nome_completo") or "Elaborador",
            autor_nome=autor_nome or "O responsável pela etapa",
            etapa_label=etapa_label,
            comentarios=comentarios,
            codigo=pop["codigo"],
            nome=pop["nome"],
            setor_nome=setor.get("nome") or "",
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = (
            f"O POP {pop['codigo']} ({pop['nome']}) foi devolvido na {etapa_label} "
            f"por {autor_nome or 'o responsável pela etapa'}.\n"
            f"Comentários: {comentarios}\n"
            f"Acesse: {link}\n"
        )
        assunto = f"POP devolvido na {etapa_label}: {pop['codigo']} ({pop['nome']})"
        return _enviar_email(elaborador["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 (email nunca quebra a transição)
        logger.warning(f"[pop_devolucao] Falha ao notificar Elaborador do POP {pop.get('codigo')}: {e}")
        return False


def send_papel_etapa_ativa_notification(
    supabase, pop: dict, setor: dict, *, papel: str, remetente_nome: str | None = None
) -> bool:
    """Notifica a pessoa recém-designada para a etapa ATIVA do POP (issue #156):
    a troca de papel antes da assinatura avisa quem passa a responder pela etapa.

    Reaproveita os emails de cada etapa (já buscam a pessoa certa e linkam para
    o lugar certo): `elaborador_id` → "novo POP para elaborar"; `revisor_id` →
    "aguardando sua revisão"; `validador_id` → "aguardando sua validação".
    Best-effort: falha de email nunca desfaz a edição."""
    if papel == "elaborador_id":
        return send_pop_criado_notification(supabase, pop, setor, criador_nome=remetente_nome)
    if papel == "revisor_id":
        return send_elaboracao_concluida_notification(supabase, pop, setor, elaborador_nome=remetente_nome)
    if papel == "validador_id":
        return send_validacao_pendente_notification(supabase, pop, setor, remetente_nome=remetente_nome)
    return False


def send_pop_publicado_notification(supabase, pop: dict, setor: dict, numero_versao: str | None = None) -> bool:
    """Notifica o criador do POP que a Versão foi publicada na Biblioteca
    (todas as assinaturas coletadas no ClickSign): o fim do ciclo (PRD #76).

    numero_versao vem do caller (o webhook tem a Versão em mãos). Isso evita
    re-consultar e, com múltiplas Versões (pós-Leva 1), pegar a errada.
    Best-effort como os demais: falha de email nunca desfaz a publicação.
    Os Signatários não recebem este email: a ClickSign os notifica.
    """
    try:
        from app.services.email_constants import get_logo_data_uri

        criador_id = pop.get("criado_por")
        if not criador_id:
            logger.warning(f"[pop_publicado] POP {pop.get('codigo')} sem criador registrado: notificação pulada")
            return False
        criador_q = (
            supabase.table("participantes").select("id, nome_completo, email").eq("id", criador_id).limit(1).execute()
        )
        criador = criador_q.data[0] if criador_q.data else None
        if not criador or not criador.get("email"):
            logger.warning(f"[pop_publicado] Criador {criador_id} sem email: notificação pulada")
            return False

        numero_versao = numero_versao or "1.0"

        link = f"{settings.frontend_url}/pops/biblioteca"
        template = jinja_env.get_template("email_pop_publicado.html")
        html = template.render(
            criador_nome=criador.get("nome_completo") or "Criador do POP",
            codigo=pop["codigo"],
            nome=pop["nome"],
            numero_versao=numero_versao,
            setor_nome=setor.get("nome") or "",
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = (
            f"O POP {pop['codigo']} ({pop['nome']}) versão {numero_versao} foi assinado por todos "
            f"os Signatários e está publicado na Biblioteca.\n"
            f"Acesse: {link}\n"
        )
        assunto = f"POP publicado: {pop['codigo']} ({pop['nome']})"
        return _enviar_email(criador["email"], assunto, html, texto)
    except Exception as e:  # noqa: BLE001 (email nunca quebra a publicação)
        logger.warning(f"[pop_publicado] Falha ao notificar criador do POP {pop.get('codigo')}: {e}")
        return False
