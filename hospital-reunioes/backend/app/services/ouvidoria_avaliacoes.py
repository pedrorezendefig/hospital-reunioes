"""Avaliação do QR da Ouvidoria (issue #1622, ADR 0086).

O cartaz abre uma nota de 1 a 5, com os motivos e um comentário opcionais. A
avaliação é dado de gestão, não caso: não tem protocolo, prazo nem fila, e não
guarda nada de quem avaliou (sem IP, sem aparelho, sem contato). Quem pede
retorno segue para a Manifestação guiada, e o caso fica ligado à avaliação,
menos quando a pessoa escolhe o anonimato (decisão 3).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TABELA = "ouvidoria_avaliacoes"

# Os oito motivos da tela N2 (seção 4.1 da especificação da Diretoria), na
# ordem da tela. A lista vive aqui e no CHECK da migration 140, e um teste
# confere que as duas batem.
MOTIVOS: tuple[str, ...] = (
    "atencao_equipe",
    "tempo_espera",
    "informacao_recebida",
    "limpeza",
    "conforto",
    "atendimento_medico",
    "atendimento_enfermagem",
    "recepcao",
)

TAMANHO_DO_COMENTARIO = 500

# A nota que pergunta se a pessoa quer retorno (tela N3): de 1 a 3. A 4 e a 5
# oferecem o elogio, que não é pedido de retorno.
NOTA_QUE_PERGUNTA_RETORNO = 3


def gravar(supabase, ponto: dict, nota: int, motivos: list[str], comentario: str | None) -> dict | None:
    """Grava a avaliação de um cartaz ativo e devolve a linha, ou None se o
    banco recusou. Só o ponto, a nota, os motivos e o comentário: nada que
    identifique quem avaliou entra aqui, nem por engano de quem chama."""
    linha = {
        "ponto_id": ponto["id"],
        "canal": "qr",
        "nota": nota,
        "motivos": motivos,
        "comentario": comentario,
    }
    result = supabase.table(TABELA).insert(linha).execute()
    return result.data[0] if result.data else None


def para_ligar(supabase, avaliacao_id: str | None, cartaz: dict | None) -> dict | None:
    """A avaliação que o caso novo pode carregar, ou None.

    Só a nota do mesmo cartaz, e só enquanto nenhum caso a carrega: o id solto
    vindo da página não pendura o caso na avaliação de outro lugar, nem liga
    dois casos à mesma nota. Quem chama já descartou o anônimo (ADR 0086,
    decisão 3). Falha de leitura vira None: perder a ligação é ruim, perder a
    manifestação é pior."""
    if not avaliacao_id or not cartaz:
        return None
    try:
        achadas = supabase.table(TABELA).select("id, ponto_id, nota").eq("id", avaliacao_id).execute().data or []
        if not achadas or achadas[0].get("ponto_id") != cartaz.get("id"):
            return None
        ja_ligada = (
            supabase.table("ouvidoria_protocolos").select("id").eq("avaliacao_id", avaliacao_id).execute().data
        )
    except Exception:
        logger.warning("[Ouvidoria] Falha ao conferir a avaliação do caso; o caso entra sem a ligação")
        return None
    return None if ja_ligada else achadas[0]


def marcar_retorno(supabase, avaliacao: dict) -> None:
    """Marca o pedido de retorno na nota de 1 a 3 que virou caso. A 4 e a 5
    seguem para o elogio, que não é pedido de retorno. Falha aqui não desfaz o
    caso, que já tem protocolo."""
    if avaliacao.get("nota", 0) > NOTA_QUE_PERGUNTA_RETORNO:
        return
    try:
        supabase.table(TABELA).update({"pediu_retorno": True}).eq("id", avaliacao["id"]).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao marcar o pedido de retorno da avaliação")
