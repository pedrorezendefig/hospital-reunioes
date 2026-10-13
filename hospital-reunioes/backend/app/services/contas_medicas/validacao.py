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

import csv
import io
import re
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.services.contas_medicas.ia import chamada_curta
from app.services.contas_medicas.memoria_edicao import mudar_regra
from app.services.contas_medicas.operadoras import memoria_vigente
from app.services.paginacao import ler_tudo
from app.services.prompt_loader import load_prompt
from app.utils.text_sanitizer import sanitizar_travessao

__all__ = [
    "DecisaoRecusadaError",
    "TemaNaoEncontradoError",
    "acao_decidida",
    "acompanhar_marcacao",
    "csv_do_cadastro",
    "decidir_tema",
    "fila_de_validacao",
    "leitura_da_observacao",
    "linhas_do_retorno",
    "respostas_da_conta",
    "temas_da_observacao",
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


def _poucas_por_id(supabase, tabela: str, coluna: str, ids: Iterable[str]) -> list[dict]:
    """A leitura do que é de uma conta ou de uma linha: lotes de 100 ids, cada
    id com poucas linhas, longe do teto de mil do PostgREST. Sem paginação."""
    ids = [i for i in dict.fromkeys(ids) if i]
    linhas: list[dict] = []
    for i in range(0, len(ids), LOTE_DE_IDS):
        linhas += supabase.table(tabela).select("*").in_(coluna, ids[i : i + LOTE_DE_IDS]).execute().data or []
    return linhas


def _tema_aberto(
    supabase,
    tipo: str,
    titulo: str,
    *,
    operadora_id: str | None = None,
    regra_codigo: str | None = None,
    codigo_item: str | None = None,
) -> dict:
    """O tema aberto da chave, ou um novo. Quem chama segura a trava.

    A chave pode ter coluna nula (o Bloqueado não tem operadora; a observação
    sem regra citada não tem regra): o banco filtra as preenchidas, e o nulo é
    conferido aqui."""
    chave = {"operadora_id": operadora_id, "regra_codigo": regra_codigo, "codigo_item": codigo_item}
    consulta = supabase.table("cm_validacao_tema").select("*").eq("tipo", tipo).eq("estado", ABERTO)
    for coluna, valor in chave.items():
        if valor is not None:
            consulta = consulta.eq(coluna, valor)
    abertos = consulta.execute().data or []
    achado = next((t for t in abertos if all(t.get(c) == v for c, v in chave.items())), None)
    if achado:
        return achado
    return supabase.table("cm_validacao_tema").insert({"tipo": tipo, "titulo": titulo, **chave}).execute().data[0]


def _ligar(supabase, tema: dict, *, guia_linha_id: str | None = None, observacao_id: str | None = None) -> None:
    supabase.table("cm_validacao_tema_linha").insert(
        {"tema_id": tema["id"], "guia_linha_id": guia_linha_id, "observacao_id": observacao_id}
    ).execute()


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


def acompanhar_marcacao(supabase, conta: dict, linha: dict) -> None:
    """A marcação da faturista na fila de Validação. Toda marcação (e o
    Desfazer) tira a linha dos temas abertos de Bloqueado e de observação; o
    Bloqueado põe a linha no tema aberto do código."""
    with _trava_dos_temas:
        ligacoes = (
            supabase.table("cm_validacao_tema_linha").select("*").eq("guia_linha_id", linha["id"]).execute().data or []
        )
        temas = _poucas_por_id(supabase, "cm_validacao_tema", "id", [li["tema_id"] for li in ligacoes])
        abertos = [t["id"] for t in temas if t.get("estado") == ABERTO and t["tipo"] in (BLOQUEADO, OBSERVACAO)]
        if abertos:
            supabase.table("cm_validacao_tema_linha").delete().eq("guia_linha_id", linha["id"]).in_(
                "tema_id", abertos
            ).execute()
        if linha.get("estado") == "BLOQUEADO" and linha.get("codigo"):
            tema = _tema_aberto(supabase, BLOQUEADO, f"Código {linha['codigo']} bloqueado", codigo_item=linha["codigo"])
            _ligar(supabase, tema, guia_linha_id=linha["id"])
        elif linha.get("estado") == "NAO_PROCEDE":
            operadora_id = _operadora_da_conta(supabase, conta["id"])
            _ligar(
                supabase,
                _tema_da_observacao(supabase, operadora_id, linha.get("regra_codigo")),
                guia_linha_id=linha["id"],
            )


def _tema_da_observacao(supabase, operadora_id: str | None, regra: str | None) -> dict:
    """O tema aberto das observações sobre a regra. A leitura da IA guardada
    nele não leu a observação que está chegando: some, e a próxima é nova."""
    titulo = f"Observações sobre a regra {regra}" if regra else "Observações sem regra citada"
    tema = _tema_aberto(supabase, OBSERVACAO, titulo, operadora_id=operadora_id, regra_codigo=regra)
    if tema.get("leitura_ia"):
        supabase.table("cm_validacao_tema").update({"leitura_ia": None}).eq("id", tema["id"]).execute()
    return tema


def temas_da_observacao(supabase, conta: dict, observacao: dict) -> None:
    """A observação da conclusão entra no tema de cada regra da memória vigente
    que ela cita pelo código; sem regra citada, no tema da operadora sem regra."""
    operadora_id = _operadora_da_conta(supabase, conta["id"])
    memoria = memoria_vigente(supabase, operadora_id) if operadora_id else None
    texto = observacao.get("texto") or ""
    citadas = sorted(
        {
            r["codigo"]
            for r in (memoria or {}).get("regras", [])
            if re.search(rf"(?<![\w-]){re.escape(r['codigo'])}(?![\w-])", texto, re.IGNORECASE)
        }
    )
    with _trava_dos_temas:
        for regra in citadas or [None]:
            _ligar(supabase, _tema_da_observacao(supabase, operadora_id, regra), observacao_id=observacao["id"])


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


# O motivo do Não procede como a faturista escolheu no Guia.
MOTIVOS_NAO_PROCEDE = {
    "JA_ESTA_NA_CONTA": "Já está na conta",
    "SEM_EVIDENCIA": "Sem evidência no prontuário",
    "REGRA_E_OUTRA": "A regra é outra",
    "OUTRO": "Outro",
}


def _falas_do_time(ligadas: list[dict], linhas: dict[str, dict], observacoes: dict[str, dict]) -> list[str]:
    """O que o time disse no tema, na ordem em que chegou: o motivo do Não
    procede (com o texto, quando houver) e as observações da conclusão."""
    falas = []
    for ligacao in sorted(ligadas, key=lambda li: li.get("criado_em") or ""):
        if (linha := linhas.get(ligacao.get("guia_linha_id"))) is not None:
            motivo = MOTIVOS_NAO_PROCEDE.get(linha.get("motivo_nao_procede") or "", "Não procede")
            falas.append(f"{motivo}: {linha['texto_nao_procede']}" if linha.get("texto_nao_procede") else motivo)
        elif (observacao := observacoes.get(ligacao.get("observacao_id"))) is not None:
            falas.append(observacao["texto"])
    return falas


def _temas_do_dicionario(supabase) -> None:
    """Um tema por termo que a IA propôs ao dicionário e ninguém decidiu ainda.

    A proposta nasce fora daqui (a pergunta curta do dicionário): a fila abre o
    tema que falta ao ser lida. O tema decidido também conta, para o termo
    rejeitado não voltar."""
    propostas = ler_tudo(
        lambda: (
            supabase.table("cm_item_dicionario")
            .select("id, termo, origem, situacao")
            .eq("origem", "IA")
            .eq("situacao", "PROPOSTO")
            .order("id")
        ),
        rotulo="propostas do dicionário",
    )
    if not propostas:
        return
    with _trava_dos_temas:
        com_tema = {
            t.get("item_dicionario_id")
            for t in _em_lotes(
                supabase, "cm_validacao_tema", "item_dicionario_id", [p["id"] for p in propostas], "temas do dicionário"
            )
        }
        novas = [
            {"tipo": DICIONARIO, "titulo": f"Termo {p['termo']} no dicionário", "item_dicionario_id": p["id"]}
            for p in propostas
            if p["id"] not in com_tema
        ]
        if novas:
            supabase.table("cm_validacao_tema").insert(novas).execute()


def fila_de_validacao(supabase) -> dict[str, Any]:
    """Os temas abertos como a tela mostra, do maior R$ em jogo para o menor,
    e os três números do topo: aguardando decisão, contas afetadas e R$ em jogo."""
    _temas_do_dicionario(supabase)
    temas = ler_tudo(
        lambda: supabase.table("cm_validacao_tema").select("*").eq("estado", ABERTO).order("id"), rotulo="temas abertos"
    )
    termos = {
        t["id"]: t
        for t in _em_lotes(
            supabase, "cm_item_dicionario", "id", [t.get("item_dicionario_id") for t in temas], "termos da Validação"
        )
    }
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
        ligadas = do_tema.get(tema["id"], [])
        das_linhas = [linhas[li["guia_linha_id"]] for li in ligadas if li.get("guia_linha_id") in linhas]
        das_observacoes = [observacoes[li["observacao_id"]] for li in ligadas if li.get("observacao_id") in observacoes]
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
                "observacoes": _falas_do_time(ligadas, linhas, observacoes) if tema["tipo"] == OBSERVACAO else [],
                "dicionario": (
                    {k: termo.get(k) for k in ("termo", "codigo_conta", "descricao_conta")}
                    if (termo := termos.get(tema.get("item_dicionario_id")))
                    else None
                ),
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


COLUNAS_DO_CADASTRO = ("Código", "Descrição", "Operadora", "Coluna", "Preço de tabela", "Contas afetadas")


def _reais(valor) -> str:
    return "" if valor is None else f"{_dinheiro(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def csv_do_cadastro(supabase, tema_id: str) -> str:
    """A lista do código bloqueado para o cadastro e a consultoria do MV: uma
    linha por descrição, operadora, coluna e preço, com as contas afetadas.
    Separado por ponto e vírgula, como as planilhas da casa."""
    linhas = _linhas_do_tema(supabase, tema_id)
    contas = {c["id"]: c for c in _em_lotes(supabase, "cm_conta", "id", [x["conta_id"] for x in linhas], "contas")}
    atendimentos = {
        a["id"]: a
        for a in _em_lotes(
            supabase, "cm_atendimento", "id", [c["atendimento_id"] for c in contas.values()], "atendimentos"
        )
    }
    siglas = {
        o["id"]: o["sigla"]
        for o in _em_lotes(
            supabase, "cm_operadora", "id", [a.get("operadora_id") for a in atendimentos.values()], "operadoras"
        )
    }
    grupos: dict[tuple, list[str]] = {}
    for linha in sorted(linhas, key=lambda x: (contas.get(x["conta_id"]) or {}).get("ordem_fila") or 0):
        conta = contas.get(linha["conta_id"]) or {}
        atendimento = atendimentos.get(conta.get("atendimento_id")) or {}
        chave = (
            linha.get("codigo") or "",
            linha.get("descricao") or "",
            siglas.get(atendimento.get("operadora_id"), ""),
            atendimento.get("coluna_preco") or "",
            _reais(linha.get("preco_tabela")),
        )
        rotulo = f"{atendimento.get('numero_atendimento') or ''} ({conta.get('numero_conta') or ''})".strip()
        if rotulo not in grupos.setdefault(chave, []):
            grupos[chave].append(rotulo)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS_DO_CADASTRO)
    for chave, rotulos in grupos.items():
        escritor.writerow([_celula(valor) for valor in (*chave, ", ".join(rotulos))])
    return saida.getvalue()


