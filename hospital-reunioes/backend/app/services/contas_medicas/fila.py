"""A Fila de contas de Contas médicas (issue #1307, ADR 0073).

A Fila é comum: toda conta com Guia pronto (`A_FAZER`) é livre, qualquer que
seja o `faturista_id`, e ganha dono quando uma faturista abre o Guia dela
(puxar a conta). Quem envia não vira dono: quem enviou fica em
`cm_envio.usuario_id`, e é quem acompanha a conta até ela ficar pronta.
"""

from __future__ import annotations

# A conta com Guia pronto que ninguém puxou.
LIVRE = "A_FAZER"


def puxar(supabase, conta_id: str, pessoa_id: str, agora: str) -> bool:
    """A conta livre passa a ser de quem abriu. O UPDATE é condicional na
    situação: de duas aberturas ao mesmo tempo, só uma grava, e a outra recebe
    `False`."""
    gravadas = (
        supabase.table("cm_conta")
        .update({"situacao": "EM_CORRECAO", "aberta_em": agora, "faturista_id": pessoa_id})
        .eq("id", conta_id)
        .eq("situacao", LIVRE)
        .execute()
        .data
        or []
    )
    return bool(gravadas)


def primeira_livre(supabase) -> str | None:
    """A primeira conta livre na ordem de envio, de quem quer que tenha enviado."""
    livres = (
        supabase.table("cm_conta").select("id").eq("situacao", LIVRE).order("ordem_fila").limit(1).execute().data or []
    )
    return livres[0]["id"] if livres else None
