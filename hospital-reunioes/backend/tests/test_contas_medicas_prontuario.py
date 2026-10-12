"""Leitura do Prontuário por código, a estrutura (issue #1117, PRD #1113, ADR 0070).

As fixtures são sintéticas, em texto, uma por Família de documento, no layout do
MV (`tests/fixtures/contas_medicas/prontuario/`). A paciente é fictícia: ANTÔNIA
MELO FARIAS, mãe JOSEFA RIBEIRO COSTA, Atendimento 31245; o pronto-socorro que
vem no mesmo arquivo é o Atendimento 31190. PDF real nunca entra em teste.

O montador abaixo faz o papel do extrator: junta as páginas das fixtures na
ordem pedida e põe em cada uma o rodapé global do MV, "Impressão de Prontuário -
Página N de T".
"""

from pathlib import Path

import pytest

from app.services.contas_medicas.prontuario import ErroLeitura, ler_prontuario

FIXTURES = Path(__file__).parent / "fixtures" / "contas_medicas" / "prontuario"
QUEBRA = "<<<QUEBRA DE PÁGINA>>>"
ATENDIMENTO = "31245"


def paginas_da_fixture(nome: str) -> list[str]:
    return [p.strip("\n") for p in (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8").split(QUEBRA)]


def montar(*partes: str | list[str], total_no_rodape: int | None = None) -> list[str]:
    """Cada parte é o nome de uma fixture ou uma lista de páginas já prontas."""
    paginas: list[str] = []
    for parte in partes:
        paginas += paginas_da_fixture(parte) if isinstance(parte, str) else parte
    total = total_no_rodape or len(paginas)
    return [
        f"{texto}\n\n          Impressão de Prontuário - Página {n} de {total}"
        for n, texto in enumerate(paginas, start=1)
    ]


def test_rodape_com_total_diferente_do_numero_de_paginas_e_arquivo_incompleto():
    paginas = montar("capa", "evolucao", "anotacao_enf", total_no_rodape=5)

    with pytest.raises(ErroLeitura, match="arquivo incompleto"):
        ler_prontuario(paginas, ATENDIMENTO)


def test_rodape_com_total_igual_ao_numero_de_paginas_le_o_prontuario():
    paginas = montar("capa", "evolucao", "anotacao_enf")

    assert ler_prontuario(paginas, ATENDIMENTO).total_paginas == 3
