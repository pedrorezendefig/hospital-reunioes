"""Domínio do POP — escopo, Código travado e máquina de estados (ADR 0007).

Módulo único das regras do contexto POPs (PRD #76): guardas de escopo
(papel × Setor), geração do Código `HSM_[SIGLA]-[NNN]` e as transições da
máquina de estados da Versão como ações nomeadas — endpoint algum manipula
estado diretamente.
"""

from __future__ import annotations

from datetime import UTC, datetime

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


# ─── Revisão e Validação (issue #85) — guardas e transições nomeadas ─────────


def exigir_leitor_da_versao(actor: dict, pop: dict, supabase) -> None:
    """Leitura da Versão completa: designados do POP (a designação formal
    vence o escopo) ou quem tem o Setor no escopo do perfil. Demais: 403."""
    if actor.get("id") in (pop.get("elaborador_id"), pop.get("revisor_id"), pop.get("validador_id")):
        return
    escopo = setores_do_escopo(actor, supabase)
    if escopo is not None and pop.get("setor_id") not in escopo:
        raise AcessoNegadoError("Este POP está fora do seu escopo de Setores")


def exigir_revisor(actor: dict, pop: dict) -> None:
    """Só o Revisor designado age na Revisão (etapa) — a designação formal
    vence o escopo de Setor, como na elaboração. Demais papéis: 403."""
    if actor.get("id") != pop.get("revisor_id"):
        raise AcessoNegadoError("A Revisão é exclusiva do Revisor designado deste POP")


def aprovar_revisao(supabase, versao: dict, *, actor: dict, request=None) -> dict:
    """EM_REVISAO → EM_VALIDACAO (aprovação do Revisor)."""
    if versao.get("estado") != "EM_REVISAO":
        raise TransicaoInvalidaError(
            f"Aprovar a Revisão exige a Versão EM_REVISAO (estado atual: {versao.get('estado')})"
        )
    supabase.table("pops_versoes").update({"estado": "EM_VALIDACAO"}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_APROVAR_REVISAO",
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": "EM_REVISAO", "para": "EM_VALIDACAO"},
        request=request,
    )
    return {**versao, "estado": "EM_VALIDACAO"}


def exigir_validador(actor: dict, pop: dict) -> None:
    """Só o Validador designado age na Validação — a designação formal vence
    o escopo de Setor, como na elaboração. Demais papéis: 403."""
    if actor.get("id") != pop.get("validador_id"):
        raise AcessoNegadoError("A Validação é exclusiva do Validador designado deste POP")


def aprovar_validacao(supabase, versao: dict, *, actor: dict, request=None) -> dict:
    """EM_VALIDACAO → EM_ASSINATURA (aprovação final do Validador). O disparo
    ClickSign chega na fatia de publicação (PRD #76)."""
    if versao.get("estado") != "EM_VALIDACAO":
        raise TransicaoInvalidaError(
            f"Aprovar a Validação exige a Versão EM_VALIDACAO (estado atual: {versao.get('estado')})"
        )
    supabase.table("pops_versoes").update({"estado": "EM_ASSINATURA"}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_APROVAR_VALIDACAO",
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": "EM_VALIDACAO", "para": "EM_ASSINATURA"},
        request=request,
    )
    return {**versao, "estado": "EM_ASSINATURA"}


def _devolver(supabase, versao: dict, *, actor: dict, comentarios: str, etapa: str, action: str, request) -> dict:
    """Núcleo da Devolução (Revisor ou Validador): grava os comentários com
    autor, timestamp e a etapa de retorno — no reenvio, a Versão volta direto
    a quem devolveu (PRD #76) — e move a Versão a EM_ELABORACAO, auditando."""
    if versao.get("estado") != etapa:
        raise TransicaoInvalidaError(f"Esta Devolução exige a Versão {etapa} (estado atual: {versao.get('estado')})")
    supabase.table("pops_devolucoes").insert(
        {
            "versao_id": versao["id"],
            "autor_id": actor.get("id"),
            "etapa_retorno": etapa,
            "comentarios": comentarios,
            # Timestamp explícito da aplicação: a ordem das Devoluções decide
            # o destino do reenvio — determinístico também fora do banco.
            "created_at": datetime.now(UTC).isoformat(),
        }
    ).execute()
    supabase.table("pops_versoes").update({"estado": "EM_ELABORACAO"}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action=action,
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": etapa, "para": "EM_ELABORACAO"},
        request=request,
    )
    return {**versao, "estado": "EM_ELABORACAO"}


