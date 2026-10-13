"""O dicionário de itens do hospital (issue #1120, PRD #1113, ADR 0070).

O mesmo produto aparece com três nomes: na conta (Brasíndice, "ESMERON - 10
MG/ML SOL INJ"), na prescrição ("ESMERON 10MG/ML") e na ficha anestésica pelo
genérico ("Rocurônio"). O dicionário é do hospital, não da operadora: liga o
termo ao código da conta. Entra por CSV (`termo;codigo;descricao_na_conta;situacao`,
sinônimos no termo separados por `|`), um termo por linha do banco.

O casamento segue o código de referência do diretor (`leitura/itens.py`):
primeiro o dicionário, depois marca e concentração, depois só a marca, que
sai com confiança média.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Casamento",
    "DicionarioRecusadoError",
    "TermoLido",
    "casar",
    "dicionario_do_banco",
    "importar_dicionario",
    "ler_dicionario",
]

COLUNAS = ("termo", "codigo", "descricao_na_conta", "situacao")

_UNIDADE = r"(MG|MCG|G|ML|UI|%|MEQ)"


class DicionarioRecusadoError(ValueError):
    """O CSV não entra; a mensagem é para quem enviou."""


@dataclass(frozen=True)
class TermoLido:
    termo: str
    codigo: str
    descricao: str | None
    situacao: str


@dataclass(frozen=True)
class Casamento:
    """Os itens da conta que casaram com o nome, como e com que confiança.

    `como`: DICIONARIO, MARCA_E_CONCENTRACAO, MARCA ou NENHUM (sem par).
    """

    itens: list[dict[str, Any]] = field(default_factory=list)
    como: str = "NENHUM"
    confianca: str | None = None


def _norm(texto: str | None) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.upper().split())


def ler_dicionario(texto: str) -> list[TermoLido]:
    """Um termo por sinônimo, todos com o código da linha, ou `DicionarioRecusadoError`."""
    linhas = csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";")
    cabecalho = [c.strip().lower() for c in next(linhas, [])]
    if not {"termo", "codigo"} <= set(cabecalho):
        raise DicionarioRecusadoError(
            f"O cabeçalho do CSV ({';'.join(cabecalho)}) não é o do dicionário. Colunas esperadas: {';'.join(COLUNAS)}."
        )
    termos: dict[str, tuple[int, TermoLido]] = {}
    for numero, celulas in enumerate(linhas, start=2):
        linha = {coluna: (celulas[i].strip() if i < len(celulas) else "") for i, coluna in enumerate(cabecalho)}
        if not linha["termo"] and not linha["codigo"]:
            continue
        if not linha["termo"] or not linha["codigo"]:
            raise DicionarioRecusadoError(f"Linha {numero}: falta o termo ou o código.")
        situacao = "CONFIRMADO" if _norm(linha.get("situacao")) == "CONFIRMADO" else "PROPOSTO"
        for sinonimo in linha["termo"].split("|"):
            termo = _norm(sinonimo)
            if not termo:
                continue
            anterior = termos.get(termo)
            if anterior and anterior[1].codigo != linha["codigo"]:
                raise DicionarioRecusadoError(
                    f"O termo {termo} aparece nas linhas {anterior[0]} e {numero} com códigos diferentes "
                    f"({anterior[1].codigo} e {linha['codigo']}). Deixe um só."
                )
            termos[termo] = (
                numero,
                TermoLido(termo, linha["codigo"], linha.get("descricao_na_conta") or None, situacao),
            )
    if not termos:
        raise DicionarioRecusadoError("O CSV só tem o cabeçalho: nenhum termo para carregar.")
    return [termo for _, termo in termos.values()]


def importar_dicionario(supabase, termos: list[TermoLido], autor_id: str | None) -> dict[str, int]:
    """Grava os termos: o que já existe é atualizado, o resto entra novo."""
    existentes = {
        linha["termo"].lower(): linha["id"]
        for linha in supabase.table("cm_item_dicionario").select("id, termo").execute().data or []
    }
    novos, atualizados = [], 0
    for termo in termos:
        dados = {
            "codigo_conta": termo.codigo,
            "descricao_conta": termo.descricao,
            "situacao": termo.situacao,
            "origem": "GESTAO",
            "autor_id": autor_id,
        }
        if termo.termo.lower() in existentes:
            supabase.table("cm_item_dicionario").update(dados).eq("id", existentes[termo.termo.lower()]).execute()
            atualizados += 1
        else:
            novos.append({"termo": termo.termo, **dados})
    if novos:
        supabase.table("cm_item_dicionario").insert(novos).execute()
    return {"termos": len(termos), "novos": len(novos), "atualizados": atualizados}


def dicionario_do_banco(supabase) -> dict[str, set[str]]:
    """O dicionário como o casamento usa: termo normalizado -> códigos da conta."""
    dicionario: dict[str, set[str]] = {}
    for linha in supabase.table("cm_item_dicionario").select("termo, codigo_conta").execute().data or []:
        if linha.get("codigo_conta"):
            dicionario.setdefault(_norm(linha["termo"]), set()).add(linha["codigo_conta"])
    return dicionario


def _marca(nome: str) -> str:
    texto = re.sub(r"^\(D\d+/\d+\)\s*", "", _norm(nome))
    achada = re.match(r"([A-Z][A-Z'.+ ]*?)(?=\s*(-|\d|\(|$))", texto)
    return achada.group(1).strip() if achada else texto.split(" ")[0]


def _concentracao(nome: str) -> str | None:
    achada = re.search(r"(\d+(?:[.,]\d+)?)\s*" + _UNIDADE + r"\b", _norm(nome))
    return achada.group(1).replace(",", ".") if achada else None


def _generico(nome: str) -> str | None:
    achado = re.search(r"\(([^)]+)\)", nome or "")
    return _norm(achado.group(1)) if achado else None


def casar(nome: str, itens_conta: list[dict[str, Any]], dicionario: dict[str, set[str]]) -> Casamento:
    """Os itens da conta que correspondem ao nome do prontuário.

    Ordem: termo do dicionário no nome (ou o genérico entre parênteses),
    marca e concentração, só a marca (confiança média). Nada: sem par.
    """
    texto = _norm(nome)
    codigos: set[str] = set()
    for termo, cods in dicionario.items():
        if termo and (termo == texto or re.search(r"(?<![A-Z])" + re.escape(termo) + r"(?![A-Z])", texto)):
            codigos |= cods
    generico = _generico(nome)
    if generico and generico in dicionario:
        codigos |= dicionario[generico]
    if codigos:
        achados = [i for i in itens_conta if i["codigo"] in codigos]
        if achados:
            return Casamento(achados, "DICIONARIO", "ALTA")
    marca, concentracao = _marca(nome), _concentracao(nome)
    if len(marca) >= 4:
        mesmos = [i for i in itens_conta if _marca(i["descricao"]) == marca]
        if concentracao:
            exatos = [i for i in mesmos if _concentracao(i["descricao"]) == concentracao]
            if exatos:
                return Casamento(exatos, "MARCA_E_CONCENTRACAO", "ALTA")
        if mesmos:
            return Casamento(mesmos, "MARCA", "MEDIA")
    return Casamento()
