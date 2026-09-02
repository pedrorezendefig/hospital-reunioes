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

logger = logging.getLogger(__name__)

# O rótulo que abre a observação do movimento. Ele é o que separa a resposta
# vinda do portal do setor de qualquer outra transição para "respondido" que o
# ouvidor faça pelo painel com observação própria: sem a marca, o histórico
# listaria as duas coisas como se fossem ciclos de resposta da área.
MARCA = "Resposta da área pelo portal do setor"
_SEPARADOR = ": "

# O que fica no lugar do texto quando o movimento é anterior a esta fatia. Até
# ela, o portal gravava só o rótulo, sem separador e sem conteúdo. Descartar
# esses movimentos faria o histórico começar do zero justo nos casos já
# devolvidos em produção (os que motivaram a #370), e ainda numeraria a segunda
# resposta como se fosse a primeira.
TEXTO_NAO_REGISTRADO = "(texto não registrado: resposta anterior ao registro do conteúdo na trilha)"

CAMPOS_MOVIMENTO = "ocorrido_em, autor_nome, observacao, estado_novo"

# O mínimo que faz a resposta da área dizer o que foi FEITO (RN-61, issue
# #482). Resposta de uma palavra chega ao ouvidor como caso "respondido" sem
# conteúdo, e tirá-la de lá custa um ciclo inteiro de devolução por
# insuficiência. A regra vive aqui, e não na tela, porque a tela não é a única
# porta: o link do email aceita POST de qualquer cliente.
MINIMO_DE_CARACTERES = 20

RECUSA_CURTA = (
    f"Escreva o que o setor fez para corrigir: a resposta precisa ter pelo menos {MINIMO_DE_CARACTERES} caracteres."
)


def motivo_de_recusa(texto: str) -> str | None:
    """Por que este texto não vale como resposta da área, ou None quando vale.

    Conta o texto já aparado: espaço em volta não é o que foi feito. O texto
    devolvido é o que o responsável lê, então ele diz o mínimo que falta
    alcançar, e não que a entrada é inválida."""
    return RECUSA_CURTA if len(texto.strip()) < MINIMO_DE_CARACTERES else None


def observacao_da_resposta(texto: str) -> str:
    """A observação do movimento que carrega o texto da resposta.

    O rótulo continua na frente porque a trilha é lida por humano: um movimento
    que mostrasse só o texto do setor não diria o que aconteceu ali."""
    return f"{MARCA}{_SEPARADOR}{texto}"


def _texto_da_observacao(observacao: str | None) -> str | None:
    """O texto da resposta dentro da observação, ou None quando o movimento não
    é uma resposta do portal do setor.

    Movimento gravado antes desta fatia casa o rótulo exato, sem separador, e
    conta como ciclo com o texto ausente declarado: o ciclo existiu."""
    if not observacao:
        return None
    if observacao == MARCA:
        return TEXTO_NAO_REGISTRADO
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
    conseguir abrir o caso mesmo sem ele. A captura é larga de propósito:
    timeout e erro de conexão do httpx são a falha transitória mais provável
    aqui, e são justamente os que `APIError` não pega."""
    try:
        result = (
            supabase.table("ouvidoria_movimentos")
            .select(CAMPOS_MOVIMENTO)
            .eq("manifestacao_id", manifestacao_id)
            .eq("estado_novo", "respondido")
            .order("ocorrido_em")
            .execute()
        )
    except Exception:
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