def devolver_revisao(supabase, versao: dict, *, actor: dict, comentarios: str, request=None) -> dict:
    """EM_REVISAO → EM_ELABORACAO (Devolução do Revisor): comentários com
    autor e timestamp, visíveis na elaboração e no contexto do agente."""
    return _devolver(
        supabase,
        versao,
        actor=actor,
        comentarios=comentarios,
        etapa="EM_REVISAO",
        action="POPS_DEVOLVER_REVISAO",
        request=request,
    )


def devolver_validacao(supabase, versao: dict, *, actor: dict, comentarios: str, request=None) -> dict:
    """EM_VALIDACAO → EM_ELABORACAO (Devolução do Validador): a etapa de
    retorno gravada é EM_VALIDACAO — o reenvio volta direto ao Validador,
    sem repassar pelo Revisor (decisão do grilling, PRD #76)."""
    return _devolver(
        supabase,
        versao,
        actor=actor,
        comentarios=comentarios,
        etapa="EM_VALIDACAO",
        action="POPS_DEVOLVER_VALIDACAO",
        request=request,
    )


def listar_devolucoes(supabase, versao: dict) -> list[dict]:
    """Devoluções da Versão, da mais recente à mais antiga (a primeira decide
    o destino do reenvio). Comentários com autor e timestamp (PRD #76)."""
    result = (
        supabase.table("pops_devolucoes")
        .select("*")
        .eq("versao_id", versao["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def aprovar_versao_final(supabase, versao: dict, *, actor: dict, request=None) -> dict:
    """EM_ELABORACAO → EM_REVISAO ("Aprovar versão final" do Elaborador) — ou
    direto a EM_VALIDACAO quando a última Devolução veio do Validador: a
    Versão volta a quem devolveu, sem repassar pelo Revisor (PRD #76).

    Exige conteúdo elaborado: o rascunho persistido na Versão não pode estar
    vazio (A_ELABORAR nunca passa — sem interação não há o que revisar).
    """
    if versao.get("estado") != "EM_ELABORACAO":
        raise TransicaoInvalidaError(
            f"Aprovar a versão final exige a Versão EM_ELABORACAO (estado atual: {versao.get('estado')})"
        )
    rascunho = versao.get("rascunho") or {}
    # Dict com todas as seções em branco também é "sem conteúdo" — o agente
    # pode devolver o esqueleto vazio num primeiro turno improdutivo.
    if not any(v.strip() for v in rascunho.values() if isinstance(v, str)):
        raise TransicaoInvalidaError("Ainda não há conteúdo elaborado para enviar à Revisão")
    devolucoes = listar_devolucoes(supabase, versao)
    destino = devolucoes[0]["etapa_retorno"] if devolucoes else "EM_REVISAO"
    supabase.table("pops_versoes").update({"estado": destino}).eq("id", versao["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_APROVAR_VERSAO_FINAL",
        target_type="pop_versao",
        target_id=versao["id"],
        metadata={"pop_id": versao.get("pop_id"), "de": "EM_ELABORACAO", "para": destino},
        request=request,
    )
    return {**versao, "estado": destino}


# ─── Documento oficial em PDF (issue #86) — guardas de leitura ────────────────

# O documento preliminar existe da Revisão em diante; o assinado substitui o
# download na fatia de publicação (PRD #76).
ESTADOS_COM_DOCUMENTO: tuple[str, ...] = ("EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO")


def exigir_leitura_do_pop(actor: dict, pop: dict, supabase) -> None:
    """Leitura do POP: designado (Elaborador/Revisor/Validador — a designação
    formal vence o escopo de Setor) OU Setor dentro do escopo do perfil."""
    if actor.get("id") in (pop.get("elaborador_id"), pop.get("revisor_id"), pop.get("validador_id")):
        return
    escopo = setores_do_escopo(actor, supabase)
    if escopo is None or pop.get("setor_id") in escopo:
        return
    raise AcessoNegadoError("POP fora do escopo dos seus Setores")


def exigir_documento_disponivel(versao: dict) -> None:
    """O documento institucional só existe com a elaboração concluída — em
    A_ELABORAR/EM_ELABORACAO o rascunho ainda está nas mãos do Elaborador."""
    if versao.get("estado") not in ESTADOS_COM_DOCUMENTO:
        raise TransicaoInvalidaError(
            f"O documento do POP existe da Revisão em diante — a Versão está em {versao.get('estado')}"
        )
