"""O Guia da faturista em Contas médicas (issue #1121, PRD #1113, ADR 0070).

A faturista abre o Guia de uma Conta, corrige no MV linha por linha, marca
Feito, Não procede ou Bloqueado e conclui. As linhas já estão gravadas em
`cm_guia_linha` (quem as escreve é o processamento da fila); aqui elas são
lidas, marcadas e fechadas.

Toda rota passa pelo gate "enviar e corrigir contas" e depois pelo filtro da
Conta: a faturista só abre a Conta em que é `faturista_id`; quem tem "painel
completo" abre qualquer uma.
"""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas import reenvio
from app.services.contas_medicas.envio import LIMITE_POR_ARQUIVO, MENSAGEM_ARQUIVO_GRANDE
from app.services.contas_medicas.guia import (
    agrupar_por_dia_e_setor,
    linha_nao_conferida,
    linha_pendente,
    nota_de_entrada,
    numeros_do_topo,
)
from app.services.contas_medicas.regra_nova import SITUACOES_REANALISAVEIS, regra_nova_desde_a_analise
from app.services.contas_medicas.validacao import (
    acompanhar_marcacao,
    linhas_do_retorno,
    respostas_da_conta,
    temas_da_observacao,
)
from app.services.contas_medicas_conta import ErroLeitura

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_CORRIGIR = require_permissao_cm("enviar_corrigir_contas")
_PODE_MEXER_EM_REGRA = require_permissao_cm("regra_contratual_tabelas")

CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")
# As situações em que o Guia já existe. Antes disso (aguardando arquivo, na
# fila, processando, erro) não há linha para mostrar.
COM_GUIA = ("A_FAZER", "EM_CORRECAO", "RETORNO", *CONCLUIDAS)
# As situações em que "Reanalisar" vale: o Guia pronto e ainda em aberto.
REANALISAVEIS = SITUACOES_REANALISAVEIS


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _primeira(supabase: Client, tabela: str, coluna: str, valor) -> dict | None:
    if valor is None:
        return None
    linhas = supabase.table(tabela).select("*").eq(coluna, valor).limit(1).execute().data or []
    return linhas[0] if linhas else None


def _conta_do_guia(
    supabase: Client,
    conta_id: UUID,
    me: dict,
    aceitas: tuple[str, ...] = COM_GUIA,
    recusa: str = "O guia desta conta ainda não está pronto",
) -> dict:
    """A Conta, se a pessoa pode abrir o Guia dela, e se o Guia existe."""
    conta = _primeira(supabase, "cm_conta", "id", str(conta_id))
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if conta.get("faturista_id") != me.get("id") and "painel_completo" not in me["permissoes_cm"]:
        raise HTTPException(status_code=403, detail="Esta conta é de outra faturista")
    if conta.get("situacao") not in aceitas:
        raise HTTPException(status_code=409, detail=recusa)
    return conta


def _faltantes(conta: dict) -> list:
    """O que o prontuário não trouxe. O processamento (#1124) grava em
    `faltantes` os itens e, ao lado, o tempo de cada etapa, que a 116 não tem
    coluna própria para guardar."""
    faltantes = conta.get("faltantes") or []
    return (faltantes.get("itens") or []) if isinstance(faltantes, dict) else faltantes


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
    dados_do_reenvio = reenvio.resumo(conta)
    marcas = (dados_do_reenvio or {}).get("linhas") or {}
    # Em Retorno, a faturista vê só o que a Validação devolveu.
    da_tela = linhas_do_retorno(supabase, linhas) if conta.get("situacao") == "RETORNO" else linhas
    grupos = agrupar_por_dia_e_setor(da_tela)
    for grupo in grupos:
        for linha in grupo["linhas"]:
            linha["reenvio"] = marcas.get(linha["id"])
            # A versão da tabela que deu o preço fica só registrada (#1206).
            linha.pop("tabela_id", None)
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
            "faltantes": _faltantes(conta),
        },
        "numeros": numeros_do_topo(linhas, conta.get("total_lancado"), concluida=concluida),
        "grupos": grupos,
        # O reenvio da conta corrigida (issue #1136): a nota de saída e as
        # marcas por linha, nulo enquanto a conta não foi reenviada.
        "reenvio": dados_do_reenvio,
        "pode_reenviar": concluida,
        # O "Responder ao time" da Validação sobre o que esta conta levantou.
        "respostas": respostas_da_conta(supabase, conta["id"], linhas),
        # O botão "Reanalisar": a tela desenha pelo que vem aqui, e a rota decide.
        "pode_reanalisar": "regra_contratual_tabelas" in me["permissoes_cm"] and conta.get("situacao") in REANALISAVEIS,
        # A conta analisada com uma memória que já mudou: o botão vira "Reanalisar com a regra nova".
        "regra_nova_desde_analise": regra_nova_desde_a_analise(supabase, conta, operadora.get("id")),
    }


def _conta_em_correcao(supabase: Client, conta_id: UUID, me: dict) -> dict:
    """A Conta cujo Guia ainda aceita marcação: concluída não muda mais."""
    conta = _conta_do_guia(supabase, conta_id, me)
    if conta.get("situacao") in CONCLUIDAS:
        raise HTTPException(status_code=409, detail="A conta já foi concluída")
    return conta


