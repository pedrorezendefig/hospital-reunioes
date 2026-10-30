"""A matriz perfil x permissão de Contas médicas como o banco a tem depois das
migrations (issue #1308, ADR 0073).

Os INSERTs em `cm_perfil_permissao` de cada migration rodam de verdade, em
ordem, num SQLite em memória: a 116 carrega a matriz inicial com VALUES e a 121
copia "Analisar contas" para "Enviar contas" com INSERT ... SELECT, o que uma
regex sobre VALUES não lê. Os CHECKs e o resto do SQL ficam de fora (o SQLite
não fala o dialeto do Postgres neles); quem os confere é o teste da migration.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _inserts_da_matriz(sql: str) -> list[str]:
    sem_comentarios = re.sub(r"--[^\n]*", "", sql)
    return re.findall(r"INSERT INTO cm_perfil_permissao\b.*?;", sem_comentarios, flags=re.DOTALL)


def banco_da_matriz() -> sqlite3.Connection:
    """A tabela vazia, com a chave da 116 (o ON CONFLICT depende dela)."""
    banco = sqlite3.connect(":memory:")
    banco.execute(
        "CREATE TABLE cm_perfil_permissao ("
        " perfil TEXT NOT NULL, permissao TEXT NOT NULL, ligada BOOLEAN NOT NULL DEFAULT false,"
        " PRIMARY KEY (perfil, permissao))"
    )
    return banco


def aplicar(banco: sqlite3.Connection, *, de: int = 0, ate: int = 10_000) -> None:
    """Roda, em ordem, os INSERTs da matriz das migrations de `de` a `ate`."""
    for arquivo in sorted(MIGRATIONS.glob("*.sql")):
        if de <= int(arquivo.name.split("_", 1)[0]) <= ate:
            for comando in _inserts_da_matriz(arquivo.read_text(encoding="utf-8")):
                banco.execute(comando)


def linhas(banco: sqlite3.Connection) -> list[dict[str, Any]]:
    consulta = banco.execute("SELECT perfil, permissao, ligada FROM cm_perfil_permissao ORDER BY perfil, permissao")
    return [{"perfil": p, "permissao": k, "ligada": bool(v)} for p, k, v in consulta.fetchall()]


def matriz_aplicada() -> list[dict[str, Any]]:
    """As linhas de `cm_perfil_permissao` depois de todas as migrations."""
    banco = banco_da_matriz()
    aplicar(banco)
    return linhas(banco)
