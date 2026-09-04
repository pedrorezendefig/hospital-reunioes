"""Import de exames e cirurgias a partir dos exports CSV do NocoDB (issue #289, ADR 0031).

Parseia o export (colunas originais do NocoDB) para o schema da tabela
correspondente e insere via Supabase, ou emite o SQL de seed idempotente
para aplicar direto no Studio (caminho de produção). Mesmo padrão do
import_consultas_particulares (issue #288), generalizado por tabela.

O texto passa pelo sanitizador de tipografia do app (ADR 0013): travessão e
meia-risca do dado fonte viram vírgula/hífen, porque a Ana repassa esses
campos literalmente a pacientes.

Uso:
  uv run python -m scripts.oneshot.import_tabelas_ana <tabela> <export.csv>        # insere no banco do .env
  uv run python -m scripts.oneshot.import_tabelas_ana <tabela> <export.csv> --sql  # imprime INSERTs

Tabelas: exames | cirurgias_estimativas
"""

from __future__ import annotations

import csv
import sys

from app.utils.text_sanitizer import sanitizar_estrutura


def _texto(linha: dict, coluna: str) -> str:
    return linha[coluna].strip()


def _valor(linha: dict, coluna: str) -> float:
    """Converte o formato do NocoDB ("R$ 6.000,00") em número."""
    limpo = linha[coluna].replace("R$", "").replace(".", "").replace(",", ".").strip()
    return float(limpo)


def _data(linha: dict, coluna: str) -> str:
    """Converte DD/MM/AAAA em AAAA-MM-DD (formato do Postgres)."""
    dia, mes, ano = linha[coluna].strip().split("/")
    return f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"


def _flag(linha: dict, coluna: str) -> bool:
    return linha[coluna].strip().upper() == "S"


# Por tabela: coluna destino -> (coluna do export, parser). O ON CONFLICT do
# seed usa `conflict` (a chave natural da tabela) para não sobrescrever
# edições feitas depois no admin.
TABELAS: dict[str, dict] = {
    "exames": {
        "conflict": "nome_exame",
        "colunas": {
            "nome_exame": ("Nome_Exame", _texto),
            "tipo_exame": ("Tipo_Exame", _texto),
            "convenio_aceito": ("Convenio_Aceito", _flag),
            "valor_particular_rs": ("Valor_Particular_RS", _valor),
            "requer_pedido_medico": ("Requer_Pedido_Medico", _flag),
            "preparo_necessario": ("Preparo_Necessario", _flag),
            "instrucoes_preparo_completas": ("Instrucoes_Preparo_Completas", _texto),
            "tempo_resultado": ("Tempo_Resultado", _texto),
            "local_realizacao": ("Local_Realizacao", _texto),
            "diferencial_1": ("Diferencial_1", _texto),
            "diferencial_2": ("Diferencial_2", _texto),
            "observacoes_ana": ("Observacoes_Ana", _texto),
            "ativo": ("Ativo", _flag),
            "ultima_atualizacao": ("Ultima_Atualizacao", _data),
        },
    },
    "cirurgias_estimativas": {
        "conflict": "procedimento",
        "colunas": {
            "procedimento": ("Procedimento", _texto),
            "descricao_procedimento": ("Descricao_Procedimento", _texto),
            "honorarios_equipe_rs": ("Honorarios_Equipe_RS", _valor),
            "valor_internacao_rs": ("Valor_Internacao_RS", _valor),
            "estimativa_total_rs": ("Estimativa_Total_RS", _valor),
            "o_que_inclui_honorarios": ("O_Que_Inclui_Honorarios", _texto),
            "o_que_inclui_internacao": ("O_Que_Inclui_Internacao", _texto),
            "diferencial_1": ("Diferencial_1", _texto),
            "diferencial_2": ("Diferencial_2", _texto),
            "caveat_obrigatorio_ana": ("Caveat_Obrigatorio_Ana", _texto),
            "observacoes_ana": ("Observacoes_Ana", _texto),
            "ativo": ("Ativo", _flag),
            "ultima_atualizacao": ("Ultima_Atualizacao", _data),
        },
    },
}


def parse_export(tabela: str, csv_path: str) -> list[dict]:
    """Lê o export do NocoDB e devolve as rows no schema da tabela dada."""
    spec = TABELAS[tabela]
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            rows.append(
                sanitizar_estrutura(
                    {destino: parser(linha, fonte) for destino, (fonte, parser) in spec["colunas"].items()}
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


def to_sql(tabela: str, rows: list[dict]) -> str:
    """SQL de seed idempotente (ON CONFLICT na chave natural não sobrescreve edição posterior)."""
    spec = TABELAS[tabela]
    colunas = list(rows[0].keys())
    values = ",\n".join("  (" + ", ".join(_sql_literal(r[c]) for c in colunas) + ")" for r in rows)
    return (
        f"INSERT INTO {tabela} ({', '.join(colunas)})\nVALUES\n{values}\nON CONFLICT ({spec['conflict']}) DO NOTHING;"
    )


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in TABELAS:
        print(__doc__)
        sys.exit(1)
    tabela, csv_path = sys.argv[1], sys.argv[2]
    rows = parse_export(tabela, csv_path)
    if "--sql" in sys.argv:
        print(to_sql(tabela, rows))
        return
    from app.dependencies import get_supabase_client

    supabase = get_supabase_client()
    # ignore_duplicates: mesma semântica do --sql (DO NOTHING), não sobrescreve
    # edições feitas depois no admin.
    result = (
        supabase.table(tabela).upsert(rows, on_conflict=TABELAS[tabela]["conflict"], ignore_duplicates=True).execute()
    )
    print(f"Importadas {len(result.data or [])} rows em {tabela}.")


if __name__ == "__main__":
    main()
