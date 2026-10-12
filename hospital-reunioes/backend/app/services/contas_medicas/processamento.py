"""O processamento da fila de Contas médicas (issue #1124, PRD #1113, ADR 0070).

A fila vive em `cm_conta` (ADR 0070, decisão 5): o envio deixa a conta
`NA_FILA` e um job do APScheduler a consome no mesmo processo do app.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Quantas contas da cabeça da fila o claim tenta antes de desistir: perder a
# primeira para a outra vaga não pode deixar a vaga parada até o próximo tique.
_CANDIDATAS = 5

# A conta em PROCESSANDO há mais que isto ficou para trás (restart do app no
# meio da análise): volta para a fila. A leitura de um prontuário de 900
# páginas tem prazo de 120 segundos, então 15 minutos não cortam análise viva.
PRAZO_DA_ANALISE = timedelta(minutes=15)
MAXIMO_DE_TENTATIVAS = 3

MENSAGEM_TENTATIVAS_ESGOTADAS = "A análise não terminou em três tentativas. Envie de novo."


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


def _devolver(supabase, conta: dict, erro_motivo: str) -> None:
    """Fim de uma tentativa que não deu certo: volta para a fila, ou, na
    terceira, Erro com a frase. A guarda das tentativas no UPDATE deixa intacta
    a conta que outra vaga já pegou de novo."""
    tentativas = conta.get("tentativas") or 0
    if tentativas >= MAXIMO_DE_TENTATIVAS:
        campos = {"situacao": "ERRO", "erro_motivo": erro_motivo, "processando_desde": None}
    else:
        campos = {"situacao": "NA_FILA", "processando_desde": None}
    supabase.table("cm_conta").update(campos).eq("id", conta["id"]).eq("situacao", "PROCESSANDO").eq(
        "tentativas", tentativas
    ).execute()


def devolver_presas(supabase, agora: datetime) -> int:
    """As contas em PROCESSANDO há mais de 15 minutos voltam para a fila; na
    terceira tentativa, Erro. Devolve quantas foram mexidas."""
    presas = (
        supabase.table("cm_conta")
        .select("id, tentativas")
        .eq("situacao", "PROCESSANDO")
        .lt("processando_desde", (agora - PRAZO_DA_ANALISE).isoformat())
        .execute()
        .data
        or []
    )
    for conta in presas:
        _devolver(supabase, conta, MENSAGEM_TENTATIVAS_ESGOTADAS)
    return len(presas)
