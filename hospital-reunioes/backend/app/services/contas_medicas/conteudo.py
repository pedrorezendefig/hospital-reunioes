"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (`prontuario.ler_prontuario`, #1117),
o código lê o que sustenta cobrança sem passar pela IA: a prescrição, o balanço
hídrico, as glicemias, a internação e a alta, o setor de cada dia com as
transferências, a descrição cirúrgica, a ficha anestésica e a guia TISS.

Entra o mesmo texto por página que a estrutura leu e o Prontuário que ela devolveu;
as páginas de cada documento são lidas pelo número. Função pura: sem banco, sem
rede, sem log (o texto do prontuário nunca vai para log, ADR 0070, decisão 8).
Os campos de texto livre que saem daqui (observação da prescrição, por exemplo)
não estão desidentificados: quem os mandar à IA passa por `desidentificar`.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.contas_medicas.prescricao import ItemConsolidado, Prescricao, consolidar, ler_itens
from app.services.contas_medicas.prontuario import Documento, Prontuario


@dataclass(frozen=True)
class Conteudo:
    prescricoes: tuple[Prescricao, ...]
    prescricao_consolidada: tuple[ItemConsolidado, ...]


def _paginas(textos: Sequence[str], documento: Documento) -> list[tuple[int, str]]:
    return [(n, textos[n - 1]) for n in documento.paginas]


def ler_conteudo(texto_por_pagina: Sequence[str | None], prontuario: Prontuario) -> Conteudo:
    textos = [texto or "" for texto in texto_por_pagina]
    prescricoes = tuple(
        Prescricao(
            data=d.data,
            hora=d.hora,
            subtipo=d.subtipo,
            setor=d.setor,
            paginas=d.paginas,
            itens=tuple(ler_itens(_paginas(textos, d))),
        )
        for d in prontuario.documentos
        if d.familia == "PRESCRICAO"
    )
    return Conteudo(prescricoes=prescricoes, prescricao_consolidada=tuple(consolidar(prescricoes)))
