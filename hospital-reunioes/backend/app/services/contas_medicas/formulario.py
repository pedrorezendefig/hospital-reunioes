"""Formulário em branco aprendido (issue #1132, PRD #1128).

Os formulários do MV (fisioterapia e o editor de documentos: anamnese de UTI,
sumário de alta, fonoaudiologia e os demais) imprimem as perguntas mesmo sem
resposta. Essas linhas são o modelo do formulário, iguais em quase todo
documento da mesma Família, e só gastam a leitura da IA.

Linha que aparece igual em 80% ou mais dos documentos da mesma Família de um
Prontuário é do modelo: entra em `cm_linha_formulario` (migration 117), com a
contagem de prontuários em que foi modelo, e sai do texto que vai à IA. As
linhas da tabela saem de todo Prontuário, então quem tem um formulário só se
beneficia do que os outros ensinaram.

O que a tabela guarda: só as linhas que foram modelo, nunca o texto livre do
prontuário, e já desidentificadas (o texto vem de `ler_prontuario`). Ficam de
fora do aprendizado e da remoção a primeira linha de cada documento (o título,
que diz à IA qual formulário é) e a linha com opção marcada (`[X]`), que é a
resposta e não a pergunta.

A Família do editor de documentos é uma só para muitos formulários; a chave do
aprendizado é ela com o título, para a anamnese não diluir o sumário de alta.

Nada daqui vai para log além de contagem: as linhas são texto do prontuário.
"""

from __future__ import annotations

import dataclasses
import logging
import unicodedata
from collections import Counter
from collections.abc import Sequence

import httpx
from postgrest.exceptions import APIError

from app.services.contas_medicas.marcacoes import MARCADA
from app.services.contas_medicas.prontuario import FAMILIAS_DE_FORMULARIO, Documento, Prontuario

logger = logging.getLogger(__name__)

TABELA = "cm_linha_formulario"
FRACAO_DO_MODELO = 0.8
# Com menos de 3 documentos, toda linha de um documento só já seria "80%".
MINIMO_DE_DOCUMENTOS = 3


def _chave(documento: Documento) -> str | None:
    if documento.familia not in FAMILIAS_DE_FORMULARIO or not documento.linhas:
        return None
    if documento.familia != "DOC_EDITOR":
        return documento.familia
    titulo = unicodedata.normalize("NFKD", documento.linhas[0]).encode("ascii", "ignore").decode()
    return f"DOC_EDITOR|{' '.join(titulo.upper().split())[:60]}"


def _candidatas(documento: Documento) -> set[str]:
    return {linha for linha in documento.linhas[1:] if MARCADA not in linha}


def _modelo(documentos: Sequence[Documento]) -> set[str]:
    if len(documentos) < MINIMO_DE_DOCUMENTOS:
        return set()
    vezes = Counter(linha for documento in documentos for linha in _candidatas(documento))
    return {linha for linha, n in vezes.items() if n >= FRACAO_DO_MODELO * len(documentos)}


def _aprender(supabase, deste: dict[str, set[str]], aprender: bool) -> dict[str, set[str]]:
    """As linhas de modelo de cada chave: as da tabela mais as deste Prontuário, que
    entram na tabela (ou somam um na contagem) quando `aprender`."""
    try:
        guardadas = (
            supabase.table(TABELA).select("familia,linha,contagem").in_("familia", list(deste)).execute().data or []
        )
        contagem = {(r["familia"], r["linha"]): r.get("contagem") or 0 for r in guardadas}
        novas = [
            {"familia": chave, "linha": linha, "contagem": contagem.get((chave, linha), 0) + 1}
            for chave, linhas in deste.items()
            for linha in sorted(linhas)
        ]
        if aprender and novas:
            supabase.table(TABELA).upsert(novas, on_conflict="familia,linha").execute()
    except (APIError, httpx.HTTPError) as erro:
        # Sem a tabela (migration 117 ainda não aplicada) ou com o banco fora, a leitura
        # segue com o que este Prontuário ensinou: a remoção é economia, não conferência.
        logger.warning("[ContasMedicas] Formulario em branco sem a tabela: %s", type(erro).__name__)
        return deste
    modelo = {chave: set(linhas) for chave, linhas in deste.items()}
    for chave, linha in contagem:
        modelo.setdefault(chave, set()).add(linha)
    return modelo


def sem_formulario_em_branco(supabase, prontuario: Prontuario, *, aprender: bool) -> Prontuario:
    """O Prontuário com as linhas de modelo fora dos documentos de formulário.
    `aprender` falso (o mesmo arquivo lido de novo) só remove, sem somar na contagem."""
    por_chave: dict[str, list[Documento]] = {}
    for documento in prontuario.documentos:
        if chave := _chave(documento):
            por_chave.setdefault(chave, []).append(documento)
    if not por_chave:
        return prontuario

    modelo = _aprender(supabase, {chave: _modelo(docs) for chave, docs in por_chave.items()}, aprender)

    def limpo(documento: Documento) -> Documento:
        chave = _chave(documento)
        if not chave or not modelo.get(chave):
            return documento
        titulo, *corpo = documento.linhas
        fica = tuple(linha for linha in corpo if linha not in modelo[chave])
        return dataclasses.replace(documento, linhas=(titulo, *fica))

    return dataclasses.replace(prontuario, documentos=tuple(limpo(d) for d in prontuario.documentos))
