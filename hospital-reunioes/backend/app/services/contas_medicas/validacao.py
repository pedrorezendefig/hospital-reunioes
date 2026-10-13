"""A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).

A diretoria e a gestão decidem por tema, não por conta. Um tema
(`cm_validacao_tema`) junta, em `cm_validacao_tema_linha`, as linhas do Guia
ou as observações do time que esperam a mesma decisão:

- REGRA_PENDENTE: as linhas Validar, um tema por regra e operadora. Nasce no
  ponto único de gravação das linhas do Guia (`processamento._gravar_guia`),
  pela ação, sem olhar a origem: as linhas do código e as da IA passam ali;
- BLOQUEADO: as linhas que a faturista marcou Bloqueado, um tema por código;
- OBSERVACAO: as linhas Não procede e as observações da conclusão, um tema
  por regra citada (e um por operadora para a observação que não cita regra);
- DICIONARIO: o termo que a IA propôs ao dicionário, um tema por termo.

Só tema ABERTO aceita linha nova: depois da decisão, a próxima linha da mesma
regra abre outro tema.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas.memoria_edicao import mudar_regra
from app.services.paginacao import ler_tudo

__all__ = [
    "DecisaoRecusadaError",
    "TemaNaoEncontradoError",
    "acao_decidida",
    "decidir_tema",
    "fila_de_validacao",
    "temas_das_linhas_validar",
]

REGRA_PENDENTE = "REGRA_PENDENTE"
BLOQUEADO = "BLOQUEADO"
OBSERVACAO = "OBSERVACAO"
DICIONARIO = "DICIONARIO"

ABERTO = "ABERTO"
DECIDIDO = "DECIDIDO"

LOTE_DE_IDS = 100
CENTAVO = Decimal("0.01")

# As duas vagas do processamento gravam o Guia ao mesmo tempo: sem trava, as
# duas contas da mesma regra abririam dois temas.
_trava_dos_temas = threading.Lock()


def _em_lotes(supabase, tabela: str, coluna: str, ids: Iterable[str], rotulo: str) -> list[dict]:
    ids = [i for i in dict.fromkeys(ids) if i]
    linhas: list[dict] = []
    for i in range(0, len(ids), LOTE_DE_IDS):
        lote = ids[i : i + LOTE_DE_IDS]
        linhas += ler_tudo(
            lambda lote=lote: supabase.table(tabela).select("*").in_(coluna, lote).order("id"), rotulo=rotulo
        )
    return linhas


def _igual_ou_nulo(consulta, coluna: str, valor):
    return consulta.eq(coluna, valor) if valor is not None else consulta.is_(coluna, "null")


def _tema_aberto(
    supabase,
    tipo: str,
    titulo: str,
    *,
    operadora_id: str | None = None,
    regra_codigo: str | None = None,
    codigo_item: str | None = None,
) -> dict:
    """O tema aberto da chave, ou um novo. Quem chama segura a trava."""
    consulta = supabase.table("cm_validacao_tema").select("*").eq("tipo", tipo).eq("estado", ABERTO)
    consulta = _igual_ou_nulo(consulta, "operadora_id", operadora_id)
    consulta = _igual_ou_nulo(consulta, "regra_codigo", regra_codigo)
    consulta = _igual_ou_nulo(consulta, "codigo_item", codigo_item)
    achados = consulta.limit(1).execute().data or []
    if achados:
        return achados[0]
    return (
        supabase.table("cm_validacao_tema")
        .insert(
            {
                "tipo": tipo,
                "titulo": titulo,
                "operadora_id": operadora_id,
                "regra_codigo": regra_codigo,
                "codigo_item": codigo_item,
            }
        )
        .execute()
        .data[0]
    )


def _operadora_da_conta(supabase, conta_id: str) -> str | None:
    contas = supabase.table("cm_conta").select("atendimento_id").eq("id", conta_id).limit(1).execute().data or []
    if not contas:
        return None
    atendimentos = (
        supabase.table("cm_atendimento").select("operadora_id").eq("id", contas[0]["atendimento_id"]).limit(1)
    ).execute().data or []
    return atendimentos[0].get("operadora_id") if atendimentos else None


def temas_das_linhas_validar(supabase, conta_id: str, linhas: list[dict]) -> None:
    """Cada linha Validar gravada entra no tema aberto da regra e da operadora
    dela. A linha sem regra citada não tem o que decidir e fica de fora."""
    por_regra: dict[str, list[dict]] = {}
    for linha in linhas:
        if linha.get("acao") == "VALIDAR" and linha.get("regra_codigo"):
            por_regra.setdefault(linha["regra_codigo"], []).append(linha)
    if not por_regra:
        return
    operadora_id = _operadora_da_conta(supabase, conta_id)
    with _trava_dos_temas:
        for regra, da_regra in por_regra.items():
            tema = _tema_aberto(
                supabase, REGRA_PENDENTE, f"Regra {regra}", operadora_id=operadora_id, regra_codigo=regra
            )
            supabase.table("cm_validacao_tema_linha").insert(
                [{"tema_id": tema["id"], "guia_linha_id": linha["id"]} for linha in da_regra]
            ).execute()


# ----------------------------------------------------------------------------------
# A fila
# ----------------------------------------------------------------------------------


def _dinheiro(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _regras_vigentes(supabase, operadora_ids: Iterable[str]) -> dict[tuple[str, str], dict]:
    """As regras da memória vigente de cada operadora, por (operadora, código)."""
    versoes = _em_lotes(supabase, "cm_memoria_versao", "operadora_id", operadora_ids, "memórias da Validação")
    vigentes = {v["id"]: v["operadora_id"] for v in versoes if v.get("vigente")}
    regras = _em_lotes(supabase, "cm_regra", "memoria_versao_id", vigentes, "regras da Validação")
    return {
        (vigentes[r["memoria_versao_id"]], r["codigo"]): r
        for r in regras
        if r.get("ativa", True) and r["memoria_versao_id"] in vigentes
    }


def fila_de_validacao(supabase) -> dict[str, Any]:
    """Os temas abertos como a tela mostra, do maior R$ em jogo para o menor,
    e os três números do topo: aguardando decisão, contas afetadas e R$ em jogo."""
    temas = supabase.table("cm_validacao_tema").select("*").eq("estado", ABERTO).order("criado_em").execute().data or []
    ligacoes = _em_lotes(supabase, "cm_validacao_tema_linha", "tema_id", [t["id"] for t in temas], "ligações")
    linhas = {
        linha["id"]: linha
        for linha in _em_lotes(
            supabase, "cm_guia_linha", "id", [li.get("guia_linha_id") for li in ligacoes], "linhas da Validação"
        )
    }
    observacoes = {
        o["id"]: o
        for o in _em_lotes(
            supabase, "cm_observacao", "id", [li.get("observacao_id") for li in ligacoes], "observações da Validação"
        )
    }
    contas = {
        c["id"]: c
        for c in _em_lotes(
            supabase,
            "cm_conta",
            "id",
            [x["conta_id"] for x in [*linhas.values(), *observacoes.values()]],
            "contas da Validação",
        )
    }
    atendimentos = {
        a["id"]: a
        for a in _em_lotes(
            supabase, "cm_atendimento", "id", [c["atendimento_id"] for c in contas.values()], "atendimentos"
        )
    }
    operadora_da_conta = {
        c["id"]: (atendimentos.get(c["atendimento_id"]) or {}).get("operadora_id") for c in contas.values()
    }
    operadora_ids = {t["operadora_id"] for t in temas if t.get("operadora_id")} | {
        o for o in operadora_da_conta.values() if o
    }
    siglas = {o["id"]: o["sigla"] for o in _em_lotes(supabase, "cm_operadora", "id", operadora_ids, "operadoras")}
    regras = _regras_vigentes(supabase, operadora_ids)

    do_tema: dict[str, list[dict]] = {}
    for ligacao in ligacoes:
        do_tema.setdefault(ligacao["tema_id"], []).append(ligacao)

    cartoes = []
    todas_as_contas: set[str] = set()
    for tema in temas:
        das_linhas = [
            linhas[li["guia_linha_id"]] for li in do_tema.get(tema["id"], []) if li.get("guia_linha_id") in linhas
        ]
        das_observacoes = [
            observacoes[li["observacao_id"]]
            for li in do_tema.get(tema["id"], [])
            if li.get("observacao_id") in observacoes
        ]
        conta_ids = {x["conta_id"] for x in [*das_linhas, *das_observacoes]}
        if not conta_ids and tema["tipo"] != DICIONARIO:
            continue
        todas_as_contas |= conta_ids
        valor = sum((abs(_dinheiro(linha.get("valor_diferenca"))) for linha in das_linhas), Decimal("0.00"))
        if tema.get("operadora_id"):
            operadora = siglas.get(tema["operadora_id"])
        else:
            operadora = ", ".join(sorted({siglas[o] for c in conta_ids if (o := operadora_da_conta.get(c)) in siglas}))
        regra = regras.get((tema.get("operadora_id"), tema.get("regra_codigo")))
        cartoes.append(
            {
                "id": tema["id"],
                "tipo": tema["tipo"],
                "titulo": tema["titulo"],
                "operadora": operadora or None,
                "regra_codigo": tema.get("regra_codigo"),
                "regra": ({k: regra.get(k) for k in ("texto", "tipo", "origem", "status")} if regra else None),
                "codigo_item": tema.get("codigo_item"),
                "contas": len(conta_ids),
                "desde": tema.get("criado_em"),
                "valor": float(valor),
                "leitura_ia": tema.get("leitura_ia"),
            }
        )
    cartoes.sort(key=lambda c: (-c["valor"], c["desde"] or ""))
    return {
        "numeros": {
            "aguardando_decisao": len(cartoes),
            "contas_afetadas": len(todas_as_contas),
            "valor_em_jogo": float(sum((_dinheiro(c["valor"]) for c in cartoes), Decimal("0.00"))),
        },
        "temas": cartoes,
    }


# ----------------------------------------------------------------------------------
# As decisões
# ----------------------------------------------------------------------------------

VALIDAR_REGRA = "VALIDAR_REGRA"
DEIXAR_PENDENTE = "DEIXAR_PENDENTE"
ENVIAR_AO_CADASTRO = "ENVIAR_AO_CADASTRO"
DESCARTAR = "DESCARTAR"
MANTER_REGRA = "MANTER_REGRA"
EDITAR_REGRA = "EDITAR_REGRA"
RESPONDER = "RESPONDER"
CONFIRMAR = "CONFIRMAR"
REJEITAR = "REJEITAR"

# O que cada tipo de tema aceita. "Enviar ao cadastro" tem rota própria, que
# devolve o CSV.
DECISOES = {
    REGRA_PENDENTE: (VALIDAR_REGRA, DEIXAR_PENDENTE),
    BLOQUEADO: (ENVIAR_AO_CADASTRO, DESCARTAR),
    OBSERVACAO: (MANTER_REGRA, EDITAR_REGRA, RESPONDER),
    DICIONARIO: (CONFIRMAR, REJEITAR),
}

CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")


class TemaNaoEncontradoError(LookupError):
    """O tema não existe."""


class DecisaoRecusadaError(ValueError):
    """A decisão não cabe no tema como ele está; a mensagem é para quem decide."""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def acao_decidida(linha: dict) -> str | None:
    """A ação que a linha Validar vira quando a regra é validada, pelo que a
    própria linha diz: quantidade devida contra a lançada, ou preço de tabela
    contra o lançado. Sem diferença para corrigir, `None`: a linha é descartada."""
    lancada, devida = linha.get("quantidade_lancada"), linha.get("quantidade_devida")
    if lancada is not None and devida is not None and lancada != devida:
        if not lancada:
            return "INCLUIR"
        if not devida:
            return "RETIRAR"
        return "AJUSTAR_QUANTIDADE"
    preco_lancado, preco_tabela = linha.get("preco_lancado"), linha.get("preco_tabela")
    if preco_lancado is not None and preco_tabela is not None and preco_lancado != preco_tabela:
        return "CORRIGIR_PRECO"
    return None


def _tema(supabase, tema_id: str) -> dict:
    temas = supabase.table("cm_validacao_tema").select("*").eq("id", tema_id).limit(1).execute().data or []
    if not temas:
        raise TemaNaoEncontradoError("Tema não encontrado")
    return temas[0]


def _ligacoes(supabase, tema_id: str) -> list[dict]:
    return supabase.table("cm_validacao_tema_linha").select("*").eq("tema_id", tema_id).execute().data or []


def _linhas_do_tema(supabase, tema_id: str) -> list[dict]:
    ids = [li.get("guia_linha_id") for li in _ligacoes(supabase, tema_id)]
    return _em_lotes(supabase, "cm_guia_linha", "id", ids, "linhas do tema")


def _regra_vigente(supabase, operadora_id: str | None, codigo: str | None) -> tuple[str, dict]:
    """A sigla da operadora e a regra na memória vigente dela."""
    operadoras = supabase.table("cm_operadora").select("id, sigla").eq("id", operadora_id).execute().data or []
    regra = _regras_vigentes(supabase, [operadora_id]).get((operadora_id, codigo)) if operadora_id else None
    if not operadoras or regra is None:
        raise TemaNaoEncontradoError(f"A regra {codigo} não está na memória vigente da operadora.")
    return operadoras[0]["sigla"], regra


def _mudar_a_regra(supabase, tema: dict, corpo: dict, me: dict, *, validar: bool) -> None:
    """A edição da memória (versão nova) com o texto do corpo, ou o atual. A
    regra pendente é decidida; a vigente só muda se o texto mudou."""
    sigla, regra = _regra_vigente(supabase, tema.get("operadora_id"), tema.get("regra_codigo"))
    texto = (corpo.get("texto") or "").strip() or regra["texto"]
    pendente = regra.get("status") != "VIGENTE"
    if validar and not pendente and texto == regra["texto"]:
        return
    mudar_regra(
        supabase,
        sigla,
        regra["codigo"],
        texto=texto,
        tipo=corpo.get("tipo") or regra.get("tipo"),
        origem=corpo.get("origem") if corpo.get("origem") is not None else regra.get("origem"),
        decidir=validar and pendente,
        autor_id=me.get("id"),
        permissoes=me.get("permissoes_cm") or [],
    )


def _decidir_as_linhas(supabase, tema: dict, autor_id: str | None) -> None:
    """As linhas Validar do tema viram Decidida, com a ação resultante ou sem
    ação (descarte). A conta já concluída com linha a lançar volta para a
    faturista em Retorno."""
    agora = _agora()
    a_lancar: set[str] = set()
    pendente = f"Regra {tema.get('regra_codigo')} pendente. "
    for linha in _linhas_do_tema(supabase, tema["id"]):
        if linha.get("acao") != "VALIDAR" or linha.get("estado") not in ("ABERTA", "EM_VALIDACAO"):
            continue
        campos: dict[str, Any] = {"estado": "DECIDIDA", "marcado_por": autor_id, "marcado_em": agora}
        acao = acao_decidida(linha)
        if acao:
            campos["acao"] = acao
            a_lancar.add(linha["conta_id"])
        motivo = linha.get("motivo") or ""
        if motivo.startswith(pendente):
            campos["motivo"] = f"Regra {tema['regra_codigo']} validada. " + motivo[len(pendente) :]
        supabase.table("cm_guia_linha").update(campos).eq("id", linha["id"]).eq("acao", "VALIDAR").execute()
    if a_lancar:
        supabase.table("cm_conta").update({"situacao": "RETORNO"}).in_("id", sorted(a_lancar)).in_(
            "situacao", list(CONCLUIDAS)
        ).execute()


def linhas_do_retorno(supabase, linhas: list[dict]) -> list[dict]:
    """As linhas da conta em Retorno que voltaram para a faturista: as que a
    Validação decidiu ao validar a regra. As outras ela já resolveu antes."""
    ligacoes = _em_lotes(
        supabase, "cm_validacao_tema_linha", "guia_linha_id", [linha["id"] for linha in linhas], "ligações do Retorno"
    )
    temas = _em_lotes(supabase, "cm_validacao_tema", "id", [li["tema_id"] for li in ligacoes], "temas do Retorno")
    validados = {t["id"] for t in temas if t["tipo"] == REGRA_PENDENTE and t.get("decisao") == VALIDAR_REGRA}
    voltaram = {li["guia_linha_id"] for li in ligacoes if li["tema_id"] in validados}
    return [linha for linha in linhas if linha["id"] in voltaram]


def decidir_tema(supabase, tema_id: str, corpo: dict, me: dict) -> dict:
    """Aplica a decisão do corpo ao tema aberto e o fecha com quem e quando.

    O tema é tomado antes (de ABERTO para DECIDIDO, condicional): dois cliques
    ao mesmo tempo decidem uma vez. Se a decisão falhar no meio, ele volta a
    ABERTO."""
    tema = _tema(supabase, tema_id)
    decisao = corpo.get("decisao")
    if decisao not in DECISOES.get(tema["tipo"], ()):
        raise DecisaoRecusadaError("Esta decisão não cabe neste tema.")
    fechamento = {"estado": DECIDIDO, "decisao": decisao, "decidido_por": me.get("id"), "decidido_em": _agora()}
    tomado = (
        supabase.table("cm_validacao_tema").update(fechamento).eq("id", tema["id"]).eq("estado", ABERTO).execute()
    ).data or []
    if not tomado:
        raise DecisaoRecusadaError("Este tema já foi decidido.")
    try:
        if decisao == VALIDAR_REGRA:
            _mudar_a_regra(supabase, tema, corpo, me, validar=True)
            _decidir_as_linhas(supabase, tema, me.get("id"))
    except Exception:
        supabase.table("cm_validacao_tema").update(
            {"estado": ABERTO, "decisao": None, "decidido_por": None, "decidido_em": None}
        ).eq("id", tema["id"]).execute()
        raise
    return {**tema, **fechamento}
