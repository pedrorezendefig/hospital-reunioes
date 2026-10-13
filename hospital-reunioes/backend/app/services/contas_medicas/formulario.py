"""Formulário em branco: esqueleto fixo e aprendido (issue #1132, PRD #1128).

Os formulários do MV (fisioterapia e o editor de documentos: anamnese de UTI,
sumário de alta, fonoaudiologia e os demais) imprimem as perguntas mesmo sem
resposta. Essas linhas são o modelo do formulário, iguais em quase todo
documento da mesma Família, e só gastam a leitura da IA.

O esqueleto dos formulários conhecidos é fixo (`esqueleto_formulario`) e sai do
texto desde o primeiro Prontuário, com ou sem o banco. O aprendizado abaixo é o
complemento, para formulário novo ou alterado.

Linha que aparece igual em 80% ou mais dos documentos da mesma Família de um
Prontuário é candidata a modelo: entra em `cm_linha_formulario` (migration 117)
com a contagem de prontuários em que foi candidata. Só sai do texto que vai à
IA quando foi candidata em `MINIMO_DE_PRONTUARIOS` prontuários ou mais, e aí
sai de todo Prontuário, inclusive do que tem um formulário só. Um Prontuário
sozinho não basta: a evolução copiada de um dia para outro também se repete em
todos os documentos de um paciente, e é resposta, não pergunta.

O que a tabela guarda: as candidatas, já desidentificadas (o texto vem de
`ler_prontuario`); uma resposta repetida dentro de um paciente pode entrar com
contagem 1, mas não sai de texto nenhum. Ficam de fora do aprendizado e da
remoção a primeira linha de cada documento (o título, que diz à IA qual
formulário é) e a linha com opção marcada (`[X]`), que é a resposta.

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

from app.services.contas_medicas.esqueleto_formulario import ESQUELETO
from app.services.contas_medicas.marcacoes import MARCADA
from app.services.contas_medicas.prontuario import FAMILIAS_DE_FORMULARIO, Documento, Prontuario
from app.services.paginacao import LeituraIncompletaError, ler_tudo

logger = logging.getLogger(__name__)

TABELA = "cm_linha_formulario"
FRACAO_DO_MODELO = 0.8
# Com menos de 3 documentos, toda linha de um documento só já seria "80%".
MINIMO_DE_DOCUMENTOS = 3
# Prontuários (pacientes) em que a linha foi candidata para sair do texto.
MINIMO_DE_PRONTUARIOS = 3


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


_CAUSAS = {
    "42P01": "tabela ausente (migration 117)",
    "PGRST205": "tabela ausente (migration 117)",
    "42P10": "sem unique (familia, linha) para o upsert",
}


def _causa(erro: APIError | httpx.HTTPError | LeituraIncompletaError) -> str:
    """O motivo do aviso, só com o código: a mensagem do banco pode trazer a linha."""
    if isinstance(erro, LeituraIncompletaError):
        return "leitura da tabela incompleta (teto de linhas)"
    if isinstance(erro, httpx.HTTPError):
        return f"banco fora ({type(erro).__name__})"
    return f"{_CAUSAS.get(erro.code, 'erro do banco')} (codigo {erro.code})"


def _aprender(supabase, deste: dict[str, set[str]], aprender: bool) -> dict[str, set[str]]:
    """As linhas de modelo de cada chave: as candidatas em `MINIMO_DE_PRONTUARIOS` ou
    mais, contando este. Com `aprender`, as deste Prontuário entram na tabela (ou somam
    um na contagem)."""
    try:
        # Paginada: o PostgREST corta no `max_rows` sem aviso, e a linha que não
        # voltasse teria a contagem reescrita para 1 no upsert abaixo.
        guardadas = ler_tudo(
            lambda: supabase.table(TABELA).select("id,familia,linha,contagem").in_("familia", list(deste)).order("id"),
            rotulo="linhas de formulario aprendidas",
        )
        contagem = {(r["familia"], r["linha"]): r.get("contagem") or 0 for r in guardadas}
        if aprender:
            for chave, linhas in deste.items():
                for linha in linhas:
                    contagem[(chave, linha)] = contagem.get((chave, linha), 0) + 1
            novas = [
                {"familia": chave, "linha": linha, "contagem": contagem[(chave, linha)]}
                for chave, linhas in deste.items()
                for linha in sorted(linhas)
            ]
            if novas:
                supabase.table(TABELA).upsert(novas, on_conflict="familia,linha").execute()
    except (APIError, httpx.HTTPError, LeituraIncompletaError) as erro:
        # A remoção é economia, não conferência: sem o aprendizado sai só o esqueleto fixo.
        # Com a leitura incompleta, nada é gravado, para não reescrever contagem que não voltou.
        logger.warning("[ContasMedicas] Formulario em branco sem aprendizado: %s", _causa(erro))
        return {}
    modelo: dict[str, set[str]] = {}
    for (chave, linha), n in contagem.items():
        if n >= MINIMO_DE_PRONTUARIOS:
            modelo.setdefault(chave, set()).add(linha)
    return modelo


def sem_formulario_em_branco(supabase, prontuario: Prontuario, *, aprender: bool) -> Prontuario:
    """O Prontuário com o esqueleto fixo e as linhas de modelo aprendidas fora dos
    documentos de formulário. `aprender` falso (o mesmo arquivo lido de novo) só remove, sem somar na contagem."""
    por_chave: dict[str, list[Documento]] = {}
    for documento in prontuario.documentos:
        if chave := _chave(documento):
            por_chave.setdefault(chave, []).append(documento)
    if not por_chave:
        return prontuario

    modelo = _aprender(supabase, {chave: _modelo(docs) for chave, docs in por_chave.items()}, aprender)

    def limpo(documento: Documento) -> Documento:
        chave = _chave(documento)
        fora = (ESQUELETO.get(chave, frozenset()) | modelo.get(chave, set())) if chave else set()
        if not fora:
            return documento
        titulo, *corpo = documento.linhas
        fica = tuple(linha for linha in corpo if linha not in fora)
        return dataclasses.replace(documento, linhas=(titulo, *fica))

    return dataclasses.replace(prontuario, documentos=tuple(limpo(d) for d in prontuario.documentos))
