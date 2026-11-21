"""As configurações e os textos do Canal de Conduta, com versão (issue #1826,
especificação seção 15).

Cada item é uma lista de versões que só cresce: salvar grava a versão
seguinte, com autor e data, e a anterior fica. A vigente é a de maior número.
O banco (migration 186) recusa UPDATE, DELETE e TRUNCATE, então nenhum perfil
apaga uma versão.

Não existe o item "E-mail do DP" da especificação: o encaminhamento ao DP não
sai por e-mail, e a página só mostra o contato (decisão 4 do diretor no PRD
#1786). A lista de chaves é a mesma do CHECK da migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Item:
    chave: str
    rotulo: str
    grupo: str
    # Lido pelas telas públicas, sem login. Os outros são do lado do Comitê.
    publico: bool


ITENS: tuple[Item, ...] = (
    Item("contato_dp", "Contato do DP exibido", "Contatos", True),
    Item("orientacao_nsp", "Orientação do NSP", "Contatos", True),
    Item("aviso_p1_anonimato", "Aviso 1: relatar sem se identificar", "Avisos do passo 1", True),
    Item("aviso_p1_protocolo", "Aviso 2: guardar o protocolo e o código", "Avisos do passo 1", True),
    Item("aviso_p1_boa_fe", "Aviso 3: boa-fé e acusação falsa", "Avisos do passo 1", True),
    Item("protecao_abertura", "Frase de abertura", "Página de proteção", True),
    Item("protecao_quem_relata", "Para quem relata", "Página de proteção", True),
    Item("protecao_quem_e_citado", "Para quem é citado", "Página de proteção", True),
    Item("protecao_quem_le", "Quem lê e quem não lê", "Página de proteção", True),
    Item("protecao_direcao", "Se envolver a Direção ou a família", "Página de proteção", True),
    Item("protecao_prazos", "Prazos", "Página de proteção", True),
    Item("protecao_nao_garante", "O que o canal não garante", "Página de proteção", True),
    Item("consentimento_gravacao", "Texto de consentimento da gravação", "Comitê", False),
    Item("local_guarda_envelopes", "Local padrão de guarda dos envelopes", "Comitê", False),
)

POR_CHAVE = {item.chave: item for item in ITENS}

TABELA = "conduta_configuracoes"


def _todas_as_versoes(supabase, chaves: list[str]) -> dict[str, list[dict]]:
    """As versões de cada chave, da mais nova para a mais antiga."""
    linhas = supabase.table(TABELA).select("*").in_("chave", chaves).execute().data or []
    por_chave: dict[str, list[dict]] = {chave: [] for chave in chaves}
    for linha in linhas:
        por_chave[linha["chave"]].append(linha)
    for versoes in por_chave.values():
        versoes.sort(key=lambda linha: linha["versao"], reverse=True)
    return por_chave


def _nomes(supabase, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    linhas = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute().data
    return {linha["id"]: linha.get("nome_completo") or "" for linha in linhas or []}


def _versao(linha: dict, nomes: dict[str, str]) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "versao": linha["versao"],
        "texto": linha["texto"],
        "autor": nomes.get(linha["autor_id"], ""),
        "criado_em": linha["criado_em"],
    }


def itens_com_historico(supabase) -> list[dict[str, Any]]:
    """Todos os itens, na ordem da tela, cada um com as versões (a vigente
    primeiro). Item nunca salvo vem com a lista vazia."""
    por_chave = _todas_as_versoes(supabase, [item.chave for item in ITENS])
    nomes = _nomes(supabase, {linha["autor_id"] for versoes in por_chave.values() for linha in versoes})
    return [
        {
            "chave": item.chave,
            "rotulo": item.rotulo,
            "grupo": item.grupo,
            "publico": item.publico,
            "versoes": [_versao(linha, nomes) for linha in por_chave[item.chave]],
        }
        for item in ITENS
    ]


def vigentes_publicas(supabase) -> dict[str, dict[str, Any] | None]:
    """O que as telas públicas mostram: a versão vigente de cada item público,
    com o identificador dela, para a tela gravar qual versão a pessoa leu. Sem
    autor. Item nunca salvo vem como None."""
    publicos = [item.chave for item in ITENS if item.publico]
    por_chave = _todas_as_versoes(supabase, publicos)
    return {
        chave: (
            {"texto": versoes[0]["texto"], "versao": versoes[0]["versao"], "versao_id": versoes[0]["id"]}
            if versoes
            else None
        )
        for chave, versoes in por_chave.items()
    }


def salvar(supabase, chave: str, texto: str, autor_id: str) -> dict[str, Any]:
    """Grava a versão seguinte do item. A anterior não é tocada."""
    atuais = _todas_as_versoes(supabase, [chave])[chave]
    proxima = (atuais[0]["versao"] if atuais else 0) + 1
    (linha,) = (
        supabase.table(TABELA)
        .insert(
            {
                "chave": chave,
                "versao": proxima,
                "texto": texto,
                "autor_id": autor_id,
                "criado_em": datetime.now(UTC).isoformat(),
            }
        )
        .execute()
        .data
    )
    return _versao(linha, _nomes(supabase, {autor_id}))
