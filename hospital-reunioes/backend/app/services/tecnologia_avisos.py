"""Os avisos da entrega: Em producao e demonstracao pronta (issue #1560, PRD #1548).

Saem no sino (notificacao TECNOLOGIA, que abre a Demanda na aba) e por e-mail,
com o resumo do Documento do card. Quem chama sao os caminhos que ja garantem
"uma vez so": o carimbo de Em producao (`_carimbar_em_producao`, um
compare-and-swap na Etapa que o webhook de deploy e a reconciliacao dividem) e
a escrita do link novo de Demonstracao na sincronizacao. A carga do historico
grava as datas direto e nao passa por aqui.

Destino: no card do diretor, o autor; no card da Vitta, os Super admins ativos
que nao sao Desenvolvedores (sem login do GitHub), que e a diretoria. A Vitta
ja sabe o que subiu.

Best-effort: falha aqui nunca desfaz a Etapa nem o link gravados.
"""

from __future__ import annotations

import logging
from typing import Any

from app.dependencies import is_super_admin, selecionar_participantes
from app.services import tecnologia_email
from app.services.notificacao_service import criar_notificacao_tecnologia
from app.services.tecnologia import ORIGEM_VITTA, e_desenvolvedor, origem_da_demanda

logger = logging.getLogger(__name__)

AVISO_EM_PRODUCAO = "Entrou no ar"
AVISO_DEMONSTRACAO = "Demonstração pronta"


def destinatarios(supabase, demanda: dict[str, Any]) -> list[str]:
    """Quem o aviso da entrega alcanca nesta Demanda."""
    if origem_da_demanda(demanda) != ORIGEM_VITTA:
        autor = demanda.get("autor_id")
        return [str(autor)] if autor else []
    result = selecionar_participantes(
        supabase,
        "id, access_profile, is_super_admin, github_login, ativo",
        lambda q: q.eq("access_profile", "super_admin"),
    )
    return sorted(
        str(p["id"])
        for p in result.data or []
        if p.get("ativo") is not False and is_super_admin(p) and not e_desenvolvedor(p)
    )


def avisar(supabase, demanda: dict[str, Any], *, aviso: str) -> None:
    """Um aviso no sino e um e-mail para cada destinatario da Demanda."""
    try:
        for destinatario in destinatarios(supabase, demanda):
            criar_notificacao_tecnologia(
                supabase,
                destinatario_id=destinatario,
                titulo=aviso,
                mensagem=str(demanda.get("titulo") or "")[:80],
                demanda_id=str(demanda["id"]),
            )
            tecnologia_email.enviar_aviso_da_entrega(
                supabase, destinatario_id=destinatario, aviso=aviso, demanda=demanda
            )
    except Exception:  # noqa: BLE001 (aviso nunca desfaz a Etapa nem o link)
        logger.warning("[tecnologia] Falha ao avisar %r na Demanda %s.", aviso, demanda.get("id"), exc_info=True)
