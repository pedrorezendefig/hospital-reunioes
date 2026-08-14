"""Import dos protocolos de ouvidoria a partir do export CSV do NocoDB (issue #290, ADR 0031).

Ato da virada (fase 2 do ADR-0015 da Ana): o export da tabela
`5_Ouvidoria_Protocolos` nao entra no git (dado operacional de ouvidoria).
O import preserva numero e data de abertura (numeros ja comunicados seguem
consultaveis) e ajusta a sequence para continuar do ultimo numero usado,
mesmo com buraco na numeracao (o NocoDB consumiu Ids de teste apagados).

O parser recusa export inconsistente: o Protocolo da fonte tem que recompor
de Id + ano da abertura, senao um numero comunicado mudaria de dono.

Tipografia sanitizada (ADR 0013): o resumo aparece no painel de ouvidoria.

Uso:
  uv run python -m app.scripts.import_ouvidoria_protocolos <export.csv>        # insere no banco do .env
  uv run python -m app.scripts.import_ouvidoria_protocolos <export.csv> --sql  # imprime INSERTs + setval
"""

from __future__ import annotations

import csv
import sys

from app.utils.text_sanitizer import sanitizar_estrutura

_STATUS = {"aberto": "aberto", "respondido": "respondido", "encerrado": "encerrado"}

SETVAL_SQL = "SELECT setval('ouvidoria_protocolos_numero_seq', (SELECT MAX(numero) FROM ouvidoria_protocolos));"


def _parse_data(data: str) -> str:
    """Aceita o created time do NocoDB (ISO, com ou sem hora) e DD/MM/AAAA."""
    data = data.strip()
    if "/" in data:
        dia, mes, ano = data.split(" ")[0].split("/")
        return f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"
    return data[:10]


def parse_export(csv_path: str) -> list[dict]:
    """Le o export do NocoDB e devolve as rows no schema de ouvidoria_protocolos."""
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            numero = int(linha["Id"])
            data_abertura = _parse_data(linha["Data_Abertura"])
            protocolo_fonte = linha["Protocolo"].strip()
            protocolo_gerado = f"{data_abertura[:4]}-{numero:04d}"
            if protocolo_fonte != protocolo_gerado:
                raise ValueError(
                    f"Export inconsistente: Protocolo {protocolo_fonte!r} nao recompoe "
                    f"de Id {numero} + ano ({protocolo_gerado!r})"
                )
            status = _STATUS[linha["Status"].strip().lower()]
            rows.append(
                sanitizar_estrutura(
                    {
                        "numero": numero,
                        "data_abertura": data_abertura,
                        "categoria": linha["Categoria"].strip(),
                        "setor": linha["Setor"].strip(),
                        "resumo": linha["Resumo"].strip(),
                        "status": status,
                        "conversa_id": linha["Conversa_Id"].strip(),
                    }
                )
            )
    return rows


def _sql_literal(valor) -> str:
    if isinstance(valor, int):
        return str(valor)
    escapado = str(valor).replace("'", "''")
    return f"'{escapado}'"


def to_sql(rows: list[dict]) -> str:
    """SQL do import: INSERTs idempotentes + sequence continuando do ultimo numero."""
    colunas = list(rows[0].keys())
    values = ",\n".join("  (" + ", ".join(_sql_literal(r[c]) for c in colunas) + ")" for r in rows)
    return (
        f"INSERT INTO ouvidoria_protocolos ({', '.join(colunas)})\nVALUES\n{values}\n"
        "ON CONFLICT (numero) DO NOTHING;\n"
        f"{SETVAL_SQL}"
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
    # ignore_duplicates: mesma semantica do --sql (DO NOTHING), reexecucao nao duplica.
    result = supabase.table("ouvidoria_protocolos").upsert(rows, on_conflict="numero", ignore_duplicates=True).execute()
    # PostgREST nao roda setval: ajustar a sequence e um passo manual no Studio.
    print(f"Importados {len(result.data or [])} protocolos.")
    print(f"Agora rode no SQL Editor: {SETVAL_SQL}")


if __name__ == "__main__":
    main()
