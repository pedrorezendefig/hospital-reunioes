"""O aviso da Conversa da Demanda por e-mail (issue #1538, ADR 0083, decisão 8).

Sai junto com o aviso do sino, para o mesmo destinatário: o diretor não fica
com o app aberto. Leva o título da Demanda, quem escreveu e o link que abre a
Demanda na aba Tecnologia. Não leva número de issue nem link do GitHub: o
diretor não está no GitHub e o repositório é público.

Best-effort como os demais e-mails do app: falha aqui nunca desfaz a mensagem
gravada nem o aviso do sino.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from app.config import settings
from app.services.email_service import _enviar_email, jinja_env

logger = logging.getLogger(__name__)


def link_da_demanda(demanda_id: str) -> str:
    """O mesmo endereço que o clique no sino abre."""
    return f"{settings.frontend_url}/admin/tecnologia?demanda={quote(str(demanda_id), safe='')}"


def enviar_aviso_da_conversa(supabase, *, destinatario_id: str, aviso: str, autor_nome: str, demanda: dict) -> bool:
    """Um e-mail para `destinatario_id` com o `aviso` do sino ("Fulano mencionou
    você" ou "Fulano escreveu na Demanda"). `False` quando não saiu."""
    try:
        from app.services.email_constants import get_logo_data_uri

        linhas = (
            supabase.table("participantes").select("id, nome_completo, email").eq("id", destinatario_id).execute().data
        )
        destinatario = linhas[0] if linhas else None
        if not destinatario or not destinatario.get("email"):
            logger.warning(f"[tecnologia_conversa] {destinatario_id} sem e-mail: aviso por e-mail pulado")
            return False

        titulo = str(demanda.get("titulo") or "Demanda sem título")
        link = link_da_demanda(demanda["id"])
        html = jinja_env.get_template("email_tecnologia_conversa.html").render(
            destinatario_nome=destinatario.get("nome_completo") or "",
            aviso=aviso,
            autor_nome=autor_nome,
            titulo=titulo,
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = f"{aviso}.\n\nDemanda: {titulo}\nQuem escreveu: {autor_nome}\n\nPara ler e responder: {link}\n"
        return _enviar_email(destinatario["email"], f"{aviso}: {titulo}", html, texto)
    except Exception as e:  # noqa: BLE001 (e-mail nunca desfaz a mensagem nem o sino)
        logger.warning(f"[tecnologia_conversa] Falha no e-mail para {destinatario_id}: {e}")
        return False


# O rotulo em negrito que abre uma linha do bloco no formato fixo da ADR 0084
# ("**O que muda:**", "**O que você precisa saber:**"): moldura, e nao conteudo,
# como no `documentoDoBloco` da tela.
_ROTULO_DO_BLOCO = re.compile(r"^\*\*[^*]+:\*\*\s*")
_MARCADOR_DE_ITEM = re.compile(r"^[-*]\s+")


def resumo_do_documento(texto: str | None) -> tuple[str, list[str]]:
    """A frase e os topicos do Documento do card, lidos do bloco "Para o
    diretor" guardado na Demanda (issue #1560). A mesma separacao da tela
    (`documentoDoBloco`): item de lista e topico, o resto e a frase, sem o
    rotulo em negrito. Sem IA: o texto nao e reescrito."""
    frase: list[str] = []
    topicos: list[str] = []
    for bruta in str(texto or "").splitlines():
        linha = bruta.strip()
        if not linha:
            continue
        if _MARCADOR_DE_ITEM.match(linha):
            topicos.append(_MARCADOR_DE_ITEM.sub("", linha).replace("**", ""))
            continue
        sobra = _ROTULO_DO_BLOCO.sub("", linha).replace("**", "").strip()
        if sobra:
            frase.append(sobra)
    return " ".join(frase), topicos


def enviar_aviso_da_entrega(supabase, *, destinatario_id: str, aviso: str, demanda: dict) -> bool:
    """O e-mail do aviso de Em producao ou de demonstracao pronta (issue
    #1560): o `aviso`, o titulo, a frase e os topicos do Documento do card e o
    link que abre a Demanda. `False` quando nao saiu."""
    try:
        from app.services.email_constants import get_logo_data_uri

        linhas = (
            supabase.table("participantes").select("id, nome_completo, email").eq("id", destinatario_id).execute().data
        )
        destinatario = linhas[0] if linhas else None
        if not destinatario or not destinatario.get("email"):
            logger.warning(f"[tecnologia_entrega] {destinatario_id} sem e-mail: aviso por e-mail pulado")
            return False

        titulo = str(demanda.get("titulo") or "Demanda sem título")
        frase, topicos = resumo_do_documento(demanda.get("o_que_muda"))
        link = link_da_demanda(demanda["id"])
        html = jinja_env.get_template("email_tecnologia_entrega.html").render(
            destinatario_nome=destinatario.get("nome_completo") or "",
            aviso=aviso,
            titulo=titulo,
            frase=frase,
            topicos=topicos,
            link=link,
            logo_base64=get_logo_data_uri(),
        )
        texto = "\n".join(
            [
                f"{aviso}: {titulo}",
                "",
                *([frase, ""] if frase else []),
                *[f"- {t}" for t in topicos],
                *([""] if topicos else []),
                f"Para ver o pedido: {link}",
                "",
            ]
        )
        return _enviar_email(destinatario["email"], f"{aviso}: {titulo}", html, texto)
    except Exception as e:  # noqa: BLE001 (e-mail nunca desfaz a Etapa nem o sino)
        logger.warning(f"[tecnologia_entrega] Falha no e-mail para {destinatario_id}: {e}")
        return False
