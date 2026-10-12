"""O processamento da fila de Contas médicas (issue #1124, PRD #1113, ADR 0070).

A fila vive em `cm_conta` (ADR 0070, decisão 5): o envio deixa a conta
`NA_FILA` e um job do APScheduler a consome no mesmo processo do app.
"""

from __future__ import annotations

from datetime import datetime

# Quantas contas da cabeça da fila o claim tenta antes de desistir: perder a
# primeira para a outra vaga não pode deixar a vaga parada até o próximo tique.
_CANDIDATAS = 5


def pegar_da_fila(supabase, agora: datetime) -> dict | None:
    """Claim atômico da próxima conta `NA_FILA`, na ordem de envio.

    O PostgREST não dá `FOR UPDATE SKIP LOCKED` sem uma função no banco, e a
    116 é a única migration do PRD. O claim é o `UPDATE ... WHERE situacao =
    'NA_FILA'` da ADR: o Postgres reavalia o WHERE da segunda escrita depois
    da primeira, então duas chamadas que leram a mesma conta não a pegam as
    duas; a que perdeu tenta a seguinte.
    """
    candidatas = (
        supabase.table("cm_conta")
        .select("id, tentativas")
        .eq("situacao", "NA_FILA")
        .order("ordem_fila")
        .limit(_CANDIDATAS)
        .execute()
        .data
        or []
    )
    for candidata in candidatas:
        pegas = (
            supabase.table("cm_conta")
            .update(
                {
                    "situacao": "PROCESSANDO",
                    "processando_desde": agora.isoformat(),
                    "tentativas": (candidata.get("tentativas") or 0) + 1,
                }
            )
            .eq("id", candidata["id"])
            .eq("situacao", "NA_FILA")
            .execute()
            .data
            or []
        )
        if pegas:
            return pegas[0]
    return None