def _linha_da_faturista(supabase: Client, conta: dict, linha_id: UUID) -> dict:
    """A linha da Conta que a faturista pode marcar. Validar não tem botão."""
    linhas = (
        supabase.table("cm_guia_linha")
        .select("*")
        .eq("id", str(linha_id))
        .eq("conta_id", conta["id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not linhas:
        raise HTTPException(status_code=404, detail="Linha não encontrada nesta conta")
    if linhas[0].get("acao") == "VALIDAR":
        raise HTTPException(status_code=409, detail="O item já foi para a validação")
    return linhas[0]


def _gravar_marcacao(supabase: Client, linha: dict, me: dict, estado: str, motivo=None, texto=None) -> dict:
    """Toda marcação, inclusive o Desfazer, grava quem e quando."""
    campos = {
        "estado": estado,
        "motivo_nao_procede": motivo,
        "texto_nao_procede": texto,
        "marcado_por": me.get("id"),
        "marcado_em": _agora(),
    }
    gravada = supabase.table("cm_guia_linha").update(campos).eq("id", linha["id"]).execute().data or []
    resultado = gravada[0] if gravada else {**linha, **campos}
    # A versão da tabela que deu o preço fica só registrada (#1206).
    resultado = {chave: valor for chave, valor in resultado.items() if chave != "tabela_id"}
    return {**resultado, "nao_conferido": linha_nao_conferida(resultado)}


class Marcacao(BaseModel):
    estado: Literal["FEITO", "NAO_PROCEDE", "BLOQUEADO"]
    motivo: Literal["JA_ESTA_NA_CONTA", "SEM_EVIDENCIA", "REGRA_E_OUTRA", "OUTRO"] | None = None
    texto: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _motivo_do_nao_procede(self):
        self.texto = (self.texto or "").strip() or None
        if self.estado != "NAO_PROCEDE":
            self.motivo, self.texto = None, None
        elif self.motivo is None:
            raise ValueError("Escolha o motivo do Não procede")
        elif self.motivo == "OUTRO" and not self.texto:
            raise ValueError('Em "outro", escreva o motivo')
        return self


@router.post("/contas/{conta_id}/guia/linhas/{linha_id}/marcacao")
@limiter.limit("240/minute")
async def marcar_linha(
    request: Request,
    conta_id: UUID,
    linha_id: UUID,
    corpo: Marcacao,
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Feito, Não procede (com motivo) ou Bloqueado numa linha do Guia. O
    Bloqueado e o Não procede caem na fila de Validação."""
    conta = _conta_em_correcao(supabase, conta_id, me)
    linha = _linha_da_faturista(supabase, conta, linha_id)
    marcada = _gravar_marcacao(supabase, linha, me, corpo.estado, corpo.motivo, corpo.texto)
    acompanhar_marcacao(supabase, conta, marcada)
    return marcada


@router.delete("/contas/{conta_id}/guia/linhas/{linha_id}/marcacao")
@limiter.limit("240/minute")
async def desfazer_marcacao(
    request: Request,
    conta_id: UUID,
    linha_id: UUID,
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Desfazer: a linha volta a aberta, enquanto a Conta não foi concluída."""
    conta = _conta_em_correcao(supabase, conta_id, me)
    linha = _linha_da_faturista(supabase, conta, linha_id)
    desfeita = _gravar_marcacao(supabase, linha, me, "ABERTA")
    acompanhar_marcacao(supabase, conta, desfeita)
    return desfeita


class Dia(BaseModel):
    data: date | None = None
    setor: str | None = Field(default=None, max_length=200)


@router.post("/contas/{conta_id}/guia/dia/feito")
@limiter.limit("120/minute")
async def marcar_o_dia_como_feito(
    request: Request,
    conta_id: UUID,
    corpo: Dia,
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Feito em todas as linhas abertas do grupo (dia e setor). As já marcadas
    e as em validação ficam como estão."""
    conta = _conta_em_correcao(supabase, conta_id, me)
    data = corpo.data.isoformat() if corpo.data else None
    abertas = [
        linha["id"]
        for linha in _linhas(supabase, conta["id"])
        if linha.get("data") == data
        and linha.get("setor") == corpo.setor
        and linha.get("estado") == "ABERTA"
        and linha.get("acao") != "VALIDAR"
    ]
    if not abertas:
        return {"marcadas": 0}
    campos = {"estado": "FEITO", "marcado_por": me.get("id"), "marcado_em": _agora()}
    gravadas = (
        supabase.table("cm_guia_linha").update(campos).in_("id", abertas).eq("estado", "ABERTA").execute().data or []
    )
    return {"marcadas": len(gravadas)}


class Conclusao(BaseModel):
    observacao: str | None = Field(default=None, max_length=4000)


@router.post("/contas/{conta_id}/guia/concluir")
@limiter.limit("60/minute")
async def concluir_guia(
    request: Request,
    conta_id: UUID,
    corpo: Conclusao,
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Concluir é sempre possível. Sem pendência, a Conta fica Concluída; com
    linha sem marcação, em validação ou bloqueada, Concluída com pendência.

    A nota de entrada é recalculada sem as linhas Não procede; a nota bruta
    fica como o processamento gravou. A resposta traz a próxima Conta A fazer
    da faturista na ordem de envio, para a tela abrir em seguida.
    """
    conta = _conta_em_correcao(supabase, conta_id, me)
    linhas = _linhas(supabase, conta["id"])
    pendencias = sum(1 for linha in linhas if linha_pendente(linha))
    situacao = "CONCLUIDA_COM_PENDENCIA" if pendencias else "CONCLUIDA"
    sem_nao_procede = [linha for linha in linhas if linha.get("estado") != "NAO_PROCEDE"]
    nota = nota_de_entrada(sem_nao_procede, conta.get("total_lancado")).nota

    supabase.table("cm_conta").update({"situacao": situacao, "nota_entrada": nota, "concluida_em": _agora()}).eq(
        "id", conta["id"]
    ).execute()

    observacao = (corpo.observacao or "").strip()
    if observacao:
        gravada = (
            supabase.table("cm_observacao")
            .insert({"conta_id": conta["id"], "autor_id": me.get("id"), "texto": observacao})
            .execute()
        )
        # A observação cai na fila de Validação, no tema da regra que ela cita.
        temas_da_observacao(supabase, conta, gravada.data[0])

    return {
        "situacao": situacao,
        "pendencias": pendencias,
        "nota_entrada": nota,
        "nota_bruta": conta.get("nota_bruta"),
        "proxima_conta_id": _proxima_a_fazer(supabase, conta.get("faturista_id")),
    }


@router.post("/contas/{conta_id}/reenvio")
@limiter.limit("30/minute")
async def reenviar_conta(
    request: Request,
    conta_id: UUID,
    arquivo: UploadFile = File(...),
    me: dict = Depends(_PODE_CORRIGIR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Reenviar conta corrigida (issue #1136): só o PDF da conta, de uma conta
    concluída. Devolve as marcas por linha e a nota de saída. O prontuário não
    é lido de novo e a IA não é chamada."""
    conta = _conta_do_guia(supabase, conta_id, me, CONCLUIDAS, reenvio.MENSAGEM_NAO_CONCLUIDA)
    # Lê um byte além do limite: basta para recusar sem ler o resto.
    conteudo = await arquivo.read(LIMITE_POR_ARQUIVO + 1)
    if len(conteudo) > LIMITE_POR_ARQUIVO:
        raise HTTPException(status_code=422, detail=MENSAGEM_ARQUIVO_GRANDE)
    # A leitura do PDF leva segundos: fora do laço de eventos.
    lida = await run_in_threadpool(reenvio.ler_conta_reenviada, conteudo)
    if isinstance(lida, ErroLeitura):
        raise HTTPException(status_code=422, detail=lida.motivo)
    atendimento = _primeira(supabase, "cm_atendimento", "id", conta.get("atendimento_id")) or {}
    numero = atendimento.get("numero_atendimento")
    if not reenvio.e_a_mesma_conta(conta, numero, lida):
        raise HTTPException(status_code=422, detail=reenvio.mensagem_outra_conta(numero, conta.get("numero_conta")))
    return reenvio.reenviar(supabase, conta, lida, datetime.now(UTC))


@router.post("/contas/{conta_id}/reanalisar")
@limiter.limit("60/minute")
async def reanalisar_conta(
    request: Request,
    conta_id: UUID,
    me: dict = Depends(_PODE_MEXER_EM_REGRA),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Reanalisar (issue #1130): a conta A fazer ou Em correção volta para a
    fila e passa pela análise de novo, com a memória e as tabelas de agora. O
    reprocesso preserva as linhas que a faturista já marcou e troca as abertas.

    Só para quem mexe em regra contratual e tabelas: é quem sabe que a regra
    mudou. A faturista da conta continua a mesma.
    """
    conta = _primeira(supabase, "cm_conta", "id", str(conta_id))
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    # Condicional na situação: a conta que mudou entre a leitura e a escrita
    # (concluída, já na fila) não volta para a análise.
    devolvida = (
        supabase.table("cm_conta")
        .update({"situacao": "NA_FILA", "tentativas": 0, "erro_motivo": None, "processando_desde": None})
        .eq("id", conta["id"])
        .in_("situacao", list(REANALISAVEIS))
        .execute()
        .data
        or []
    )
    if not devolvida:
        raise HTTPException(status_code=409, detail="Só a conta A fazer ou Em correção pode ser reanalisada")
    return {"situacao": "NA_FILA"}


def _proxima_a_fazer(supabase: Client, faturista_id: str | None) -> str | None:
    if not faturista_id:
        return None
    proximas = (
        supabase.table("cm_conta")
        .select("id")
        .eq("faturista_id", faturista_id)
        .eq("situacao", "A_FAZER")
        .order("ordem_fila")
        .limit(1)
        .execute()
        .data
        or []
    )
    return proximas[0]["id"] if proximas else None
