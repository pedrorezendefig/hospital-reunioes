"""Domínio do POP — escopo, Código travado e máquina de estados (ADR 0007).

Módulo único das regras do contexto POPs (PRD #76): guardas de escopo
(papel × Setor), geração do Código `HSM_[SIGLA]-[NNN]` e as transições da
máquina de estados da Versão como ações nomeadas — endpoint algum manipula
estado diretamente.
"""

from __future__ import annotations

from app.services import audit

# Perfis com escopo institucional: enxergam e criam em todos os Setores.
PERFIS_ESCOPO_TOTAL: tuple[str, ...] = ("superadmin", "gestor_qualidade")

# Estados em que a Versão está nas mãos do Elaborador (edição aberta).
ESTADOS_ELABORACAO: tuple[str, ...] = ("A_ELABORAR", "EM_ELABORACAO")


class AcessoNegadoError(Exception):
    """Papel errado para a ação (vira 403 no router)."""


class TransicaoInvalidaError(Exception):
    """Ação fora do estado válido da Versão (vira 400 no router)."""


def setores_do_escopo(me: dict, supabase) -> set[str] | None:
    """IDs dos Setores no escopo da pessoa. `None` = irrestrito (todos).

    Superadmin (POPs) e Gestor de Qualidade têm escopo institucional;
    Gerente e Coordenador enxergam os Setores dos seus vínculos N:N.
    """
    if me.get("perfil_pop") in PERFIS_ESCOPO_TOTAL:
        return None
    result = (
        supabase.table("pops_setores_participantes").select("setor_id").eq("participante_id", me.get("id")).execute()
    )
    return {row["setor_id"] for row in (result.data or [])}


def gerar_codigo(supabase, setor: dict) -> tuple[int, str]:
    """Próximo número da sequência do Setor e o Código `HSM_[SIGLA]-[NNN]`.

    A garantia final contra corrida é o UNIQUE (setor_id, numero) do banco;
    aqui calculamos o próximo da sequência lendo o maior número já usado.
    """
    result = supabase.table("pops").select("numero").eq("setor_id", setor["id"]).execute()
    numero = max((row.get("numero") or 0 for row in (result.data or [])), default=0) + 1
    return numero, f"HSM_{setor['sigla']}-{numero:03d}"


# ─── Elaboração (issue #83) — guardas e transições nomeadas ──────────────────


def exigir_elaborador(actor: dict, pop: dict) -> None:
    """Só o Elaborador designado elabora — a designação formal vence o escopo
    de Setor (foi escolhido na criação do POP). Demais papéis: 403."""
    if actor.get("id") != pop.get("elaborador_id"):
        raise AcessoNegadoError("A elaboração é exclusiva do Elaborador designado deste POP")


def exigir_estado_de_elaboracao(versao: dict) -> None:
    """A edição (chat, periodicidade) só acontece com a Versão nas mãos do
    Elaborador: A_ELABORAR ou EM_ELABORACAO."""
    if versao.get("estado") not in ESTADOS_ELABORACAO:
        raise TransicaoInvalidaError(
            f"A Versão está em {versao.get('estado')} — a elaboração já foi enviada ao fluxo de revisão"
        )


def iniciar_elaboracao_se_preciso(supabase, versao: dict, *, actor: dict, request=None) -> dict:
    """A_ELABORAR → EM_ELABORACAO na primeira interação real com o agente.

    Idempotente: já EM_ELABORACAO, não faz nada (sem re-auditar). Toda
    transição de estado é registrada com autor e timestamp (PRD #76).
    """
    if versao.get("estado") != "A_ELABORAR":
        return versao
    supabase.table("pops_versoes").update({"estado": "EM_ELABORACAO"}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_INICIAR_ELABORACAO",
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": "A_ELABORAR", "para": "EM_ELABORACAO"},
        request=request,
    )
    return {**versao, "estado": "EM_ELABORACAO"}


def aprovar_versao_final(supabase, versao: dict, *, actor: dict, request=None) -> dict:
    """EM_ELABORACAO → EM_REVISAO ("Aprovar versão final" do Elaborador).

    Exige conteúdo elaborado: o rascunho persistido na Versão não pode estar
    vazio (A_ELABORAR nunca passa — sem interação não há o que revisar).
    """
    if versao.get("estado") != "EM_ELABORACAO":
        raise TransicaoInvalidaError(
            f"Aprovar a versão final exige a Versão EM_ELABORACAO (estado atual: {versao.get('estado')})"
        )
    if not (versao.get("rascunho") or {}):
        raise TransicaoInvalidaError("Ainda não há conteúdo elaborado para enviar à Revisão")
    supabase.table("pops_versoes").update({"estado": "EM_REVISAO"}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_APROVAR_VERSAO_FINAL",
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": "EM_ELABORACAO", "para": "EM_REVISAO"},
        request=request,
    )
    return {**versao, "estado": "EM_REVISAO"}
