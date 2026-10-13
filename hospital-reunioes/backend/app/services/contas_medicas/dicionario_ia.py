"""O dicionário de itens aprendido com a IA (issue #1135, PRD #1128).

Termo de medicamento da prescrição sem par na conta em nenhuma das três
etapas do casamento (dicionário, marca e concentração, só a marca) vai uma vez
à IA, numa chamada curta com os medicamentos da conta. A proposta entra no
dicionário como `PROPOSTO`, com origem IA, e vale a partir dali: da segunda
conta em diante o termo é código, sem IA. O termo que a IA não soube ligar
também fica, sem código, para não ser perguntado de novo.

A gestão confirma ou rejeita a proposta na tela Operadoras. Rejeitar tira o
código e deixa o termo decidido, sem par.
"""

from __future__ import annotations

import logging
from typing import Any

from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict

from app.services.contas_medicas import ia
from app.services.contas_medicas.conferencia import ProntuarioLido
from app.services.contas_medicas.dicionario import _norm, casar
from app.services.contas_medicas_conta import Conta
from app.services.prompt_loader import load_prompt

__all__ = ["PropostaRecusadaError", "decidir_proposta", "listar_propostas", "propor_termos"]

logger = logging.getLogger(__name__)

# Unique violation do Postgres: a outra parcial gravou o mesmo termo antes.
_TERMO_REPETIDO = "23505"


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Proposta(_Estrito):
    termo: str
    codigo: str | None


class PropostasDoDicionario(_Estrito):
    propostas: list[Proposta]


class PropostaRecusadaError(LookupError):
    """A proposta não existe ou já foi decidida."""


def _termos_sem_par(prontuario: ProntuarioLido, medicamentos: list[dict[str, Any]], dicionario) -> list[str]:
    return sorted(
        {
            _norm(item.nome)
            for item in prontuario.conteudo.prescricao_consolidada
            if (item.secao or "").upper().startswith("MEDICAMENTO")
            and _norm(item.nome)
            and not casar(item.nome, medicamentos, dicionario).itens
        }
    )


def _pergunta(termos: list[str], medicamentos: list[dict[str, Any]]) -> str:
    vistos = {item["codigo"]: item["descricao"] for item in medicamentos}
    linhas = ["TERMOS SEM PAR", *(f"- {termo}" for termo in termos), "", "MEDICAMENTOS DA CONTA", "codigo | descricao"]
    linhas += [f"{codigo} | {descricao}" for codigo, descricao in vistos.items()]
    return "\n".join(linhas)


def propor_termos(
    supabase, prontuario: ProntuarioLido, conta: Conta, dicionario, *, conta_id: str, atendimento_id: str
) -> int:
    """Pergunta à IA o código dos termos sem par que o dicionário ainda não
    conhece e grava as propostas. Devolve quantos termos entraram. A IA fora
    do ar não para a análise: o termo fica para a próxima conta."""
    medicamentos = [{"codigo": i.codigo, "descricao": i.descricao} for i in conta.itens if i.grupo == "MEDICAMENTOS"]
    if not medicamentos:
        return 0
    conhecidos = {
        _norm(linha["termo"]) for linha in supabase.table("cm_item_dicionario").select("termo").execute().data or []
    }
    termos = [termo for termo in _termos_sem_par(prontuario, medicamentos, dicionario) if termo not in conhecidos]
    if not termos:
        return 0
    try:
        resposta = ia.chamada_curta(
            load_prompt("contas_medicas_dicionario"),
            _pergunta(termos, medicamentos),
            PropostasDoDicionario,
            passo="DICIONARIO",
            supabase=supabase,
            conta_id=conta_id,
            atendimento_id=atendimento_id,
        )
    except ia.ErroDaIA as erro:
        logger.warning("[ContasMedicas] Dicionário sem a IA na conta %s: %s", conta_id, erro)
        return 0

    descricoes = {item["codigo"]: item["descricao"] for item in medicamentos}
    # Só código da conta: o que a IA inventar fora da lista vira termo sem par.
    propostos = {_norm(p.termo): p.codigo for p in resposta.propostas if p.codigo in descricoes}
    gravados = 0
    for termo in termos:
        codigo = propostos.get(termo)
        try:
            supabase.table("cm_item_dicionario").insert(
                {
                    "termo": termo,
                    "codigo_conta": codigo,
                    "descricao_conta": descricoes.get(codigo),
                    "situacao": "PROPOSTO",
                    "origem": "IA",
                }
            ).execute()
        except APIError as erro:
            if getattr(erro, "code", None) != _TERMO_REPETIDO:
                raise
            continue
        gravados += 1
    return gravados


def listar_propostas(supabase) -> list[dict[str, Any]]:
    """As propostas da IA com código, à espera da gestão, na ordem em que chegaram."""
    linhas = (
        supabase.table("cm_item_dicionario")
        .select("id, termo, codigo_conta, descricao_conta, criado_em")
        .eq("situacao", "PROPOSTO")
        .eq("origem", "IA")
        .order("criado_em")
        .execute()
        .data
        or []
    )
    return [linha for linha in linhas if linha.get("codigo_conta")]


def decidir_proposta(supabase, proposta_id: str, *, confirmar: bool, autor_id: str | None) -> dict[str, Any]:
    """Confirmar mantém o código; rejeitar tira o código e deixa o termo
    decidido, sem par, para a IA não ser perguntada de novo."""
    campos: dict[str, Any] = {"situacao": "CONFIRMADO", "autor_id": autor_id}
    if not confirmar:
        campos |= {"codigo_conta": None, "descricao_conta": None}
    # Condicional na situação: a proposta já decidida não muda de novo.
    decididas = (
        supabase.table("cm_item_dicionario")
        .update(campos)
        .eq("id", proposta_id)
        .eq("situacao", "PROPOSTO")
        .eq("origem", "IA")
        .execute()
        .data
        or []
    )
    if not decididas:
        raise PropostaRecusadaError("A proposta não existe ou já foi decidida.")
    return decididas[0]
