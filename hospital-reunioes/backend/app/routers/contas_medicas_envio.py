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

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.descarte import (
    ContaNaoEncontradaError,
    NaoDescartavelError,
    SemPermissaoDeDescartarError,
    descartar,
    pode_descartar,
)
from app.services.contas_medicas.envio import (
    LIMITE_POR_ARQUIVO,
    ArquivoRecebido,
    EnvioNaoEncontradoError,
    receber,
)
from app.services.contas_medicas.erro_da_conta import arquivo_da_etapa, detalhe_legivel
from app.services.contas_medicas.fila import NAO_PRONTAS, envios_da_pessoa, fila_da_pessoa
from app.services.contas_medicas.guia import MARCADAS, linha_pendente
from app.services.contas_medicas.painel_do_processamento import (
    ContaNaoEncontradaError as ContaDoPainelNaoEncontradaError,
)
from app.services.contas_medicas.painel_do_processamento import detalhe as detalhe_do_processamento
from app.services.contas_medicas.reanalise import (
    ContaNaoEncontradaError as ContaAAnalisarNaoEncontradaError,
)
from app.services.contas_medicas.reanalise import (
    NaoAnalisavelError,
    SemPermissaoError,
    acao_do_cartao,
    analisar_assim_mesmo,
    analisar_de_novo,
    com_pdf_guardado,
    pode_analisar_assim_mesmo,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_ENVIAR = require_permissao_cm("enviar_contas")
# "Analisar contas" na tela; a chave guarda o nome antigo (ADR 0073).
_PODE_ANALISAR = require_permissao_cm("enviar_corrigir_contas")
# Descartar e Analisar de novo: quem enviou ou quem tem o Painel completo,
# decidido na regra (issues #1338 e #1339).
_TEM_O_EIXO = require_permissao_cm()


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


def _paginas_do_prontuario(supabase: Client, contas: list[dict]) -> dict[str, dict]:
    """As páginas do Prontuário de cada atendimento (issue #1336) e, delas, as
    que vão por OCR (issue #1419). Com o prontuário reenviado, vale o último
    que chegou."""
    ids = list({c["atendimento_id"] for c in contas if c.get("atendimento_id")})
    if not ids:
        return {}
    prontuarios = (
        supabase.table("cm_arquivo")
        .select("atendimento_id, paginas, paginas_ocr, criado_em")
        .in_("atendimento_id", ids)
        .eq("tipo", "PRONTUARIO")
        .order("criado_em")
        .execute()
        .data
    )
    # Em ordem de chegada: o último de cada atendimento sobrescreve os de antes.
    return {p["atendimento_id"]: p for p in prontuarios or []}


def _dias_de_internacao(conta: dict) -> int | None:
    """Os dias do período da Conta, contados como diárias: do início ao fim.
    A internação que começa e termina no mesmo dia conta um."""
    if not (conta.get("periodo_inicio") and conta.get("periodo_fim")):
        return None
    dias = (date.fromisoformat(conta["periodo_fim"]) - date.fromisoformat(conta["periodo_inicio"])).days
    return max(dias, 1)


def _contagens(conta: dict) -> dict:
    """Quantos itens da conta e quantos eventos do prontuário o Motor gravou,
    só na conta pronta (issue #1419). A conta pronta antes desta fatia e a que
    voltou para a fila ficam sem as contagens."""
    faltantes = conta.get("faltantes")
    contagens = faltantes.get("contagens") if isinstance(faltantes, dict) else None
    if conta.get("situacao") in NAO_PRONTAS or not isinstance(contagens, dict):
        return {"itens_lidos": None, "eventos_lidos": None}
    return {"itens_lidos": contagens.get("itens"), "eventos_lidos": contagens.get("eventos")}


def _falta(conta: dict) -> str | None:
    if conta.get("situacao") != "AGUARDANDO_ARQUIVO":
        return None
    return "prontuario" if conta.get("arquivo_id") else "conta"


def _erro(conta: dict, guardado: bool) -> dict:
    """O Código do erro da conta em Erro (issue #1337): o código, o detalhe
    técnico numa linha, a hora do erro, o quadrado que fica vermelho e a ação
    que resolve, que vira Enviar de novo com o PDF fora do bucket (issue
    #1339). Fora do Erro, tudo nulo."""
    if conta.get("situacao") != "ERRO":
        return {"erro_codigo": None, "erro_detalhe": None, "erro_em": None, "erro_arquivo": None, "erro_acao": None}
    detalhe = conta.get("erro_detalhe") or {}
    return {
        "erro_codigo": conta.get("erro_codigo"),
        "erro_detalhe": detalhe_legivel(detalhe),
        "erro_em": detalhe.get("em"),
        "erro_arquivo": arquivo_da_etapa(detalhe.get("etapa")),
        "erro_acao": acao_do_cartao(conta, guardado),
    }


def _processamento(conta: dict) -> dict:
    """A Etapa do processamento da conta em Processando (issue #1416): a etapa
    da tela, a parte do Passo A, desde quando, o início do processamento e a
    tentativa. Fora de Processando, tudo nulo."""
    if conta.get("situacao") != "PROCESSANDO":
        return dict.fromkeys(("etapa", "parte", "partes", "etapa_desde", "processando_desde", "tentativa"))
    return {
        "etapa": conta.get("etapa_atual"),
        "parte": conta.get("etapa_parte"),
        "partes": conta.get("etapa_partes"),
        "etapa_desde": conta.get("etapa_desde"),
        "processando_desde": conta.get("processando_desde"),
        "tentativa": conta.get("tentativas"),
    }


def _item(
    conta: dict, atendimento: dict, linhas: list[dict], prontuario: dict, operadora: dict, guardado: bool
) -> dict:
    """A conta como a fila mostra: identificada pelo atendimento, com a conta
    como complemento. O valor da conta não entra no cartão do envio: a Fila
    nunca anda por valor."""
    da_faturista = [linha for linha in linhas if linha.get("acao") != "VALIDAR"]
    return {
        "id": conta["id"],
        "numero_atendimento": atendimento.get("numero_atendimento"),
        "numero_conta": conta.get("numero_conta"),
        "situacao": conta.get("situacao"),
        "falta": _falta(conta),
        "periodo_inicio": conta.get("periodo_inicio"),
        "periodo_fim": conta.get("periodo_fim"),
        # O quadrado da Conta no cartão do envio (issue #1419).
        "operadora": operadora.get("sigla"),
        "dias_internacao": _dias_de_internacao(conta),
        # O quadrado do Prontuário no cartão do envio (issues #1336 e #1419).
        "prontuario_paginas": prontuario.get("paginas"),
        "prontuario_paginas_ocr": prontuario.get("paginas_ocr"),
        **_contagens(conta),
        "nota_entrada": conta.get("nota_entrada") if conta.get("nota_entrada") is not None else conta.get("nota_bruta"),
        # A nota depois do reenvio da conta corrigida (issue #1136); nula sem reenvio.
        "nota_saida": conta.get("nota_saida"),
        "valor_apontado": conta.get("valor_apontado"),
        "itens_feitos": sum(1 for linha in da_faturista if linha.get("estado") in MARCADAS),
        "itens_total": len(da_faturista),
        "pendencias": sum(1 for linha in linhas if linha_pendente(linha)),
        "erro_motivo": conta.get("erro_motivo"),
        **_erro(conta, guardado),
        **_processamento(conta),
        # O botão Analisar assim mesmo, ao lado de Enviar de novo (issue #1401).
        "pode_analisar_assim_mesmo": pode_analisar_assim_mesmo(conta, guardado),
        # O botão Descartar do cartão do envio (issue #1338).
        "pode_descartar": pode_descartar(conta, linhas),
        # Só para quem tem "painel completo": quem está com a conta.
        "com": conta.get("com_quem"),
    }


def _itens(supabase: Client, listas: dict, nomes: tuple[str, ...]) -> dict:
    todas = [conta for nome in nomes for conta in listas[nome]]
    atendimentos = _por_id(supabase, "cm_atendimento", "id", list({c["atendimento_id"] for c in todas}))
    com_operadora = {a["operadora_id"] for a in atendimentos.values() if a.get("operadora_id")}
    operadoras = _por_id(supabase, "cm_operadora", "id", list(com_operadora))
    linhas = _linhas_por_conta(supabase, todas)
    paginas = _paginas_do_prontuario(supabase, todas)
    em_erro = [c for c in todas if c.get("situacao") == "ERRO"]
    guardadas = com_pdf_guardado(supabase, em_erro, datetime.now(UTC))

    def itens(contas: list[dict]) -> list[dict]:
        return [
            _item(
                c,
                atendimentos.get(c["atendimento_id"], {}),
                linhas.get(c["id"], []),
                paginas.get(c["atendimento_id"], {}),
                operadoras.get(atendimentos.get(c["atendimento_id"], {}).get("operadora_id"), {}),
                c["id"] in guardadas,
            )
            for c in contas
        ]

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


@router.get("/contas/{conta_id}/processamento")
@limiter.limit("120/minute")
async def ver_processamento(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_PODE_ENVIAR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """O painel lateral do cartão do envio (issue #1418): as cinco etapas com o
    tempo de cada uma, a tentativa e a posição na fila; o custo da IA, só para
    quem tem "painel completo". A conta de outra pessoa dá 404."""
    try:
        return detalhe_do_processamento(supabase, str(conta_id), me, datetime.now(UTC))
    except ContaDoPainelNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada") from None


@router.post("/contas/{conta_id}/descartar")
@limiter.limit("30/minute")
async def descartar_conta(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_TEM_O_EIXO),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A conta em Erro ou Aguardando arquivo sai do banco, e os PDFs dela, do
    bucket (issue #1338). Pode quem enviou e quem tem o Painel completo."""
    try:
        await run_in_threadpool(descartar, supabase, str(conta_id), me)
    except ContaNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada") from None
    except SemPermissaoDeDescartarError as erro:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(erro)) from None
    except NaoDescartavelError as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from None
    return {"descartada": str(conta_id)}


@router.post("/contas/{conta_id}/analisar-de-novo")
@limiter.limit("30/minute")
async def analisar_conta_de_novo(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_TEM_O_EIXO),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A conta em Erro da IA, da configuração ou do app volta para a fila com
    os PDFs que já estão no bucket (issue #1339). Pode quem enviou e quem tem
    o Painel completo."""
    try:
        await run_in_threadpool(analisar_de_novo, supabase, str(conta_id), me, datetime.now(UTC))
    except ContaAAnalisarNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada") from None
    except SemPermissaoError as erro:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(erro)) from None
    except NaoAnalisavelError as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from None
    return {"situacao": "NA_FILA"}


@router.post("/contas/{conta_id}/analisar-assim-mesmo")
@limiter.limit("30/minute")
async def analisar_conta_assim_mesmo(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_TEM_O_EIXO),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A conta parada por folha digitalizada que não deu para ler
    (CM-ARQ-DIGITALIZADO) volta para a fila e a análise segue com a ressalva
    no Parecer parcial (issue #1401). As guardas do Analisar de novo."""
    try:
        await run_in_threadpool(analisar_assim_mesmo, supabase, str(conta_id), me, datetime.now(UTC))
    except ContaAAnalisarNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada") from None
    except SemPermissaoError as erro:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(erro)) from None
    except NaoAnalisavelError as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from None
    return {"situacao": "NA_FILA"}
