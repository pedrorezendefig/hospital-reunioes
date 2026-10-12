"""Leitura do arquivo de memória da operadora (issue #1119, PRD #1113, ADR 0070).

A memória é o arquivo `MEMORIA-<SIGLA>-v<X.Y>.md` que o diretor monta no
formato do `MODELO-MEMORIA-OPERADORA.md`: um cabeçalho YAML lido pelo código e,
abaixo dele, tabelas Markdown com uma regra por linha. Este módulo é puro:
recebe o texto e devolve a memória lida, ou recusa com `MemoriaRecusadaError`.

O cabeçalho vai inteiro para `parametros_json`, inclusive o que o código ainda
não lê (user story 15: a memória nunca é mutilada pela importação). Quem lê os
parâmetros passa por `parametros_lidos`, que completa com o valor padrão as
chaves que o código usa e preserva o resto.

Toda tabela cuja primeira coluna é `ID` vira regra, fora as das seções
"Pendentes (resumo)" e "Histórico", que repetem ou contam o que já está nas
outras. Coluna além de ID, Regra, Tipo, Origem, Status e Data entra no texto
da regra como "Coluna: valor", uma por linha.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import yaml

__all__ = ["MemoriaLida", "MemoriaRecusadaError", "RegraLida", "ler_memoria", "parametros_lidos"]

# Número no formato de CPF, com ou sem os pontos, sempre com o hífen do dígito
# verificador. Sem o hífen seriam onze dígitos soltos, e código de tabela
# comprido viraria recusa falsa.
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-\d{2}(?!\d)")

# A sigla vira nome de operadora e nome do arquivo exportado.
_SIGLA = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,29}")

_CABECALHO = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SEPARADOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

# Seções que não viram regra, pelo título normalizado sem o número.
_SECOES_IGNORADAS = frozenset({"PENDENTES (RESUMO)", "PENDENTES", "HISTORICO"})

_TIPOS = frozenset({"CONTRATUAL", "OPERACIONAL"})

# As colunas da tabela de regra que têm campo próprio; o resto vai para o texto.
_COLUNAS_PROPRIAS = frozenset({"ID", "REGRA", "TIPO", "ORIGEM", "STATUS", "DATA"})

# O que o código lê do cabeçalho, e o valor quando a memória não traz a chave.
# `transicao` cai nas diretrizes gerais HSM, que valem para toda operadora
# (MODELO-MEMORIA-OPERADORA.md, "Diretrizes gerais HSM").
_PADROES: dict[str, Any] = {
    "diaria": {},
    "diaria_global": None,
    "colunas_de_preco": {},
    "tetos_por_dia": {},
    "precos": {},
    "tabelas": {},
    "transicao": {
        "prescrito_vale_como_checado": True,
        "se_necessario_sem_registro": "INCLUIR_COM_OBSERVACAO",
        "se_necessario_doses_por_dia_sem_registro": 1,
    },
    "pacote_uti_adulto": None,
    "fora_da_conta_do_hospital": [],
}


class MemoriaRecusadaError(ValueError):
    """O arquivo não entra; a mensagem é para quem enviou."""


class _LeitorSemAlias(yaml.SafeLoader):
    """O `safe_load` sem alias: cada `*nome` repete o nó da âncora, e o
    `parametros_json` copia cada repetição, então poucas centenas de bytes
    aninhados viram bilhões de elementos e derrubam o backend inteiro."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            linha = self.peek_event().start_mark.line + 2
            raise MemoriaRecusadaError(
                f"O cabeçalho da memória usa alias do YAML (*nome, linha {linha}). Escreva o valor por "
                "extenso e envie de novo."
            )
        return super().compose_node(parent, index)


@dataclass(frozen=True)
class RegraLida:
    codigo: str
    secao: str | None
    texto: str
    tipo: str | None
    origem: str | None
    status: str
    validado_em: str | None


@dataclass(frozen=True)
class MemoriaLida:
    sigla: str
    nome: str
    versao: str
    situacao: str
    parametros: dict[str, Any]
    regras: tuple[RegraLida, ...]


def _normalizar(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.upper().split())


def _json(valor: Any) -> Any:
    """O que o YAML devolve, em forma que o JSONB aceita (datas viram texto)."""
    if isinstance(valor, dict):
        return {str(chave): _json(v) for chave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_json(v) for v in valor]
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    return valor


def parametros_lidos(parametros: dict[str, Any]) -> dict[str, Any]:
    """O cabeçalho como o código lê: as chaves que ele usa, com o padrão quando
    ausentes, e todo o resto preservado."""
    return {**_PADROES, **parametros}


