"""Envio e fila de Contas médicas (issue #1123, PRD #1113, ADR 0070).

A tela Contas: a faturista arrasta a Conta e o Prontuário do MV, recebe na
hora o "Último envio" por atendimento e vê a fila em ordem de envio. A regra do
envio mora em `services/contas_medicas/envio`; aqui ficam o gate e o formato.

Router próprio, com o mesmo prefixo do módulo, como o do Guia e o das
operadoras. O envio e "Meus envios" pedem "Enviar contas"; a Fila, "Minhas" e
as Concluídas pedem "Analisar contas" (a chave `enviar_corrigir_contas`, issue
#1308, ADR 0073). Quem decide o que cada pessoa vê é a Fila de contas, em
`services/contas_medicas/fila` (issue #1307).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.envio import (
    LIMITE_POR_ARQUIVO,
    ArquivoRecebido,
    EnvioNaoEncontradoError,
    receber,
)
from app.services.contas_medicas.fila import envios_da_pessoa, fila_da_pessoa
from app.services.contas_medicas.guia import MARCADAS, linha_pendente

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_ENVIAR = require_permissao_cm("enviar_contas")
# "Analisar contas" na tela; a chave guarda o nome antigo (ADR 0073).
_PODE_ANALISAR = require_permissao_cm("enviar_corrigir_contas")


@router.post("/envios")
@limiter.limit("60/minute")
async def enviar_arquivos(
    request: Request,
    arquivos: list[UploadFile] = File(...),
    envio_id: UUID | None = Form(default=None),
    me: dict = Depends(_PODE_ENVIAR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Um lote de PDFs de um envio. Sem `envio_id`, abre um envio novo; com
    ele, o lote entra no mesmo envio. Devolve o "Último envio" e as recusas."""
    recebidos = []
    for arquivo in arquivos:
        # Lê um byte além do limite: basta para recusar sem ler o resto.
        conteudo = await arquivo.read(LIMITE_POR_ARQUIVO + 1)
        recebidos.append(ArquivoRecebido(nome=arquivo.filename or "arquivo.pdf", conteudo=conteudo))
    try:
        # A leitura dos PDFs leva segundos: fora do laço de eventos.
        return await run_in_threadpool(
            receber,
            supabase,
            me["id"],
            str(envio_id) if envio_id else None,
            recebidos,
            datetime.now(UTC),
        )
    except EnvioNaoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado") from None


def _por_id(supabase: Client, tabela: str, coluna: str, valores: list) -> dict:
    if not valores:
        return {}
    linhas = supabase.table(tabela).select("*").in_(coluna, valores).execute().data or []
    return {linha[coluna]: linha for linha in linhas}


def _linhas_por_conta(supabase: Client, contas: list[dict]) -> dict[str, list[dict]]:
    ids = [c["id"] for c in contas]
    if not ids:
        return {}
    linhas = supabase.table("cm_guia_linha").select("conta_id, acao, estado").in_("conta_id", ids).execute().data
    por_conta: dict[str, list[dict]] = {}
    for linha in linhas or []:
        por_conta.setdefault(linha["conta_id"], []).append(linha)
    return por_conta


def _falta(conta: dict) -> str | None:
    if conta.get("situacao") != "AGUARDANDO_ARQUIVO":
        return None
    return "prontuario" if conta.get("arquivo_id") else "conta"


def _item(conta: dict, atendimento: dict, linhas: list[dict]) -> dict:
    """A conta como a fila mostra: identificada pelo atendimento, com a conta como complemento."""
    da_faturista = [linha for linha in linhas if linha.get("acao") != "VALIDAR"]
    return {
        "id": conta["id"],
        "numero_atendimento": atendimento.get("numero_atendimento"),
        "numero_conta": conta.get("numero_conta"),
        "situacao": conta.get("situacao"),
        "falta": _falta(conta),
        "periodo_inicio": conta.get("periodo_inicio"),
        "periodo_fim": conta.get("periodo_fim"),
        "nota_entrada": conta.get("nota_entrada") if conta.get("nota_entrada") is not None else conta.get("nota_bruta"),
        # A nota depois do reenvio da conta corrigida (issue #1136); nula sem reenvio.
        "nota_saida": conta.get("nota_saida"),
        "valor_apontado": conta.get("valor_apontado"),
        "itens_feitos": sum(1 for linha in da_faturista if linha.get("estado") in MARCADAS),
        "itens_total": len(da_faturista),
        "pendencias": sum(1 for linha in linhas if linha_pendente(linha)),
        "erro_motivo": conta.get("erro_motivo"),
        # Só para quem tem "painel completo": quem está com a conta.
        "com": conta.get("com_quem"),
    }


def _itens(supabase: Client, listas: dict, nomes: tuple[str, ...]) -> dict:
    todas = [conta for nome in nomes for conta in listas[nome]]
    atendimentos = _por_id(supabase, "cm_atendimento", "id", list({c["atendimento_id"] for c in todas}))
    linhas = _linhas_por_conta(supabase, todas)

    def itens(contas: list[dict]) -> list[dict]:
        return [_item(c, atendimentos.get(c["atendimento_id"], {}), linhas.get(c["id"], [])) for c in contas]

    return {"todas": listas["todas"], **{nome: itens(listas[nome]) for nome in nomes}}


@router.get("/fila")
@limiter.limit("120/minute")
async def ver_fila(
    request: Request,
    me: dict = Depends(_PODE_ANALISAR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A Fila, "Minhas" e as Concluídas da pessoa. Quem tem "painel completo"
    vê as de todas, com quem está com cada uma."""
    return _itens(supabase, fila_da_pessoa(supabase, me), ("fila", "minhas", "concluidas"))


@router.get("/meus-envios")
@limiter.limit("120/minute")
async def ver_meus_envios(
    request: Request,
    me: dict = Depends(_PODE_ENVIAR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """As contas que a pessoa enviou e ainda não ficaram prontas. Quem tem
    "painel completo" vê os envios de todos, com quem enviou cada um."""
    return _itens(supabase, envios_da_pessoa(supabase, me), ("meus_envios",))
