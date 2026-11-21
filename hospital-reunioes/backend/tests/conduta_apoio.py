"""Dublê do banco para os testes do Canal de Conduta (issue #1820).

Um PostgREST em memória com o que o módulo usa: select, eq, in_, is_, order,
limit, insert e update (recusado nas tabelas imutáveis, como o banco faz). O
`insert` confere as chaves únicas, e o da trilha confere a cadeia como o
trigger da migration 175 (a linha nova aponta para a última do caso), para o serviço ser
exercitado contra a mesma recusa que o banco faz.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from postgrest.exceptions import APIError


class _Consulta:
    def __init__(self, banco: Banco, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._teto: int | None = None
        self._inserir: list[dict] | None = None
        self._atualizar: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def lte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) <= str(valor))
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) >= str(valor))
        return self

    def is_(self, coluna, valor):
        esperado = None if valor == "null" else valor
        self._filtros.append(lambda linha: linha.get(coluna) is esperado)
        return self

    def ilike(self, coluna, padrao):
        trecho = padrao.strip("%").lower()
        self._filtros.append(lambda linha: trecho in str(linha.get(coluna) or "").lower())
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, n):
        self._teto = n
        return self

    def insert(self, linhas):
        self._inserir = [dict(linhas)] if isinstance(linhas, dict) else [dict(linha) for linha in linhas]
        return self

    def update(self, campos):
        if self._nome in IMUTAVEIS:
            raise AssertionError(f"o banco recusa UPDATE em {self._nome}")
        self._atualizar = dict(campos)
        return self

    def execute(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._inserir is not None:
            return SimpleNamespace(data=[self._banco.gravar(self._nome, linha) for linha in self._inserir])
        if self._atualizar is not None:
            alvos = [linha for linha in tabela if all(f(linha) for f in self._filtros)]
            for linha in alvos:
                linha.update(self._atualizar)
            return SimpleNamespace(data=[dict(linha) for linha in alvos])
        linhas = [dict(linha) for linha in tabela if all(f(linha) for f in self._filtros)]
        if self._ordem:
            coluna, desc = self._ordem
            linhas.sort(key=lambda linha: linha.get(coluna), reverse=desc)
        return SimpleNamespace(data=linhas[: self._teto] if self._teto is not None else linhas)


# As tabelas que o banco não deixa alterar (migrations 175 e 185).
IMUTAVEIS = ("conduta_trilha", "conduta_prazos_vencidos")

# As chaves únicas que o módulo usa para não gravar duas vezes (migration 185).
UNICAS = {
    "conduta_prazos_vencidos": ("caso_id", "prazo_em"),
    "conduta_contestacoes": ("caso_id",),
    "conduta_contestacao_votos": ("contestacao_id", "participante_id"),
    "conduta_participacao_votos": ("contestacao_id", "participante_id"),
}


class Banco:
    def __init__(self, tabelas: dict[str, list[dict]] | None = None):
        self.tabelas: dict[str, list[dict]] = tabelas or {}
        self._seq = itertools.count(1)
        self.falhas_da_trilha = 0

    def table(self, nome: str) -> _Consulta:
        return _Consulta(self, nome)

    def gravar(self, nome: str, linha: dict[str, Any]) -> dict[str, Any]:
        if nome == "conduta_trilha":
            if self.falhas_da_trilha:
                self.falhas_da_trilha -= 1
                raise APIError({"code": "23514", "message": "A trilha do caso é uma cadeia"})
            do_caso = [x for x in self.tabelas.get(nome, []) if x["caso_id"] == linha["caso_id"]]
            ultimo = max(do_caso, key=lambda x: x["seq"])["codigo"] if do_caso else None
            if linha.get("codigo_anterior") != ultimo:
                raise APIError({"code": "23514", "message": "A trilha do caso é uma cadeia"})
            linha = {**linha, "seq": next(self._seq)}
        elif nome == "conduta_registro":
            # O DEFAULT now() da migration 184.
            linha = {"id": str(uuid.uuid4()), "registrado_em": datetime.now(UTC).isoformat(), **linha}
        else:
            chave = UNICAS.get(nome)
            if chave and any(all(x.get(c) == linha.get(c) for c in chave) for x in self.tabelas.get(nome, [])):
                raise APIError({"code": "23505", "message": f"duplicate key value violates unique constraint ({nome})"})
            linha = {"id": str(uuid.uuid4()), **linha}
        self.tabelas.setdefault(nome, []).append(linha)
        return dict(linha)
