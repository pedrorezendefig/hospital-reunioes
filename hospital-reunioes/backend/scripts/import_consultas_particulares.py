"""Import das consultas particulares a partir do export CSV do NocoDB (issue #288, ADR 0031).

Parseia o export (colunas originais do NocoDB) para o schema da tabela
`consultas_particulares` e insere via Supabase, ou emite o SQL de seed
idempotente para aplicar direto no Studio (caminho de produção).

O texto passa pelo sanitizador de tipografia do app (ADR 0013): travessão e
meia-risca do dado fonte viram vírgula/hífen, porque a Ana repassa esses
campos literalmente a pacientes.

Uso:
  uv run python -m scripts.import_consultas_particulares <export.csv>        # insere no banco do .env
  uv run python -m scripts.import_consultas_particulares <export.csv> --sql  # imprime INSERTs
"""

from __future__ import annotations

import csv
import sys

from app.utils.text_sanitizer import sanitizar_estrutura


def _parse_valor(valor: str) -> float:
    """Converte o formato do NocoDB ("R$ 380,00") em número."""
    limpo = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return float(limpo)


def _parse_data(data: str) -> str:
    """Converte DD/MM/AAAA em AAAA-MM-DD (formato do Postgres)."""
    dia, mes, ano = data.strip().split("/")
    return f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"


def _parse_flag(flag: str) -> bool:
    return flag.strip().upper() == "S"


def parse_export(csv_path: str) -> list[dict]:
    """Lê o export do NocoDB e devolve as rows no schema de consultas_particulares."""
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            rows.append(
                sanitizar_estrutura(
                    {
                        "especialidade": linha["Especialidade"].strip(),
                        "valor_rs": _parse_valor(linha["Valor_RS"]),
                        "descricao_servico": linha["Descricao_Servico"].strip(),
                        "diferencial_1": linha["Diferencial_1"].strip(),
                        "diferencial_2": linha["Diferencial_2"].strip(),
                        "diferencial_3": linha["Diferencial_3"].strip(),
                        "alta_demanda": _parse_flag(linha["Alta_Demanda"]),
                        "observacoes_ana": linha["Observacoes_Ana"].strip(),
                        "ativo": _parse_flag(linha["Ativo"]),
                        "ultima_atualizacao": _parse_data(linha["Ultima_Atualizacao"]),
                    }
                )
            )
    return rows


def _sql_literal(valor) -> str:
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, float):
        return f"{valor:.2f}"
    escapado = str(valor).replace("'", "''")
    return f"'{escapado}'"


def to_sql(rows: list[dict]) -> str:
    """SQL de seed idempotente (ON CONFLICT na especialidade não sobrescreve edição posterior)."""
    colunas = list(rows[0].keys())
    values = ",\n".join("  (" + ", ".join(_sql_literal(r[c]) for c in colunas) + ")" for r in rows)
    return (
        f"INSERT INTO consultas_particulares ({', '.join(colunas)})\nVALUES\n{values}\n"
        "ON CONFLICT (especialidade) DO NOTHING;"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rows = parse_export(sys.argv[1])
    if "--sql" in sys.argv:
        print(to_sql(rows))
        return
    from app.dependencies import get_supabase_client

    supabase = get_supabase_client()
    # ignore_duplicates: mesma semântica do --sql (DO NOTHING), não sobrescreve
    # edições feitas depois no admin.
    result = (
        supabase.table("consultas_particulares")
        .upsert(rows, on_conflict="especialidade", ignore_duplicates=True)
        .execute()
    )
    print(f"Importadas {len(result.data or [])} consultas particulares.")


if __name__ == "__main__":
    main()
