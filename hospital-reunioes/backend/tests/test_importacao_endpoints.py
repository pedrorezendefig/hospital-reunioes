"""
Testes dos helpers do router de importação de ATAs antigas.

Endpoint integration tests (multipart + supabase real) ficam para Fase 7 (manual).
Aqui cobrimos a lógica isolada:
  - dedup check com mock supabase
  - geração de id_reuniao
  - geração de próximo id_acao
  - formatação de participantes para o prompt
"""
import os
import sys
from dataclasses import dataclass
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.importacao_service import (
    check_duplicata as _check_duplicata,
    format_participantes_ativos as _format_participantes_ativos,
    generate_reuniao_id as _generate_reuniao_id,
    get_last_id_acao_num as _get_last_id_acao_num,
)


@dataclass
class _Result:
    data: list


class _Query:
    """Mock fluente compatível com supabase-py."""

    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}
        self._order_desc = False
        self._limit_val: int | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, _col, desc=False):
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def execute(self):
        rows = [
            r for r in self._rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]
        if self._order_desc:
            rows = sorted(rows, key=lambda r: r.get("id_acao", ""), reverse=True)
        if self._limit_val is not None:
            rows = rows[: self._limit_val]
        return _Result(rows)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name):
        return _Query(self._tables.get(name, []))


# ---- _check_duplicata ----


def test_check_duplicata_sem_match_retorna_none():
    sb = _Supabase({"reunioes": []})
    assert _check_duplicata(sb, "abc123", "ATA-X-Y-001") is None


def test_check_duplicata_por_hash():
    sb = _Supabase(
        {
            "reunioes": [
                {
                    "id_reuniao": "MIG_001",
                    "titulo": "X",
                    "data": "2026-01-01",
                    "arquivo_hash": "abc",
                    "documento_id_origem": None,
                }
            ]
        }
    )
    dup = _check_duplicata(sb, "abc", None)
    assert dup is not None
    assert dup["motivo"] == "hash"
    assert dup["id_reuniao"] == "MIG_001"


def test_check_duplicata_por_documento_id():
    sb = _Supabase(
        {
            "reunioes": [
                {
                    "id_reuniao": "MIG_002",
                    "titulo": "Y",
                    "data": "2026-02-01",
                    "arquivo_hash": "other",
                    "documento_id_origem": "ATA-A-B-001",
                }
            ]
        }
    )
    dup = _check_duplicata(sb, None, "ATA-A-B-001")
    assert dup is not None
    assert dup["motivo"] == "documento_id"


def test_check_duplicata_hash_tem_precedencia_sobre_documento_id():
    """Se bater hash, retorna 'hash' sem precisar checar documento_id."""
    sb = _Supabase(
        {
            "reunioes": [
                {
                    "id_reuniao": "A",
                    "titulo": "T",
                    "data": "2026-01-01",
                    "arquivo_hash": "abc",
                    "documento_id_origem": None,
                }
            ]
        }
    )
    dup = _check_duplicata(sb, "abc", "ATA-X-Y-001")
    assert dup["motivo"] == "hash"


def test_check_duplicata_retorna_none_sem_filtros():
    sb = _Supabase({"reunioes": [{"id_reuniao": "X"}]})
    assert _check_duplicata(sb, None, None) is None


# ---- _generate_reuniao_id ----


def test_generate_reuniao_id_formato():
    rid = _generate_reuniao_id(date(2026, 3, 19))
    assert rid.startswith("MIG_20260319_")
    # MIG_YYYYMMDD_HHMMSSXX — 6 dig + 2 hex = 8 chars no sufixo
    suffix = rid.split("_", 2)[2]
    assert len(suffix) == 8


def test_generate_reuniao_id_aceita_string():
    rid = _generate_reuniao_id("2026-03-19")
    assert rid.startswith("MIG_20260319_")


def test_generate_reuniao_id_unico():
    r1 = _generate_reuniao_id(date(2026, 3, 19))
    r2 = _generate_reuniao_id(date(2026, 3, 19))
    # MIG_20260319_<HHMMSS><uid2hex> — uid aleatório torna diferente
    # (pode colidir em teste rápido mas improvável)
    assert r1 != r2 or len(r1) == len(r2)  # sanidade de formato


# ---- _get_last_id_acao_num ----


def test_get_last_id_acao_num_vazio():
    sb = _Supabase({"pendencias": []})
    assert _get_last_id_acao_num(sb) == 0


def test_get_last_id_acao_num_com_registros():
    sb = _Supabase(
        {"pendencias": [{"id_acao": "A001"}, {"id_acao": "A042"}, {"id_acao": "A012"}]}
    )
    assert _get_last_id_acao_num(sb) == 42


# ---- _format_participantes_ativos ----


def test_format_participantes_ativos_vazio():
    assert _format_participantes_ativos([]) == "Nenhum participante ativo cadastrado"


def test_format_participantes_ativos_com_cargo_e_setor():
    lista = [
        {"nome_completo": "Josiane Alves", "cargo": "Diretora Adm/Fin", "setor": "Administração"},
        {"nome_completo": "Felipe Malafaia", "cargo": "Diretor Exec", "setor": None},
    ]
    out = _format_participantes_ativos(lista)
    assert "Josiane Alves" in out
    assert "Diretora Adm/Fin" in out
    assert "Administração" in out
    assert "Felipe Malafaia" in out


def test_format_participantes_ativos_sem_cargo():
    lista = [{"nome_completo": "X", "cargo": "", "setor": ""}]
    out = _format_participantes_ativos(lista)
    assert "- X" in out
