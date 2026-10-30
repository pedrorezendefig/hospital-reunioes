"""A Fila de contas de Contas médicas (issue #1307, ADR 0073).

A Fila é comum: toda conta com Guia pronto (`A_FAZER`) é livre, qualquer que
seja o `faturista_id`, e ganha dono quando uma faturista abre o Guia dela
(puxar a conta). Quem envia não vira dono: quem enviou fica em
`cm_envio.usuario_id`, e é quem acompanha a conta até ela ficar pronta.
"""

from __future__ import annotations

from app.dependencies import selecionar_participantes

# A conta com Guia pronto que ninguém puxou.
LIVRE = "A_FAZER"
# A que a faturista puxou e está trabalhando: a única que volta para a Fila.
EM_CORRECAO = "EM_CORRECAO"
SO_EM_CORRECAO_VOLTA = "Só a conta Em correção volta para a Fila"
# As que a faturista puxou e ainda não concluiu.
COM_A_FATURISTA = (EM_CORRECAO, "RETORNO")
# As que ainda não ficaram prontas: ficam com quem enviou, que tem o PDF.
NAO_PRONTAS = ("AGUARDANDO_ARQUIVO", "NA_FILA", "PROCESSANDO", "ERRO")
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")
# A aba Concluídas mostra as mais recentes; o resto fica no banco para o Painel.
TETO_DE_CONCLUIDAS = 100


def _contas(supabase, me: dict, situacoes, *, da_pessoa: bool, recentes_primeiro: bool = False) -> list[dict]:
    consulta = supabase.table("cm_conta").select("*").in_("situacao", list(situacoes))
    if da_pessoa and not ve_todas(me):
        consulta = consulta.eq("faturista_id", me.get("id"))
    consulta = consulta.order("ordem_fila", desc=recentes_primeiro)
    if recentes_primeiro:
        consulta = consulta.limit(TETO_DE_CONCLUIDAS)
    return consulta.execute().data or []


def ve_todas(me: dict) -> bool:
    """Quem tem "painel completo" vê as listas de todas as pessoas."""
    return "painel_completo" in me["permissoes_cm"]


def fila_da_pessoa(supabase, me: dict) -> dict:
    """As listas de quem analisa, em ordem de envio (nunca por valor): a Fila
    (as livres, a mesma para todas), "Minhas" (as que a pessoa puxou e não
    concluiu) e as Concluídas dela, as mais recentes primeiro.

    Quem tem "painel completo" vê todas, e cada conta vem com `com_quem`: o nome
    da faturista que está com ela."""
    todas = ve_todas(me)
    livres = _contas(supabase, me, (LIVRE,), da_pessoa=False)
    minhas = _contas(supabase, me, COM_A_FATURISTA, da_pessoa=True)
    concluidas = _contas(supabase, me, CONCLUIDAS, da_pessoa=True, recentes_primeiro=True)

    for conta in livres:
        conta["com_quem"] = None
    for conta in minhas + concluidas:
        conta["com_quem"] = conta.get("faturista_id") if todas else None
    if todas:
        _trocar_id_por_nome(supabase, minhas + concluidas)
    return {"todas": todas, "fila": livres, "minhas": minhas, "concluidas": concluidas}


def envios_da_pessoa(supabase, me: dict) -> dict:
    """ "Meus envios": as contas que a pessoa enviou e ainda não ficaram prontas,
    em ordem de envio. Quem tem "painel completo" vê as de todos, cada uma com
    o nome de quem enviou em `com_quem`."""
    todas = ve_todas(me)
    nao_prontas = _contas(supabase, me, NAO_PRONTAS, da_pessoa=False)
    enviou = _quem_enviou(supabase, nao_prontas)
    envios = nao_prontas if todas else [c for c in nao_prontas if enviou.get(c["id"]) == me.get("id")]
    for conta in envios:
        conta["com_quem"] = enviou.get(conta["id"]) if todas else None
    if todas:
        _trocar_id_por_nome(supabase, envios)
    return {"todas": todas, "meus_envios": envios}


def _por_id(supabase, tabela: str, coluna: str, valores, **filtros) -> list[dict]:
    valores = list(dict.fromkeys(v for v in valores if v))
    if not valores:
        return []
    consulta = supabase.table(tabela).select("*").in_(coluna, valores)
    for campo, valor in filtros.items():
        consulta = consulta.eq(campo, valor)
    return consulta.execute().data or []


def _quem_enviou(supabase, contas: list[dict]) -> dict[str, str]:
    """O `cm_envio.usuario_id` de cada conta, pelo arquivo dela. A conta à
    espera da Conta ainda não tem arquivo: quem enviou é quem mandou o
    Prontuário do atendimento."""
    da_conta = {a["id"]: a for a in _por_id(supabase, "cm_arquivo", "id", (c.get("arquivo_id") for c in contas))}
    prontuarios = _por_id(
        supabase,
        "cm_arquivo",
        "atendimento_id",
        (c.get("atendimento_id") for c in contas if not c.get("arquivo_id")),
        tipo="PRONTUARIO",
    )
    do_atendimento = {a["atendimento_id"]: a for a in prontuarios}
    arquivo_de = {
        c["id"]: da_conta.get(c["arquivo_id"]) if c.get("arquivo_id") else do_atendimento.get(c.get("atendimento_id"))
        for c in contas
    }
    envios = _por_id(supabase, "cm_envio", "id", (a["envio_id"] for a in arquivo_de.values() if a))
    usuario_do_envio = {e["id"]: e.get("usuario_id") for e in envios}
    return {cid: usuario_do_envio.get(a["envio_id"]) for cid, a in arquivo_de.items() if a}


def _trocar_id_por_nome(supabase, contas: list[dict]) -> None:
    ids = list({c["com_quem"] for c in contas if c.get("com_quem")})
    nomes = {}
    if ids:
        pessoas = selecionar_participantes(supabase, "id, nome_completo", lambda q: q.in_("id", ids)).data or []
        nomes = {p["id"]: p.get("nome_completo") for p in pessoas}
    for conta in contas:
        conta["com_quem"] = nomes.get(conta.get("com_quem"))


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


def devolver(supabase, conta_id: str, dona_lida: str) -> bool:
    """A conta Em correção volta livre para a Fila (issue #1309). Só a dona e
    a situação mudam: `ordem_fila`, `aberta_em` e as marcações ficam. O UPDATE
    é condicional na situação e na dona lida: a conta concluída ou passada a
    outra faturista entre a leitura e a escrita não volta (issue #1328)."""
    gravadas = (
        supabase.table("cm_conta")
        .update({"situacao": LIVRE, "faturista_id": None})
        .eq("id", conta_id)
        .eq("situacao", EM_CORRECAO)
        .eq("faturista_id", dona_lida)
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