def _celula(valor: str) -> str:
    """A descrição vem do PDF do MV: a célula que começa como fórmula vira texto."""
    return f"'{valor}" if valor[:1] in ("=", "+", "-", "@", "\t", "\r") else valor


def linhas_do_retorno(supabase, linhas: list[dict]) -> list[dict]:
    """As linhas da conta em Retorno que voltaram para a faturista: as que a
    Validação decidiu ao validar a regra. As outras ela já resolveu antes."""
    ligacoes = _poucas_por_id(supabase, "cm_validacao_tema_linha", "guia_linha_id", [linha["id"] for linha in linhas])
    temas = _poucas_por_id(supabase, "cm_validacao_tema", "id", [li["tema_id"] for li in ligacoes])
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
    resposta = sanitizar_travessao((corpo.get("texto") or "").strip()) or None
    if decisao == RESPONDER and not resposta:
        raise DecisaoRecusadaError("Escreva a resposta ao time.")
    if decisao == EDITAR_REGRA and not tema.get("regra_codigo"):
        raise DecisaoRecusadaError("A observação não cita regra: edite pela Memória da operadora.")
    fechamento = {
        "estado": DECIDIDO,
        "decisao": decisao,
        "resposta": resposta if decisao == RESPONDER else None,
        "decidido_por": me.get("id"),
        "decidido_em": _agora(),
    }
    tomado = (
        supabase.table("cm_validacao_tema").update(fechamento).eq("id", tema["id"]).eq("estado", ABERTO).execute()
    ).data or []
    if not tomado:
        raise DecisaoRecusadaError("Este tema já foi decidido.")
    try:
        if decisao == VALIDAR_REGRA:
            _mudar_a_regra(supabase, tema, corpo, me, validar=True)
            _decidir_as_linhas(supabase, tema, me.get("id"))
        elif decisao == EDITAR_REGRA:
            _mudar_a_regra(supabase, tema, corpo, me, validar=False)
        elif decisao == CONFIRMAR:
            # Confirmado, o termo passa a casar na próxima análise.
            supabase.table("cm_item_dicionario").update({"situacao": "CONFIRMADO"}).eq(
                "id", tema.get("item_dicionario_id")
            ).execute()
    except Exception:
        supabase.table("cm_validacao_tema").update(
            {"estado": ABERTO, "decisao": None, "resposta": None, "decidido_por": None, "decidido_em": None}
        ).eq("id", tema["id"]).execute()
        raise
    return {**tema, **fechamento}


