"""A Prova da regra (issue #1488, PRD #1484, ADR 0081, decisão 7).

Antes do Validar, a regra conferida pela pessoa refaz o Passo B nas 10 últimas
Contas concluídas da Operadora com a Memória candidata (a vigente com a regra
nova e o parâmetro novo, quando há) e devolve, por Conta, as Linhas da IA que
entrariam, sairiam ou mudariam em relação ao Guia original.

Tudo sai do que ficou guardado, porque o PDF pode já ter sido apagado: os
eventos que a IA leu no Passo A (`cm_eventos.eventos_json.ia`), os itens da
conta (`cm_conta_item`) e o Guia (`cm_guia_linha`). As Linhas do código entram
nos CÁLCULOS como entraram na análise, para a IA não repetir o que o código já
apontou. Os tetos saem das diárias pagas e das cirurgias que a análise gravou
na conta (`faltantes.base_dos_tetos`, #1508), com os parâmetros da Memória
candidata: a regra que muda só o teto de um item aparece no diff. A Conta
analisada antes disso não tem a base: a devida do consumível com teto fica
fora do diff, porque na análise o código trocou a da IA pelo teto e a prova
não tem como refazê-lo. A Linha da IA passa pelas mesmas conferências
do Passo B (regra que a memória tem, período da conta, a mesma linha já
apontada, regra pendente vira Validar, código pelo dicionário do hospital); o
preço não entra no diff.

Nada é gravado nas Contas, nas Linhas nem na Memória. Cada chamada fica em
`cm_chamada_ia` com o passo PROVA, sem a conta: a soma da conta é o custo da
análise dela, e a prova é da Operadora. O resultado fica em `cm_prova`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from typing import Any

from app.services.contas_medicas import ia, passo_b
from app.services.contas_medicas.conferencia import Conferencia, _codigos_de_diaria, tetos_da_base
from app.services.contas_medicas.dicionario import dicionario_do_banco
from app.services.contas_medicas.memoria_edicao import MudancaRecusadaError
from app.services.contas_medicas.memoria_texto import montar_texto_memoria
from app.services.contas_medicas.regra_nova import regra_candidata
from app.services.contas_medicas_conta import Conta, ItemConta
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = ["CONTAS_DA_PROVA", "provar_pendente", "provar_regra", "resumo_da_prova"]

CONTAS_DA_PROVA = 10
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")

# As concluídas são lidas da mais nova para a mais velha, em páginas: a
# Operadora pequena pode não ter 10 entre as últimas do hospital. O teto de
# páginas segura a leitura quando ela tem menos de 10 no histórico inteiro.
_PAGINA = 100
_PAGINAS_NO_MAXIMO = 20

# Quantas Contas a prova refaz ao mesmo tempo: dez chamadas em fila passariam
# do prazo do repasse do frontend.
_EM_PARALELO = 5

# O que a tela mostra de cada Linha e o que diz que ela mudou.
_CAMPOS = (
    "acao",
    "data",
    "data_fim",
    "setor",
    "codigo",
    "descricao",
    "quantidade_lancada",
    "quantidade_devida",
    "regra_codigo",
    "motivo",
)
_O_QUE_MUDA = ("quantidade_lancada", "quantidade_devida", "regra_codigo")


def _ultimas_concluidas(supabase, operadora_id: str) -> list[dict[str, Any]]:
    escolhidas: list[dict[str, Any]] = []
    for pagina in range(_PAGINAS_NO_MAXIMO):
        inicio = pagina * _PAGINA
        lote = (
            supabase.table("cm_conta")
            .select("id, atendimento_id, numero_conta, periodo_inicio, periodo_fim, concluida_em, faltantes")
            .in_("situacao", list(CONCLUIDAS))
            .order("concluida_em", desc=True)
            .range(inicio, inicio + _PAGINA - 1)
            .execute()
            .data
            or []
        )
        if not lote:
            break
        atendimentos = {
            a["id"]: a.get("numero_atendimento")
            for a in supabase.table("cm_atendimento")
            .select("id, numero_atendimento")
            .in_("id", sorted({c["atendimento_id"] for c in lote}))
            .eq("operadora_id", operadora_id)
            .execute()
            .data
            or []
        }
        escolhidas += [
            {**c, "numero_atendimento": atendimentos[c["atendimento_id"]]}
            for c in lote
            if c["atendimento_id"] in atendimentos
        ]
        if len(escolhidas) >= CONTAS_DA_PROVA or len(lote) < _PAGINA:
            break
    return escolhidas[:CONTAS_DA_PROVA]


def _eventos_guardados(supabase, atendimento_id: str) -> dict[str, Any] | None:
    """Os eventos que a IA leu no Passo A, do prontuário mais novo do atendimento."""
    gravados = (
        supabase.table("cm_eventos")
        .select("eventos_json")
        .eq("atendimento_id", atendimento_id)
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return (gravados[0].get("eventos_json") or {}).get("ia") if gravados else None


def _decimal(valor: Any) -> Decimal:
    return Decimal(str(valor if valor is not None else 0))


def _dia(valor: Any) -> date | None:
    return date.fromisoformat(str(valor)[:10]) if valor else None


def _conta_guardada(supabase, conta: dict[str, Any]) -> Conta:
    """A conta como o Passo B a lê, montada dos itens gravados na análise."""
    itens = supabase.table("cm_conta_item").select("*").eq("conta_id", conta["id"]).order("ordem").execute().data or []
    return Conta(
        atendimento=str(conta.get("numero_atendimento") or ""),
        conta=conta.get("numero_conta"),
        tipo=None,
        internacao=None,
        alta=None,
        periodo_inicio=_dia(conta.get("periodo_inicio")),
        periodo_fim=_dia(conta.get("periodo_fim")),
        acomodacao=None,
        procedimento_codigo=None,
        procedimento_descricao=None,
        plano="",
        guia=None,
        total=sum((_decimal(i.get("valor_total")) for i in itens), Decimal(0)),
        itens=tuple(
            ItemConta(
                pagina=0,
                data=_dia(i["data"]),
                codigo=i.get("codigo") or "",
                descricao=i.get("descricao") or "",
                unidade=i.get("unidade") or "",
                percentual=_decimal(i.get("percentual")),
                quantidade=_decimal(i.get("quantidade")),
                unitario=_decimal(i.get("valor_unitario")),
                total=_decimal(i.get("valor_total")),
                grupo=i.get("grupo_conta"),
                setor_codigo=None,
                setor=i.get("setor"),
                grupo_procedimento=i.get("grupo_procedimento"),
            )
            for i in itens
        ),
    )


def _linha(registro: dict[str, Any]) -> dict[str, Any]:
    linha = {campo: registro.get(campo) for campo in _CAMPOS}
    linha["data"] = str(linha["data"])[:10] if linha["data"] else None
    linha["data_fim"] = str(linha["data_fim"])[:10] if linha["data_fim"] else None
    for campo in ("quantidade_lancada", "quantidade_devida"):
        linha[campo] = float(linha[campo]) if linha[campo] is not None else None
    return linha


def _chave(linha: dict[str, Any]) -> tuple:
    return (linha["acao"], linha["codigo"], linha["data"], linha["data_fim"], linha["setor"])


def _parear(antes: list[dict[str, Any]], depois: list[dict[str, Any]]) -> dict[int, int]:
    """Cada Linha de antes com no máximo uma da prova, de mesma chave, a de mesma
    descrição primeiro: duas Linhas sem código no mesmo dia e setor não se
    confundem, e nenhuma some do diff."""
    pares: dict[int, int] = {}
    livres = list(range(len(depois)))
    for mesma_descricao in (True, False):
        for i, a in enumerate(antes):
            if i in pares:
                continue
            j = next(
                (
                    j
                    for j in livres
                    if _chave(a) == _chave(depois[j])
                    and (not mesma_descricao or a["descricao"] == depois[j]["descricao"])
                ),
                None,
            )
            if j is not None:
                pares[i] = j
                livres.remove(j)
    return pares


def _diff(
    originais: list[dict[str, Any]], novas: list[dict[str, Any]], com_teto: frozenset[str]
) -> dict[str, list[dict[str, Any]]]:
    """As Linhas da IA de antes contra as da prova, pela mesma chave do reprocesso."""
    antes = [_linha(o) for o in originais]
    depois = [_linha(n) for n in novas]
    pares = _parear(antes, depois)
    sairiam = [
        {**a, "estado": originais[i].get("estado"), "feito": originais[i].get("estado") == "FEITO"}
        for i, a in enumerate(antes)
        if i not in pares
    ]
    pareadas = set(pares.values())
    entrariam = [n for j, n in enumerate(depois) if j not in pareadas]
    mudariam = []
    for i, j in pares.items():
        a, n = antes[i], depois[j]
        if a["codigo"] in com_teto:
            # Na análise a devida veio do teto, não da IA.
            n = {**n, "quantidade_devida": a["quantidade_devida"]}
        if any(a[c] != n[c] for c in _O_QUE_MUDA):
            mudariam.append({"antes": {**a, "estado": originais[i].get("estado")}, "depois": n})
    return {"entrariam": entrariam, "sairiam": sairiam, "mudariam": mudariam}


def _codigos_com_teto(parametros: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        str(teto["codigo"])
        for teto in (parametros.get("tetos_por_dia") or {}).values()
        if isinstance(teto, dict) and teto.get("codigo")
    )


def _provar_conta(
    supabase,
    conta: dict[str, Any],
    memoria: str,
    regras: dict[str, dict],
    parametros: dict,
    dicionario: dict[str, set[str]],
    modelo: str | None = None,
) -> dict[str, Any]:
    resumo = {
        "conta_id": conta["id"],
        "numero_atendimento": conta.get("numero_atendimento"),
        "numero_conta": conta.get("numero_conta"),
        "concluida_em": conta.get("concluida_em"),
    }
    eventos = _eventos_guardados(supabase, conta["atendimento_id"])
    if eventos is None:
        return {**resumo, "refeita": False, "mudaria": False, "entrariam": [], "sairiam": [], "mudariam": []}
    guia = supabase.table("cm_guia_linha").select("*").eq("conta_id", conta["id"]).execute().data or []
    do_codigo = tuple(linha for linha in guia if linha.get("origem") != "IA")
    da_ia = [linha for linha in guia if linha.get("origem") == "IA"]
    lida = _conta_guardada(supabase, conta)
    faltantes = conta.get("faltantes")
    base = faltantes.get("base_dos_tetos") if isinstance(faltantes, dict) else None
    conferencia = Conferencia(
        linhas=do_codigo,
        descartadas=(),
        nota=None,
        diarias_pagas=tuple(base["diarias_pagas"]) if base else (),
        tetos=tetos_da_base(parametros, base) if base else (),
    )

    resposta = ia.comparar_conta(
        memoria,
        passo_b.eventos_do_periodo(eventos, lida.periodo_inicio, lida.periodo_fim),
        passo_b._itens(lida),
        passo_b._calculos(conferencia),
        supabase=supabase,
        conta_id=None,
        atendimento_id=conta["atendimento_id"],
        passo="PROVA",
        modelo=modelo,
    )
    conferencias = passo_b._Conferencias(
        conta=lida,
        conferencia=conferencia,
        regras=regras,
        # O preço não entra no diff: a prova não consulta a tabela.
        preco=lambda *_: "sem preço",
        dicionario=dicionario,
        diarias=frozenset(_codigos_de_diaria(parametros)),
        bloqueados=passo_b._bloqueados(supabase, resposta),
        # O PDF pode ter saído do sistema: o trecho não é conferido na página.
        texto_da_pagina=lambda _numero: None,
        apontadas=[p for p in map(passo_b._periodo_da_linha, do_codigo) if p is not None],
        descartadas=[],
    )
    novas = [r for r in map(conferencias.registro, resposta.linhas) if r is not None]
    # Sem a base, a devida do item com teto fica fora do diff.
    diff = _diff(da_ia, novas, frozenset() if base else _codigos_com_teto(parametros))
    return {**resumo, "refeita": True, "mudaria": any(diff.values()), **diff}


def resumo_da_prova(por_conta: list[dict[str, Any]]) -> dict[str, Any]:
    """As contas refeitas, se alguma mudaria, as Linhas Feito que sumiriam e o
    aviso, a partir do resultado por Conta (o `resultado_json` de `cm_prova`)."""
    refeitas = sum(1 for c in por_conta if c["refeita"])
    mudaria = any(c["mudaria"] for c in por_conta)
    aviso = None
    if not refeitas:
        aviso = "A operadora não tem conta concluída com os eventos guardados para provar a regra."
    elif not mudaria:
        aviso = f"A regra não mudaria nada nas {refeitas} últimas contas concluídas."
    return {
        "contas": refeitas,
        "mudaria": mudaria,
        "feitas_que_sumiriam": sum(1 for c in por_conta for linha in c["sairiam"] if linha["feito"]),
        "aviso": aviso,
    }


def provar_regra(
    supabase,
    sigla: str,
    *,
    secao: str,
    texto: str,
    tipo: str | None,
    origem: str | None,
    parametro: dict[str, Any] | None,
    autor_id: str | None,
    codigo: str | None = None,
    lote_item_id: str | None = None,
    sem: tuple[str, ...] = (),
    descartar: bool = False,
) -> dict[str, Any]:
    """A prova da regra conferida pela pessoa, guardada em `cm_prova`.

    Com `codigo`, a regra é a alterada do lote do Auditor (#1490): o texto novo
    toma o lugar da regra que já existe na memória candidata, em vez de entrar
    ao lado dela. `sem` são as regras em conflito que o item junta ou substitui
    (ADR 0081, decisão 8): saem da memória candidata, como sairão no ok.
    `lote_item_id` liga a prova ao item do lote. Com `descartar`, a regra do
    `codigo` sai da memória candidata e nada entra no lugar: é a prova da Regra
    pendente que o Auditor sugere descartar (#1494)."""
    candidata = regra_candidata(
        supabase,
        sigla,
        secao=secao,
        texto=texto,
        tipo=tipo,
        origem=origem,
        parametro=parametro,
        autor_id=autor_id,
    )
    vigente, nova = candidata["vigente"], candidata["regra"]
    regras = candidata["regras"]
    if codigo:
        if not any(r["codigo"] == codigo for r in regras):
            raise MudancaRecusadaError(f"A regra {codigo} não está na memória vigente de {candidata['sigla']}.")
        nova = {**nova, "codigo": codigo}
        regras = [r for r in regras if r["codigo"] != codigo]
    return _provar(
        supabase,
        operadora_id=candidata["operadora_id"],
        sigla=candidata["sigla"],
        vigente=vigente,
        regras=[r for r in regras if r["codigo"] not in sem],
        nova=nova,
        parametros=candidata["parametros"] or vigente.get("parametros_json") or {},
        autor_id=autor_id,
        lote_item_id=lote_item_id,
        descartar=descartar,
    )


def provar_pendente(supabase, operadora_id: str, regra_codigo: str, *, modelo: str) -> dict[str, Any]:
    """A prova da regra pendente da memória vigente, como se ela fosse validada
    com o texto de hoje (issue #1491): o Auditor lê a prova antes de recomendar
    o Tema de Regra pendente. Sem autor: quem pede é o Auditor. Roda no
    `modelo` da Validação, não no do passo B (#1523)."""
    operadora = supabase.table("cm_operadora").select("id, sigla").eq("id", operadora_id).execute().data or []
    vigentes = (
        supabase.table("cm_memoria_versao")
        .select("*")
        .eq("operadora_id", operadora_id)
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    if not operadora or not vigentes:
        raise LookupError("A operadora não tem memória vigente.")
    vigente = vigentes[0]
    regras = (
        supabase.table("cm_regra").select("*").eq("memoria_versao_id", vigente["id"]).eq("ativa", True).execute().data
        or []
    )
    pendente = next((r for r in regras if r["codigo"] == regra_codigo), None)
    if pendente is None:
        raise LookupError(f"A regra {regra_codigo} não está na memória vigente.")
    return _provar(
        supabase,
        operadora_id=operadora_id,
        sigla=operadora[0]["sigla"],
        vigente=vigente,
        regras=[r for r in regras if r is not pendente],
        nova={**pendente, "status": "VIGENTE"},
        parametros=vigente.get("parametros_json") or {},
        autor_id=None,
        modelo=modelo,
    )


def _provar(
    supabase,
    *,
    operadora_id: str,
    sigla: str,
    vigente: dict[str, Any],
    regras: list[dict[str, Any]],
    nova: dict[str, Any],
    parametros: dict[str, Any],
    autor_id: str | None,
    lote_item_id: str | None = None,
    descartar: bool = False,
    modelo: str | None = None,
) -> dict[str, Any]:
    """A memória vigente com a regra `nova` refaz o Passo B nas últimas
    concluídas da operadora; o resultado fica em `cm_prova`. Com `descartar`,
    a `nova` não entra: a memória fica sem ela (#1494). Sem `modelo`, o do
    passo B."""
    regras = [*regras, *([] if descartar else [nova])]
    operadora = (supabase.table("cm_operadora").select("nome").eq("id", operadora_id).execute().data or [{}])[0]
    memoria = montar_texto_memoria(
        sigla,
        operadora.get("nome") or sigla,
        vigente["versao"],
        parametros,
        sorted(regras, key=lambda r: r["codigo"]),
    )
    por_codigo = {r["codigo"]: r for r in regras}

    contas = _ultimas_concluidas(supabase, operadora_id)
    # O mesmo dicionário com que a análise dá código à Linha da IA que veio sem.
    dicionario = dicionario_do_banco(supabase)
    with ThreadPoolExecutor(max_workers=_EM_PARALELO) as executor:
        por_conta = list(
            executor.map(
                lambda c: _provar_conta(supabase, c, memoria, por_codigo, parametros, dicionario, modelo), contas
            )
        )
    # O texto que a IA escreveu vai para a tela: sem travessão nem meia-risca.
    por_conta = sanitizar_estrutura(por_conta)

    resumo = resumo_da_prova(por_conta)
    prova = (
        supabase.table("cm_prova")
        .insert(
            {
                "operadora_id": operadora_id,
                "memoria_versao_id": vigente["id"],
                "lote_item_id": lote_item_id,
                "regra_codigo": nova["codigo"],
                "regra_texto": nova["texto"],
                "contas": resumo["contas"],
                "mudaria": resumo["mudaria"],
                "resultado_json": por_conta,
                "criado_por": autor_id,
            }
        )
        .execute()
        .data
    )[0]
    return {"prova_id": prova["id"], "regra": nova["codigo"], **resumo, "por_conta": por_conta}
