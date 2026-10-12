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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.guia import (
    PENDENTES,
    agrupar_por_dia_e_setor,
    linha_nao_conferida,
    nota_de_entrada,
    numeros_do_topo,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_CORRIGIR = require_permissao_cm("enviar_corrigir_contas")

CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")
# As situações em que o Guia já existe. Antes disso (aguardando arquivo, na
# fila, processando, erro) não há linha para mostrar.
COM_GUIA = ("A_FAZER", "EM_CORRECAO", "RETORNO", *CONCLUIDAS)


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _primeira(supabase: Client, tabela: str, coluna: str, valor) -> dict | None:
    if valor is None:
        return None
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
        "grupos": agrupar_por_dia_e_setor(linhas),
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
    """Feito, Não procede (com motivo) ou Bloqueado numa linha do Guia."""
    conta = _conta_em_correcao(supabase, conta_id, me)
    linha = _linha_da_faturista(supabase, conta, linha_id)
    return _gravar_marcacao(supabase, linha, me, corpo.estado, corpo.motivo, corpo.texto)


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
    return _gravar_marcacao(supabase, linha, me, "ABERTA")


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
    pendencias = sum(1 for linha in linhas if linha.get("estado") in PENDENTES)
    situacao = "CONCLUIDA_COM_PENDENCIA" if pendencias else "CONCLUIDA"
    sem_nao_procede = [linha for linha in linhas if linha.get("estado") != "NAO_PROCEDE"]
    nota = nota_de_entrada(sem_nao_procede, conta.get("total_lancado")).nota

    supabase.table("cm_conta").update({"situacao": situacao, "nota_entrada": nota, "concluida_em": _agora()}).eq(
        "id", conta["id"]
    ).execute()

    observacao = (corpo.observacao or "").strip()
    if observacao:
        supabase.table("cm_observacao").insert(
            {"conta_id": conta["id"], "autor_id": me.get("id"), "texto": observacao}
        ).execute()

    return {
        "situacao": situacao,
        "pendencias": pendencias,
        "nota_entrada": nota,
        "nota_bruta": conta.get("nota_bruta"),
        "proxima_conta_id": _proxima_a_fazer(supabase, conta.get("faturista_id")),
    }


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
