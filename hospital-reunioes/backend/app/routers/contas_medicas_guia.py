"""O Guia da faturista em Contas médicas (issue #1121, PRD #1113, ADR 0070).

A faturista abre o Guia de uma Conta, corrige no MV linha por linha, marca
Feito, Não procede ou Bloqueado e conclui. As linhas já estão gravadas em
`cm_guia_linha` (quem as escreve é o processamento da fila); aqui elas são
lidas, marcadas e fechadas.

Toda rota passa pelo gate "enviar e corrigir contas" e depois pelo filtro da
Conta: a faturista só abre a Conta em que é `faturista_id`; quem tem "painel
completo" abre qualquer uma.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.guia import agrupar_por_dia_e_setor, numeros_do_topo

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_CORRIGIR = require_permissao_cm("enviar_corrigir_contas")

CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")
# As situações em que o Guia já existe. Antes disso (aguardando arquivo, na
# fila, processando, erro) não há linha para mostrar.
COM_GUIA = ("A_FAZER", "EM_CORRECAO", "RETORNO", *CONCLUIDAS)


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _primeira(supabase: Client, tabela: str, coluna: str, valor) -> dict | None:
    linhas = supabase.table(tabela).select("*").eq(coluna, valor).limit(1).execute().data or []
    return linhas[0] if linhas else None


def _conta_do_guia(supabase: Client, conta_id: UUID, me: dict) -> dict:
    """A Conta, se a pessoa pode abrir o Guia dela, e se o Guia existe."""
    conta = _primeira(supabase, "cm_conta", "id", str(conta_id))
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if conta.get("faturista_id") != me.get("id") and "painel_completo" not in me["permissoes_cm"]:
        raise HTTPException(status_code=403, detail="Esta conta é de outra faturista")
    if conta.get("situacao") not in COM_GUIA:
        raise HTTPException(status_code=409, detail="O guia desta conta ainda não está pronto")
    return conta


def _linhas(supabase: Client, conta_id: str) -> list[dict]:
    return supabase.table("cm_guia_linha").select("*").eq("conta_id", conta_id).execute().data or []


@router.get("/contas/{conta_id}/guia")
@limiter.limit("120/minute")
async def abrir_guia(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """O Guia da Conta: cabeçalho, os três números e as linhas por dia e setor."""
    conta = _conta_do_guia(supabase, conta_id, me)
    if conta.get("situacao") == "A_FAZER":
        # Condicional na situação: duas aberturas ao mesmo tempo carimbam uma vez.
        supabase.table("cm_conta").update({"situacao": "EM_CORRECAO", "aberta_em": _agora()}).eq("id", conta["id"]).eq(
            "situacao", "A_FAZER"
        ).execute()
        conta["situacao"] = "EM_CORRECAO"

    atendimento = _primeira(supabase, "cm_atendimento", "id", conta.get("atendimento_id")) or {}
    operadora = _primeira(supabase, "cm_operadora", "id", atendimento.get("operadora_id")) or {}
    linhas = _linhas(supabase, conta["id"])
    concluida = conta.get("situacao") in CONCLUIDAS
    return {
        "cabecalho": {
            "numero_atendimento": atendimento.get("numero_atendimento"),
            "paciente_rotulo": atendimento.get("paciente_rotulo"),
            "numero_conta": conta.get("numero_conta"),
            "operadora": operadora.get("sigla"),
            "coluna_preco": atendimento.get("coluna_preco"),
            "periodo_inicio": conta.get("periodo_inicio"),
            "periodo_fim": conta.get("periodo_fim"),
            "situacao": conta.get("situacao"),
            "parecer_parcial": bool(conta.get("parecer_parcial")),
            "faltantes": conta.get("faltantes") or [],
        },
        "numeros": numeros_do_topo(linhas, conta.get("total_lancado"), concluida=concluida),
        "grupos": agrupar_por_dia_e_setor(linhas),
    }
