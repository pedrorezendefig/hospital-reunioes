"""Domínio do POP — escopo por perfil e Código travado (issue #82, ADR 0007).

Módulo único das regras do contexto POPs (PRD #76): guardas de escopo
(papel × Setor) e geração do Código `HSM_[SIGLA]-[NNN]`. As transições da
máquina de estados da Versão chegam nas fatias seguintes (#83+) e devem
viver aqui — endpoint algum manipula estado diretamente.
"""

from __future__ import annotations

# Perfis com escopo institucional: enxergam e criam em todos os Setores.
PERFIS_ESCOPO_TOTAL: tuple[str, ...] = ("superadmin", "gestor_qualidade")


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
