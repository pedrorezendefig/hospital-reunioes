"""Testes de `_ensure_external_stub` — helper que cria participante externo
stub quando a importação recebe uma pendência cujo responsável não resolveu
em nenhum matched nem em externo_idx do preview.

Política: importação NUNCA descarta pendência por responsável não resolvido
enquanto houver `responsavel_nome` não vazio. Em vez disso, cria (ou reusa)
stub `is_externo=true, ativo=false, email=null`.
"""
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.importacao_service import ensure_external_stub as _ensure_external_stub


@dataclass
class _InsertCall:
    table: str
    payload: dict


@dataclass
class _Result:
    data: list


class _Query:
    """Mock fluente compatível com supabase-py para select+is_+ilike+limit+insert."""

    def __init__(self, table_name: str, store: "_Store"):
        self._table = table_name
        self._store = store
        self._filters_eq: dict = {}
        self._filters_is: dict = {}
        self._filters_ilike: dict = {}
        self._insert_payload: dict | None = None
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters_eq[col] = val
        return self

    def is_(self, col, val):
        # "null" string simula o filtro .is_(col, 'null')
        self._filters_is[col] = val
        return self

    def ilike(self, col, val):
        self._filters_ilike[col] = val.lower().strip()
        return self

    def limit(self, n):
        self._limit = n
        return self

    def in_(self, col, vals):
        self._filters_eq[col] = ("in", set(vals))
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def execute(self):
        if self._insert_payload is not None:
            # registra insert e devolve row com id mockado
            self._store.inserts.append(
                _InsertCall(table=self._table, payload=dict(self._insert_payload))
            )
            self._store.next_id += 1
            new_row = {**self._insert_payload, "id": f"P{self._store.next_id:03d}"}
            # simula persistência para queries seguintes encontrarem
            self._store.tables.setdefault(self._table, []).append(new_row)
            return _Result([new_row])

        rows = list(self._store.tables.get(self._table, []))
        for col, val in self._filters_eq.items():
            if isinstance(val, tuple) and val[0] == "in":
                rows = [r for r in rows if r.get(col) in val[1]]
            else:
                rows = [r for r in rows if r.get(col) == val]
        for col, val in self._filters_is.items():
            if val == "null":
                rows = [r for r in rows if r.get(col) is None]
        for col, val in self._filters_ilike.items():
            rows = [r for r in rows if (r.get(col) or "").lower().strip() == val]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


@dataclass
class _Store:
    tables: dict = field(default_factory=dict)
    inserts: list = field(default_factory=list)
    next_id: int = 0


class _Supabase:
    def __init__(self, store: _Store):
        self._store = store

    def table(self, name):
        return _Query(name, self._store)


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_stub_criado_quando_nao_existe():
    store = _Store(tables={"participantes": []})
    sb = _Supabase(store)
    cache: dict[str, str] = {}

    pid = _ensure_external_stub(
        sb, nome="Zoraide Fornecedor", cargo="Técnico", setor=None, cache=cache
    )

    assert pid is not None
    assert len(store.inserts) == 1
    payload = store.inserts[0].payload
    assert payload["is_externo"] is True
    assert payload["ativo"] is False
    assert payload["email"] is None
    assert payload["nome_completo"] == "Zoraide Fornecedor"
    # cache populado pra evitar segunda criação
    assert cache


def test_stub_reusa_existente_por_nome_case_insensitive():
    store = _Store(
        tables={
            "participantes": [
                {
                    "id": "P999",
                    "nome_completo": "joão pereira",
                    "is_externo": True,
                    "email": None,
                    "ativo": False,
                }
            ]
        }
    )
    sb = _Supabase(store)
    cache: dict[str, str] = {}

    pid = _ensure_external_stub(
        sb, nome="João Pereira", cargo="Consultor", setor=None, cache=cache
    )

    assert pid == "P999"
    # não cria stub novo — reusa existente
    assert len(store.inserts) == 0


def test_stub_cache_intra_importacao():
    store = _Store(tables={"participantes": []})
    sb = _Supabase(store)
    cache: dict[str, str] = {}

    pid1 = _ensure_external_stub(
        sb, nome="Maria Teste", cargo=None, setor=None, cache=cache
    )
    pid2 = _ensure_external_stub(
        sb, nome="Maria Teste", cargo=None, setor=None, cache=cache
    )
    # Segunda chamada sai pelo cache — só um insert
    assert pid1 == pid2
    assert len(store.inserts) == 1


def test_stub_nome_vazio_retorna_none():
    store = _Store(tables={"participantes": []})
    sb = _Supabase(store)

    assert _ensure_external_stub(sb, nome="", cargo=None, setor=None, cache={}) is None
    assert (
        _ensure_external_stub(sb, nome="   ", cargo=None, setor=None, cache={}) is None
    )
    assert len(store.inserts) == 0
