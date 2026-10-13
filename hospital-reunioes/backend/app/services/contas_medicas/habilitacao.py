"""A Habilitação de Contas médicas (issue #1139, PRD #1129, ADR 0070).

A diretoria liga e desliga o que cada perfil pode fazer (`cm_perfil_permissao`)
e dá ou tira o perfil de uma pessoa (`participantes.perfil_contas_medicas`).
Toda mudança grava `cm_registro` com autor, data, antes e depois.

Não há cache em lugar nenhum: o guard `require_permissao_cm` lê a matriz a
cada requisição, e é isso que faz a perda de uma permissão valer na hora.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.dependencies import PERFIS_CONTAS_MEDICAS, PERMISSOES_CONTAS_MEDICAS, selecionar_participantes

__all__ = [
    "PessoaNaoEncontradaError",
    "buscar_pessoas",
    "ler_matriz",
    "mudar_perfil",
    "mudar_permissao",
]

ENTIDADE_MATRIZ = "cm_perfil_permissao"
ENTIDADE_PERFIL = "participantes.perfil_contas_medicas"

# A busca devolve no máximo isto: é para achar uma pessoa, não para listar o hospital.
LIMITE_DA_BUSCA = 20

_CAMPOS_DA_PESSOA = "id, nome_completo, cargo, setor, ativo, perfil_contas_medicas"


class PessoaNaoEncontradaError(Exception):
    """O participante da rota não existe."""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _gravar_registro(
    supabase, autor_id: str | None, entidade: str, entidade_id: str, antes: dict, depois: dict
) -> None:
    supabase.table("cm_registro").insert(
        {
            "autor_id": autor_id,
            "data": _agora(),
            "entidade": entidade,
            "entidade_id": entidade_id,
            "antes_json": antes,
            "depois_json": depois,
        }
    ).execute()


def ler_matriz(supabase) -> dict[str, Any]:
    """Os perfis nas linhas e as permissões nas colunas, na ordem da spec.

    Par sem linha no banco sai desligado: é o que o guard faz com ele.
    """
    linhas = supabase.table("cm_perfil_permissao").select("perfil, permissao, ligada").execute().data or []
    ligadas = {(linha["perfil"], linha["permissao"]) for linha in linhas if linha.get("ligada")}
    return {
        "perfis": list(PERFIS_CONTAS_MEDICAS),
        "permissoes": list(PERMISSOES_CONTAS_MEDICAS),
        "matriz": {
            perfil: {permissao: (perfil, permissao) in ligadas for permissao in PERMISSOES_CONTAS_MEDICAS}
            for perfil in PERFIS_CONTAS_MEDICAS
        },
    }


def mudar_permissao(supabase, perfil: str, permissao: str, ligada: bool, autor_id: str | None) -> dict[str, Any]:
    """Liga ou desliga uma célula da matriz e registra o antes e o depois.

    Clicar no que já está como pedido não grava registro: nada mudou.
    """
    atual = (
        supabase.table("cm_perfil_permissao")
        .select("ligada")
        .eq("perfil", perfil)
        .eq("permissao", permissao)
        .execute()
        .data
        or []
    )
    antes = bool(atual and atual[0].get("ligada"))
    if antes != ligada:
        supabase.table("cm_perfil_permissao").upsert(
            {"perfil": perfil, "permissao": permissao, "ligada": ligada}, on_conflict="perfil,permissao"
        ).execute()
        _gravar_registro(
            supabase, autor_id, ENTIDADE_MATRIZ, f"{perfil}:{permissao}", {"ligada": antes}, {"ligada": ligada}
        )
    return {"perfil": perfil, "permissao": permissao, "ligada": ligada}


def _pessoa_publica(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "nome_completo": linha.get("nome_completo"),
        "cargo": linha.get("cargo"),
        "setor": linha.get("setor"),
        "perfil": linha.get("perfil_contas_medicas"),
    }


def buscar_pessoas(supabase, busca: str | None) -> list[dict[str, Any]]:
    """Sem busca, quem já tem perfil no módulo; com busca, as pessoas pelo nome.

    Quem foi desligado não aparece: o filtro é aqui, e não no banco, porque
    `ativo` aceita nulo e o `neq` do PostgREST descartaria as linhas antigas.
    """
    termo = re.sub(r"[%_*\\]", "", (busca or "").strip())
    if termo:
        resultado = selecionar_participantes(
            supabase,
            _CAMPOS_DA_PESSOA,
            lambda q: q.ilike("nome_completo", f"%{termo}%").order("nome_completo").limit(LIMITE_DA_BUSCA),
        )
    else:
        resultado = selecionar_participantes(
            supabase,
            _CAMPOS_DA_PESSOA,
            lambda q: q.in_("perfil_contas_medicas", list(PERFIS_CONTAS_MEDICAS)).order("nome_completo"),
        )
    return [_pessoa_publica(linha) for linha in (resultado.data or []) if linha.get("ativo") is not False]


def mudar_perfil(supabase, participante_id: str, perfil: str | None, autor_id: str | None) -> dict[str, Any]:
    """Dá, troca ou tira (`None`) o perfil de Contas médicas de uma pessoa."""
    atual = supabase.table("participantes").select(_CAMPOS_DA_PESSOA).eq("id", participante_id).execute().data or []
    if not atual:
        raise PessoaNaoEncontradaError(participante_id)
    antes = atual[0].get("perfil_contas_medicas")
    if antes != perfil:
        supabase.table("participantes").update({"perfil_contas_medicas": perfil}).eq("id", participante_id).execute()
        _gravar_registro(supabase, autor_id, ENTIDADE_PERFIL, participante_id, {"perfil": antes}, {"perfil": perfil})
    return _pessoa_publica({**atual[0], "perfil_contas_medicas": perfil})
