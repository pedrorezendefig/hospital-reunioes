"""Edição determinística da lista de participantes da Ata (ADR 0023).

A lista exibida na Ata vive em `json_ata.participantes` (proposta pela IA só na
extração inicial e governada pelo Facilitador a partir daí). O roster oficial
`reuniao_participantes` dirige ClickSign e Pendências. Toda edição manual espelha
nos dois lados, mantendo tela, PDF e ClickSign consistentes.

Módulo puro nos dados (não persiste; não muta as listas recebidas), com uma única
porta que lê o roster para resolver um nome canônico ao seu vínculo. As primitivas
de "editar `json_ata.participantes`" são reaproveitadas pela resolução ("ignorar"
um não reconhecido também some da lista exibida, fatia #203).
"""

from __future__ import annotations

from app.services.participant_matcher import _normalize


def remover_da_lista(participantes: list[dict] | None, nome: str) -> tuple[list[dict], bool]:
    """Remove de `participantes` toda entrada cujo `nome` casa (normalizado).

    Devolve `(nova_lista, removeu)` sem mutar a entrada. `removeu` é False quando
    nenhum nome bateu. Primitiva reaproveitável pela resolução (remoção por nome
    canônico).
    """
    alvo = _normalize(nome or "")
    atual = list(participantes or [])
    nova = [p for p in atual if _normalize(p.get("nome") or "") != alvo]
    return nova, len(nova) != len(atual)


def adicionar_na_lista(
    participantes: list[dict] | None,
    nome: str,
    cargo: str | None = None,
    setor: str | None = None,
) -> tuple[list[dict], bool]:
    """Acrescenta `{nome, cargo, setor, presente: True}` à lista, idempotente por
    nome (normalizado).

    Devolve `(nova_lista, adicionou)` sem mutar a entrada. `adicionou` é False
    quando o nome já constava.
    """
    atual = list(participantes or [])
    alvo = _normalize(nome or "")
    if any(_normalize(p.get("nome") or "") == alvo for p in atual):
        return atual, False
    entrada = {"nome": nome, "cargo": cargo or "", "setor": setor, "presente": True}
    return [*atual, entrada], True


def eh_responsavel_no_quadro(quadro: list[dict] | None, participante_id: str | None) -> bool:
    """True se `participante_id` é `responsavel_id` de alguma ação do Quadro.

    Guarda o invariante do ADR 0008 (responsável escolhível ⊆ roster): excluir do
    roster quem responde por uma ação é bloqueado.
    """
    if not participante_id:
        return False
    return any((acao or {}).get("responsavel_id") == participante_id for acao in (quadro or []))


def id_no_roster_por_nome(supabase, id_reuniao: str, nome: str) -> str | None:
    """Resolve um nome canônico ao `participante_id` vinculado à Reunião (roster).

    Devolve None quando o nome não corresponde a nenhum vínculo (ex.: nome que a
    IA listou mas nunca virou roster). Usa duas leituras simples (sem join) para o
    espelho da exclusão e para a checagem do responsável.
    """
    vinculos = supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute()
    ids = [v["participante_id"] for v in (vinculos.data or [])]
    if not ids:
        return None
    rows = supabase.table("participantes").select("id, nome_completo").in_("id", ids).execute()
    alvo = _normalize(nome or "")
    for row in rows.data or []:
        if _normalize(row.get("nome_completo") or "") == alvo:
            return row["id"]
    return None
