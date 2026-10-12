"""Leitura do Prontuário por código: a estrutura (issue #1117, PRD #1113, ADR 0070).

Entra o texto de cada página do PDF "Impressão de Prontuário" do MV, na ordem do
arquivo, e o número do Atendimento da Conta. Sai a estrutura que o resto do
Motor usa. Função pura: não lê banco, não fala com rede, não escreve log. O texto
do prontuário nunca vai para log (ADR 0070, decisão 8), e por isso este módulo
não tem logger.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass


class ErroLeitura(Exception):
    """Leitura impossível. A mensagem é a frase que a faturista vê na Situação Erro
    e nunca carrega texto do prontuário."""


@dataclass(frozen=True)
class Prontuario:
    atendimento: str
    total_paginas: int


# Rodapé global de toda página. Em algumas Famílias a linha quebra em duas, por isso
# o espaço entre as palavras aceita quebra de linha (adendo v1.2, item 3).
_RODAPE_GLOBAL = re.compile(r"Impress[ãa]o\s+de\s+Prontu[áa]rio\s*-\s*P[áa]gina\s+(\d+)\s+de\s+(\d+)")


def ler_prontuario(texto_por_pagina: Sequence[str | None], atendimento: str | int) -> Prontuario:
    paginas = [texto or "" for texto in texto_por_pagina]
    _conferir_integridade(paginas)
    return Prontuario(atendimento=str(atendimento), total_paginas=len(paginas))


def _conferir_integridade(paginas: list[str]) -> None:
    """O T do rodapé "Página N de T" tem de ser o número de páginas do arquivo."""
    totais = {int(m.group(2)) for texto in paginas for m in _RODAPE_GLOBAL.finditer(texto)}
    if any(total != len(paginas) for total in totais):
        declarado = max(totais)
        raise ErroLeitura(
            f"Prontuário com arquivo incompleto: o rodapé indica {declarado} páginas e vieram {len(paginas)}."
        )
