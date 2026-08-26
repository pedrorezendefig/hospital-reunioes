"""Memória dos ciclos de resposta da área (issue #374, PRD #318, histórias 5 e 22).

A resposta do setor vive numa coluna única do caso (`resposta_da_area`), e o
portal a sobrescreve inteira a cada resposta nova. Depois da devolução por
insuficiência (#334), isso apagava justamente o texto que o ouvidor precisa
reler para julgar se a segunda resposta melhorou.

O histórico nasce da trilha imutável (`ouvidoria_movimentos`, migration 064),
não de tabela nova: nada sobrescreve o que já foi gravado ali, e contar ciclos
é contar movimentos. Este módulo é o único lugar que sabe como o texto entra e
sai do movimento: quem escreve chama `observacao_da_resposta`, quem lê chama
`historico`, e a codificação no meio não vaza para as rotas.
"""

from __future__ import annotations

import logging

from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

# O rótulo que abre a observação do movimento. Ele é o que separa a resposta
# vinda do portal do setor de qualquer outra transição para "respondido" que o
# ouvidor faça pelo painel com observação própria: sem a marca, o histórico
# listaria as duas coisas como se fossem ciclos de resposta da área.
MARCA = "Resposta da área pelo portal do setor"
_SEPARADOR = ": "

CAMPOS_MOVIMENTO = "ocorrido_em, autor_nome, observacao, estado_novo"


def observacao_da_resposta(texto: str) -> str:
    """A observação do movimento que carrega o texto da resposta.

    O rótulo continua na frente porque a trilha é lida por humano: um movimento
    que mostrasse só o texto do setor não diria o que aconteceu ali."""
    return f"{MARCA}{_SEPARADOR}{texto}"


def _texto_da_observacao(observacao: str | None) -> str | None:
    """O texto da resposta dentro da observação, ou None quando o movimento não
    é uma resposta do portal do setor."""
    if not observacao:
        return None
    prefixo = MARCA + _SEPARADOR
    if not observacao.startswith(prefixo):
        return None
    return observacao[len(prefixo) :]


def historico(supabase, manifestacao_id: str) -> list[dict]:
    """Os ciclos de resposta do caso, do mais antigo para o mais novo.

    Uma entrada por resposta do setor, com quando chegou, quem respondeu e o
    que disse. Caso devolvido duas vezes tem três entradas, e a primeira
    continua legível depois de as outras chegarem: é a trilha que guarda, não a
    coluna do caso.

    Falha de leitura devolve lista vazia em vez de derrubar o Dossiê: o
    histórico é contexto ao lado da resposta corrente, e o ouvidor precisa
    conseguir abrir o caso mesmo sem ele."""
    try:
        result = (
            supabase.table("ouvidoria_movimentos")
            .select(CAMPOS_MOVIMENTO)
            .eq("manifestacao_id", manifestacao_id)
            .eq("estado_novo", "respondido")
            .order("ocorrido_em")
            .execute()
        )
    except APIError:
        logger.warning("Falha ao ler o histórico de respostas da manifestação %s", manifestacao_id)
        return []

    ciclos = []
    for row in result.data or []:
        texto = _texto_da_observacao(row.get("observacao"))
        if texto is None:
            continue
        ciclos.append(
            {
                "respondida_em": row.get("ocorrido_em"),
                "respondida_por_nome": row.get("autor_nome"),
                "resposta": texto,
            }
        )
    return ciclos
