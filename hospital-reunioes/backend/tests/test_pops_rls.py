"""Regressão de RLS default-deny nas tabelas do contexto POPs — issue #112.

As tabelas criadas nas migrations 045–048 nasceram sem `ENABLE ROW LEVEL
SECURITY` — fora do padrão da casa (009/041/043/049: RLS default-deny, backend
via service_role bypassa, anon_key bloqueada). Sem RLS, a anon_key (pública no
bundle do frontend) lê/escreve direto via PostgREST, contornando as guardas de
papel × estado dos endpoints. A migration 051 habilita RLS; este teste é o guard
que teria pego o bug e impede uma futura tabela POPs de esquecê-lo.
"""

from __future__ import annotations

import os
import re

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")

# Tabelas do contexto POPs que precisam de RLS default-deny (criadas em 045–048).
TABELAS_POPS_RLS = [
    "pops_setores",
    "pops_setores_participantes",
    "pops",
    "pops_versoes",
    "pops_devolucoes",
]


def _todas_migrations_sql() -> str:
    """Concatena o SQL de todas as migrations (a RLS pode vir numa migration
    posterior à do CREATE TABLE — caso da 051)."""
    blob = []
    for nome in sorted(os.listdir(MIGRATIONS_DIR)):
        if nome.endswith(".sql"):
            with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
                blob.append(f.read())
    return "\n".join(blob)


def test_tabelas_pops_tem_rls_habilitado():
    sql = _todas_migrations_sql()
    for tabela in TABELAS_POPS_RLS:
        padrao = rf"ALTER\s+TABLE\s+{re.escape(tabela)}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
        assert re.search(padrao, sql, re.IGNORECASE), (
            f"Tabela POPs '{tabela}' sem ENABLE ROW LEVEL SECURITY nas migrations "
            f"— anon_key acessaria via PostgREST contornando as guardas de papel."
        )