# ----------------------------------------------------------------------------------
# A leitura da IA sobre a observação
# ----------------------------------------------------------------------------------


class LeituraDaObservacao(BaseModel):
    """A resposta curta: a regra atual já cobre o caso, e a sugestão."""

    model_config = ConfigDict(extra="forbid")

    cobre: bool
    sugestao: Literal["MANTER", "EDITAR"]
    leitura: str


def _frase_da_leitura(leitura: LeituraDaObservacao) -> str:
    cobre = "A regra atual já cobre o caso." if leitura.cobre else "A regra atual não cobre o caso."
    sugestao = "manter a regra" if leitura.sugestao == "MANTER" else "editar a regra"
    return sanitizar_travessao(f"{cobre} {leitura.leitura.strip()} Sugestão: {sugestao}.")


def leitura_da_observacao(supabase, tema_id: str) -> str:
    """A leitura da IA sobre as observações do tema: uma chamada curta, guardada
    no tema. É apoio; quem decide é a pessoa. Observação nova no tema apaga a
    leitura guardada, e a próxima chamada lê de novo."""
    tema = _tema(supabase, tema_id)
    if tema["tipo"] != OBSERVACAO:
        raise DecisaoRecusadaError("A leitura da IA é só das observações do time.")
    if tema.get("leitura_ia"):
        return tema["leitura_ia"]
    ligadas = _ligacoes(supabase, tema["id"])
    linhas = {
        li["id"]: li
        for li in _em_lotes(supabase, "cm_guia_linha", "id", [x.get("guia_linha_id") for x in ligadas], "linhas")
    }
    observacoes = {
        o["id"]: o for o in _em_lotes(supabase, "cm_observacao", "id", [x.get("observacao_id") for x in ligadas], "obs")
    }
    regra = (
        _regras_vigentes(supabase, [tema["operadora_id"]]).get((tema["operadora_id"], tema.get("regra_codigo")))
        if tema.get("operadora_id")
        else None
    )
    partes = [
        f"REGRA {tema['regra_codigo']} ({regra.get('status')}): {regra.get('texto')}"
        if regra
        else "REGRA: a observação não cita regra da memória."
    ]
    partes.append("OBSERVAÇÕES DO TIME")
    partes += [f"- {fala}" for fala in _falas_do_time(ligadas, linhas, observacoes)]
    leitura = chamada_curta(
        load_prompt("contas_medicas_observacao"),
        "\n".join(partes),
        LeituraDaObservacao,
        passo="OBSERVACAO",
        supabase=supabase,
        conta_id=None,
    )
    frase = _frase_da_leitura(leitura)
    supabase.table("cm_validacao_tema").update({"leitura_ia": frase}).eq("id", tema["id"]).execute()
    return frase


def respostas_da_conta(supabase, conta_id: str, linhas: list[dict]) -> list[dict]:
    """O que a Validação respondeu ao time sobre esta conta: os temas ligados a
    uma linha ou a uma observação dela, decididos com "Responder ao time"."""
    observacoes = supabase.table("cm_observacao").select("id").eq("conta_id", conta_id).execute().data or []
    ligacoes = _poucas_por_id(
        supabase, "cm_validacao_tema_linha", "guia_linha_id", [linha["id"] for linha in linhas]
    ) + _poucas_por_id(supabase, "cm_validacao_tema_linha", "observacao_id", [o["id"] for o in observacoes])
    temas = _poucas_por_id(supabase, "cm_validacao_tema", "id", [li["tema_id"] for li in ligacoes])
    respondidos = [t for t in temas if t.get("decisao") == RESPONDER and t.get("resposta")]
    return [
        {
            "titulo": t["titulo"],
            "regra_codigo": t.get("regra_codigo"),
            "resposta": t["resposta"],
            "decidido_em": t.get("decidido_em"),
        }
        for t in sorted(respondidos, key=lambda t: t.get("decidido_em") or "")
    ]
