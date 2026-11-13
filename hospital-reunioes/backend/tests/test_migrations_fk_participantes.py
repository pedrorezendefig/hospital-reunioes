"""Toda coluna que aponta para `participantes(id)` tem o tipo da chave dela.

`participantes.id` é `VARCHAR(10)` (migration 001). A migration 140 nasceu com
`revisada_por UUID REFERENCES participantes(id)` e o Postgres recusou no Studio
(42804, tipos incompatíveis); o CI não aplica SQL, então só este teste pega
antes do humano colar. Ele lê o texto de cada migration, acha cada
`REFERENCES participantes(id)` e confere o tipo declarado na mesma coluna.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

_REFERENCIA = re.compile(r"REFERENCES\s+participantes\s*\(\s*id\s*\)", re.IGNORECASE)
_TIPO = re.compile(
    r"\b(VARCHAR\s*\(\s*\d+\s*\)|CHARACTER\s+VARYING\s*\(\s*\d+\s*\)|(?:UUID|TEXT|BIGINT|INTEGER|INT)\b)",
    re.IGNORECASE,
)


def _sem_comentarios(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _tipo_da_coluna(sql: str, inicio: int) -> str | None:
    """O tipo declarado entre o fim da definição anterior e o REFERENCES."""
    trecho = sql[:inicio]
    corte = max(trecho.rfind(","), trecho.rfind(";"))
    tipos = _TIPO.findall(trecho[corte + 1 :])
    return re.sub(r"\s+", "", tipos[-1]).upper() if tipos else None


def _referencias(sql: str) -> list[str | None]:
    sql = _sem_comentarios(sql)
    return [_tipo_da_coluna(sql, m.start()) for m in _REFERENCIA.finditer(sql)]


def test_detector_pega_uuid_e_aceita_varchar10():
    errado = (
        "CREATE TABLE t (\n  id UUID PRIMARY KEY,\n"
        "  revisada_por UUID REFERENCES participantes(id) ON DELETE SET NULL\n);"
    )
    certo = (
        "ALTER TABLE t ADD COLUMN IF NOT EXISTS feito_por VARCHAR(10)\n"
        "  REFERENCES participantes(id) ON DELETE SET NULL;"
    )
    assert _referencias(errado) == ["UUID"]
    assert _referencias(certo) == ["VARCHAR(10)"]


def test_toda_fk_para_participantes_e_varchar10():
    arquivos = sorted(MIGRATIONS.glob("*.sql"))
    assert len(arquivos) > 100, MIGRATIONS
    vistas = 0
    erradas = []
    for arquivo in arquivos:
        for tipo in _referencias(arquivo.read_text(encoding="utf-8")):
            vistas += 1
            if tipo != "VARCHAR(10)":
                erradas.append(f"{arquivo.name}: {tipo}")
    assert vistas > 50
    assert erradas == [], "participantes.id é VARCHAR(10); FK com outro tipo quebra no Studio (42804)"
