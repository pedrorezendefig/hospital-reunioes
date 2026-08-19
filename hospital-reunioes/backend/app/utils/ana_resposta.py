"""Regra de tamanho das respostas de lista da API da Ana (ADR 0032).

A plataforma que hospeda a Ana (fazer.ai agents) corta o corpo de TODA resposta
de HTTP tool em 4.000 caracteres antes de entregar ao modelo: limite fixo no
runtime dela (`maxResponseChars` em `src/graph/tools/http.ts`), sem env nem
configuração. O corte é mudo, e a Ana conclui a partir do que chegou, afirmando
que o item não existe.

Este módulo é o ponto único onde a regra vive. Todo endpoint de `/api/ana/*`
que devolva lista chama `montar_resposta`: nenhum deles mede tamanho nem monta
envelope por conta própria (decisão 8 do ADR).
"""

from __future__ import annotations

import json
import re
import unicodedata

from fastapi.encoders import jsonable_encoder

# Fato externo: limite fixo do runtime da plataforma da Ana. Único ponto a
# ajustar se a plataforma mudar.
TETO_CLIENTE_CHARS = 4000

# O teto do cliente com folga (a plataforma pode acrescentar cabeçalho ao corpo
# que entrega ao modelo). Nenhuma resposta de lista sai maior que isto.
LIMITE_CORPO_CHARS = TETO_CLIENTE_CHARS - 500

# Do mais rico ao mais magro. O índice é o piso: se nem ele couber, a resposta
# sai assim mesmo, com todas as linhas (decisão 4 do ADR: tirar campo é
# permitido, tirar linha nunca).
MODOS = ("completo", "resumo", "indice")


def _normalizar(texto: str) -> str:
    """Sem acento, em caixa baixa e com a pontuação virando espaço.

    `obstetricia` acha "Obstetrícia"; `raio x` acha "Raio-X (RX)".
    """
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^0-9a-z]+", " ", sem_acento.lower()).strip()


def filtrar_por_termo(linhas: list[dict], campo: str, termo: str | None) -> list[dict]:
    """Devolve as linhas cujo `campo` contém todas as palavras do termo.

    Termo ausente, vazio ou só com espaços significa SEM FILTRO: o cliente da
    Ana interpola variável não preenchida como string vazia, em silêncio, e a
    API não pode ler isso como busca por vazio (decisão 1 do ADR 0032).
    """
    palavras = _normalizar(termo or "").split()
    if not palavras:
        return linhas
    return [linha for linha in linhas if all(p in _normalizar(str(linha.get(campo) or "")) for p in palavras)]


def _projetar(linhas: list[dict], campos: tuple[str, ...]) -> list[dict]:
    return [{campo: linha.get(campo) for campo in campos} for linha in linhas]


def _nomes(linhas: list[dict], campos: tuple[str, ...]) -> list[str]:
    """O índice é só o nome de cada registro, em texto.

    Repetir o nome do campo em cada linha é o que faz o índice estourar quando a
    tabela cresce. Quando o nome do registro é um par (convênio e especialidade,
    porque nenhum dos dois sozinho identifica a linha), os dois vêm juntos.
    """
    return [" / ".join(str(linha.get(campo) or "") for campo in campos) for linha in linhas]


def _tamanho_do_corpo(envelope: dict) -> int:
    """Mede o corpo final serializado, do mesmo jeito que sai na resposta."""
    return len(json.dumps(jsonable_encoder(envelope), ensure_ascii=False, separators=(",", ":")))


def montar_resposta(
    chave: str,
    linhas: list[dict],
    todas: list[dict],
    *,
    campos: dict[str, tuple[str, ...]],
    dicas: dict[str, str],
    caveat_campo: str | None = None,
) -> dict:
    """Monta o envelope da lista no degrau mais rico que couber no limite.

    `linhas` são os registros já filtrados; `todas` são os da tabela sem filtro,
    usados para dizer à Ana quais nomes existem quando o filtro não acha nada.
    """
    if not linhas and todas:
        # Sem medição de propósito: `disponiveis` já é o degrau mais magro que
        # existe (só os nomes, sem valor), então não há para onde descer. Vale o
        # mesmo piso do índice, e pela mesma razão: cortar nomes faria a Ana
        # reperguntar por um nome que ela não recebeu.
        return {
            chave: [],
            "modo": "completo",
            "dica": dicas["vazio"],
            "disponiveis": _nomes(todas, campos["indice"]),
        }

    # O aviso é editável linha a linha no admin, então os textos podem diferir.
    # Um só no envelope mentiria sobre as outras linhas (decisão 6 do ADR: o
    # aviso não pode se perder), por isso só sobe ao envelope quando é um só.
    avisos = {str(linha[caveat_campo]) for linha in linhas if caveat_campo and linha.get(caveat_campo)}

    envelope: dict = {}
    for modo in MODOS:
        campos_do_modo = campos[modo]
        if caveat_campo and modo == "resumo" and len(avisos) > 1:
            # Textos diferentes e o resumo carrega valor: cada linha leva o seu.
            # Se não couber, o degrau cai para o índice, que não tem valor
            # nenhum, então nenhum valor sai sem o aviso que é dele.
            campos_do_modo = campos_do_modo + (caveat_campo,)
        itens = _nomes(linhas, campos_do_modo) if modo == "indice" else _projetar(linhas, campos_do_modo)
        envelope = {chave: itens, "modo": modo, "dica": dicas[modo]}
        if modo != "completo" and len(avisos) == 1:
            envelope[caveat_campo] = next(iter(avisos))
        if _tamanho_do_corpo(envelope) <= LIMITE_CORPO_CHARS:
            return envelope
    return envelope
