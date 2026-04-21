"""
Service de notificações.

Responsável por criar notificações quando:
- Um usuário é mencionado em um comentário
- Um participante é atribuído como responsável de uma pendência
- Alguém comenta em uma pendência (notifica o responsável)
"""
import logging

logger = logging.getLogger(__name__)


def criar_notificacao_mencao(
    supabase,
    id_acao: str,
    autor_nome: str,
    mencionado_id: str,
    descricao_acao: str,
) -> None:
    """Cria notificação de menção para o participante mencionado."""
    try:
        supabase.table("notificacoes").insert({
            "destinatario_id": mencionado_id,
            "tipo": "MENCAO",
            "titulo": f"{autor_nome} mencionou você",
            "mensagem": f"Menção em: {descricao_acao[:80]}",
            "referencia_id": id_acao,
        }).execute()
        logger.info(f"[Notificacao] Menção criada: {autor_nome} → {mencionado_id} em {id_acao}")
    except Exception as e:
        logger.error(f"[Notificacao] Erro ao criar notificação de menção: {e}")


def criar_notificacao_responsavel(
    supabase,
    id_acao: str,
    descricao_acao: str,
    responsavel_id: str,
    atribuido_por: str,
) -> None:
    """Cria notificação para o participante quando ele é atribuído como responsável."""
    try:
        supabase.table("notificacoes").insert({
            "destinatario_id": responsavel_id,
            "tipo": "RESPONSAVEL_ATRIBUIDO",
            "titulo": "Você foi atribuído a uma pendência",
            "mensagem": f"{atribuido_por} te definiu como responsável: {descricao_acao[:80]}",
            "referencia_id": id_acao,
        }).execute()
        logger.info(f"[Notificacao] Responsável atribuído: {atribuido_por} → {responsavel_id} em {id_acao}")
    except Exception as e:
        logger.error(f"[Notificacao] Erro ao criar notificação de responsável: {e}")


def criar_notificacao_comentario(
    supabase,
    id_acao: str,
    autor_nome: str,
    responsavel_id: str,
    autor_id: str,
) -> None:
    """Cria notificação para o responsável quando alguém comenta na pendência (se não for o próprio)."""
    if autor_id == responsavel_id:
        return

    try:
        supabase.table("notificacoes").insert({
            "destinatario_id": responsavel_id,
            "tipo": "COMENTARIO",
            "titulo": f"{autor_nome} comentou",
            "mensagem": f"Novo comentário na pendência {id_acao}",
            "referencia_id": id_acao,
        }).execute()
        logger.info(f"[Notificacao] Comentário: {autor_nome} → responsavel {responsavel_id} em {id_acao}")
    except Exception as e:
        logger.error(f"[Notificacao] Erro ao criar notificação de comentário: {e}")
