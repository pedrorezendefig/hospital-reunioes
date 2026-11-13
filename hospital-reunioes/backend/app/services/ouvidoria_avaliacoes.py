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