def _celulas(linha: str) -> list[str]:
    corpo = linha.strip()
    if corpo.startswith("|"):
        corpo = corpo[1:]
    if corpo.endswith("|") and not corpo.endswith("\\|"):
        corpo = corpo[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", corpo)]


def _data(texto: str) -> str | None:
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date().isoformat()
        except ValueError:
            continue
    return None


def _secao(codigo: str) -> str | None:
    """A seção pelo prefixo do ID: `ASSIM-PRI-01` é PRI."""
    partes = codigo.split("-")
    return partes[-2] if len(partes) >= 2 else None


def _regra(cabecalho: list[str], celulas: list[str]) -> RegraLida | None:
    valores = dict(zip(cabecalho, celulas + [""] * (len(cabecalho) - len(celulas)), strict=False))
    proprias = {
        _normalizar(coluna): valor for coluna, valor in valores.items() if _normalizar(coluna) in _COLUNAS_PROPRIAS
    }
    codigo = proprias.get("ID", "").strip()
    if not re.search(r"[A-Za-z0-9]", codigo):  # linha vazia do modelo, ou só um traço
        return None
    extras = [
        f"{coluna}: {valor}"
        for coluna, valor in valores.items()
        if _normalizar(coluna) not in _COLUNAS_PROPRIAS and valor
    ]
    texto = "\n".join(parte for parte in [proprias.get("REGRA", ""), *extras] if parte)
    if not texto:
        return None
    tipo = proprias.get("TIPO", "").upper()
    return RegraLida(
        codigo=codigo,
        secao=_secao(codigo),
        texto=texto,
        tipo=tipo if tipo in _TIPOS else None,
        origem=proprias.get("ORIGEM") or None,
        status="VIGENTE" if proprias.get("STATUS", "").upper() == "VIGENTE" else "PENDENTE",
        validado_em=_data(proprias.get("DATA", "")),
    )


def _regras(corpo: str) -> list[RegraLida]:
    regras: list[RegraLida] = []
    ignorando_ate: int | None = None  # nível do título da seção ignorada
    linhas = corpo.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        titulo = _TITULO.match(linha)
        if titulo:
            nivel = len(titulo.group(1))
            if ignorando_ate is not None and nivel <= ignorando_ate:
                ignorando_ate = None
            nome = re.sub(r"^\d+(\.\d+)*\.?\s*", "", _normalizar(titulo.group(2)))
            if ignorando_ate is None and nome in _SECOES_IGNORADAS:
                ignorando_ate = nivel
            i += 1
            continue
        proxima = linhas[i + 1] if i + 1 < len(linhas) else ""
        if linha.lstrip().startswith("|") and _SEPARADOR.match(proxima.strip()):
            cabecalho = _celulas(linha)
            i += 2
            linhas_da_tabela = []
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                linhas_da_tabela.append(_celulas(linhas[i]))
                i += 1
            if ignorando_ate is None and _normalizar(cabecalho[0]) == "ID":
                regras.extend(r for r in (_regra(cabecalho, c) for c in linhas_da_tabela) if r)
            continue
        i += 1
    return regras


def ler_memoria(texto: str) -> MemoriaLida:
    """O arquivo de memória lido, ou `MemoriaRecusadaError` com o motivo."""
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if _CPF.search(linha):
            raise MemoriaRecusadaError(
                f"O arquivo tem um número no formato de CPF (linha {numero}). A memória não pode ter dado de "
                "paciente: tire o número e envie de novo."
            )

    bloco = _CABECALHO.match(texto)
    if not bloco:
        raise MemoriaRecusadaError("O arquivo não começa pelo cabeçalho da memória, entre duas linhas com ---.")
    try:
        cabecalho = yaml.load(bloco.group(1), Loader=_LeitorSemAlias)  # noqa: S506 (SafeLoader)
    except yaml.YAMLError as exc:
        marca = getattr(exc, "problem_mark", None)
        onde = f" (linha {marca.line + 2})" if marca else ""
        raise MemoriaRecusadaError(f"O cabeçalho da memória não pôde ser lido{onde}.") from None
    if not isinstance(cabecalho, dict):
        raise MemoriaRecusadaError("O cabeçalho da memória não pôde ser lido.")
    parametros = _json(cabecalho)

    sigla = str(parametros.get("operadora") or "").strip().upper()
    versao = str(parametros.get("versao_memoria") or "").strip()
    if not sigla:
        raise MemoriaRecusadaError("O cabeçalho não diz a operadora (campo operadora).")
    if not _SIGLA.fullmatch(sigla):
        raise MemoriaRecusadaError(
            f"A sigla da operadora no cabeçalho ({sigla}) tem que ter só letras e números, como ASSIM. "
            "O modelo vem com <SIGLA> para trocar."
        )
    if not versao:
        raise MemoriaRecusadaError("O cabeçalho não diz a versão da memória (campo versao_memoria).")
    situacao = str(parametros.get("situacao") or "").strip().upper()

    return MemoriaLida(
        sigla=sigla,
        nome=str(parametros.get("nome") or sigla).strip(),
        versao=versao,
        situacao=situacao if situacao in {"PRONTA", "PARCIAL", "SEM_MEMORIA"} else "PARCIAL",
        parametros=parametros,
        regras=tuple(_regras(texto[bloco.end() :])),
    )
