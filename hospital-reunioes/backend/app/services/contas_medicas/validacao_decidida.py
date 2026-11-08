"""A fila de Validação chega decidida (issue #1491, PRD #1484, ADR 0081, decisão 13).

O Auditor decide cada Tema aberto: a decisão que recomenda, o motivo e, no
Tema de Regra pendente, a Prova da regra (a regra pendente refeita como
vigente nas últimas Contas concluídas da operadora). A recomendação fica nas
colunas da migration 126 em `cm_validacao_tema`; a decisão de quem aprova
continua em `decisao`.

Quem decide na Validação aprova o lote de uma vez. Cada Tema aprovado passa
pelo mesmo caminho do cartão (`validacao.decidir_tema`): versão nova da
Memória e Retorno da Conta concluída só com as Linhas decididas. O Tema que a
pessoa corrigir antes, pelo cartão, já saiu da fila e o lote não mexe nele.

A recomendação sai do relógio do backend, não da tela: a prova refaz até dez
Contas e não cabe no tempo de um pedido.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.prova_da_regra import provar_pendente
from app.services.contas_medicas.validacao import (
    ABERTO,
    DECISOES,
    EDITAR_REGRA,
    ENVIAR_AO_CADASTRO,
    REGRA_PENDENTE,
    RESPONDER,
    DecisaoRecusadaError,
    TemaNaoEncontradoError,
    _em_lotes,
    decidir_tema,
    fila_de_validacao,
    juntar_motivo,
    separar_motivo,
)
from app.services.paginacao import ler_tudo
from app.utils.text_sanitizer import sanitizar_travessao

__all__ = ["aprovar_lote", "recomendar_abertos"]

logger = logging.getLogger(__name__)

# Quantos Temas o Auditor decide por rodada do relógio: cada Regra pendente
# custa até dez chamadas da prova.
TEMAS_POR_RODADA = 5

_ROTULO_DO_TIPO = {
    "REGRA_PENDENTE": "Regra pendente",
    "BLOQUEADO": "Código bloqueado",
    "OBSERVACAO": "Observação do time",
    "DICIONARIO": "Termo do dicionário",
}

# O que a decisão leva de texto: a regra editada ou a resposta ao time.
_COM_TEXTO = (EDITAR_REGRA, RESPONDER)


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _sem_recomendacao(supabase) -> set[str]:
    return {
        t["id"]
        for t in ler_tudo(
            lambda: (
                supabase.table("cm_validacao_tema")
                .select("id")
                .eq("estado", ABERTO)
                .is_("recomendado_em", "null")
                .order("id")
            ),
            rotulo="temas sem recomendação",
        )
    }


def _linhas_da_prova(linhas: list[dict]) -> list[dict]:
    return [
        {c: linha.get(c) for c in ("acao", "data", "codigo", "descricao", "quantidade_devida", "feito") if c in linha}
        for linha in linhas
    ]


def _texto_da_prova(prova: dict[str, Any]) -> str:
    if prova.get("aviso"):
        return prova["aviso"]
    mudancas = [
        {
            "conta": c.get("numero_conta"),
            "entrariam": _linhas_da_prova(c["entrariam"]),
            "sairiam": _linhas_da_prova(c["sairiam"]),
            "mudariam": [
                {"antes": _linhas_da_prova([m["antes"]])[0], "depois": _linhas_da_prova([m["depois"]])[0]}
                for m in c["mudariam"]
            ],
        }
        for c in prova["por_conta"]
        if c.get("mudaria")
    ]
    return (
        f"Refeita em {prova['contas']} contas concluídas; "
        f"{prova['feitas_que_sumiriam']} Linhas já feitas pela faturista sumiriam.\n"
        + json.dumps(mudancas, ensure_ascii=False, default=str)
    )


def _texto_do_tema(cartao: dict[str, Any], prova: dict[str, Any] | None) -> str:
    """O que o Auditor lê do Tema: o cartão da fila, sem dado de paciente."""
    partes = [
        f"Tipo: {_ROTULO_DO_TIPO[cartao['tipo']]}",
        f"Título: {cartao['titulo']}",
        f"Operadora: {cartao.get('operadora') or 'várias'}",
        f"Contas: {cartao['contas']}",
        f"R$ em jogo: {cartao['valor']:.2f}",
        f"Decisões que cabem: {', '.join(DECISOES[cartao['tipo']])}",
    ]
    if regra := cartao.get("regra"):
        partes.append(f"Regra {cartao['regra_codigo']} ({regra.get('status')}): {regra.get('texto')}")
    if cartao.get("codigo_item"):
        partes.append(f"Código bloqueado: {cartao['codigo_item']}")
    if termo := cartao.get("dicionario"):
        partes.append(
            f"Termo: {termo['termo']}; código: {termo.get('codigo_conta') or 'sem código'}; "
            f"descrição: {termo.get('descricao_conta') or 'sem descrição'}"
        )
    if cartao.get("observacoes"):
        partes.append("O QUE O TIME DISSE")
        partes += [f"- {fala}" for fala in cartao["observacoes"]]
    if prova is not None:
        partes.append(f"PROVA DA REGRA\n{_texto_da_prova(prova)}")
    return "\n".join(partes)


def _cabe(tema: dict[str, Any], resposta: ia.RecomendacaoDoTema) -> bool:
    if resposta.decisao not in DECISOES.get(tema["tipo"], ()) or not resposta.motivo.strip():
        return False
    if resposta.decisao in _COM_TEXTO and not resposta.texto.strip():
        return False
    return not (resposta.decisao == EDITAR_REGRA and not tema.get("regra_codigo"))


def _recomendar(supabase, cartao: dict[str, Any], tema: dict[str, Any]) -> bool:
    operadora_id = tema.get("operadora_id")
    prova = None
    if tema["tipo"] == REGRA_PENDENTE and operadora_id and tema.get("regra_codigo"):
        prova = provar_pendente(supabase, operadora_id, tema["regra_codigo"])
    memoria = gerar_texto_memoria(supabase, operadora_id) if operadora_id else "(o tema não é de uma operadora só)"
    resposta = ia.recomendar_tema(memoria, _texto_do_tema(cartao, prova), supabase=supabase)
    cabe = _cabe(tema, resposta)
    if not cabe:
        # Fica sem recomendação, e marcado: a pessoa decide pelo cartão, e o
        # relógio não pergunta de novo a cada rodada.
        logger.warning("[ContasMedicas] Auditor recomendou %s, que não cabe no tema %s", resposta.decisao, tema["id"])
    texto = resposta.texto if resposta.decisao in _COM_TEXTO else ""
    supabase.table("cm_validacao_tema").update(
        {
            "recomendacao": resposta.decisao if cabe else None,
            "recomendacao_motivo": (
                juntar_motivo(sanitizar_travessao(resposta.motivo), sanitizar_travessao(texto)) if cabe else None
            ),
            "recomendacao_prova_id": prova["prova_id"] if prova and cabe else None,
            "recomendado_em": _agora(),
        }
    ).eq("id", tema["id"]).eq("estado", ABERTO).execute()
    return cabe


def recomendar_abertos(supabase, limite: int = TEMAS_POR_RODADA) -> int:
    """O Auditor decide os Temas abertos ainda sem recomendação, até `limite`
    por rodada. Devolve quantos ganharam recomendação. O Tema que falhar (IA
    fora, prova sem memória) fica para a próxima rodada."""
    cartoes = fila_de_validacao(supabase)["temas"]
    sem = _sem_recomendacao(supabase)
    a_fazer = [c for c in cartoes if c["id"] in sem][:limite]
    temas = {t["id"]: t for t in _em_lotes(supabase, "cm_validacao_tema", "id", [c["id"] for c in a_fazer], "temas")}
    recomendados = 0
    for cartao in a_fazer:
        try:
            recomendados += _recomendar(supabase, cartao, temas[cartao["id"]])
        except Exception as erro:
            logger.error("[ContasMedicas] Auditor não recomendou o tema %s: %s", cartao["id"], type(erro).__name__)
    return recomendados


_RECUSAS = (
    DecisaoRecusadaError,
    TemaNaoEncontradoError,
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)


# A recomendação gravada não é mais a que a tela mostrou: uma observação nova
# apagou a antiga e o relógio gravou outra. Ninguém viu esta, então o lote não
# a aplica.
_RECOMENDACAO_MUDOU = "A recomendação do Auditor mudou depois que a tela abriu. Confira o cartão de novo."


def aprovar_lote(supabase, vistos: list[dict[str, str]], me: dict) -> dict[str, Any]:
    """Aplica a recomendação de cada Tema aberto do lote pelo caminho do
    cartão, desde que seja a que a tela mostrou (`decisao` e `recomendado_em`
    de cada item de `vistos`). O Tema já decidido (corrigido pela pessoa) ou sem
    recomendação fica como está; o que recusar ou cuja recomendação mudou volta
    em `falhas`, e o resto segue."""
    por_id = {v["id"]: v for v in vistos}
    ids = list(por_id)
    temas = {t["id"]: t for t in _em_lotes(supabase, "cm_validacao_tema", "id", ids, "temas do lote")}
    decididos: list[dict[str, str]] = []
    falhas: list[dict[str, str]] = []
    cadastro: list[str] = []
    for tema_id in ids:
        tema = temas.get(tema_id)
        if tema is None or tema.get("estado") != ABERTO or not tema.get("recomendacao"):
            continue
        decisao = tema["recomendacao"]
        visto = por_id[tema_id]
        if (visto["decisao"], visto["recomendado_em"]) != (decisao, tema.get("recomendado_em")):
            falhas.append({"id": tema_id, "titulo": tema["titulo"], "motivo": _RECOMENDACAO_MUDOU})
            continue
        _motivo, texto = separar_motivo(tema.get("recomendacao_motivo"))
        try:
            decidir_tema(supabase, tema_id, {"decisao": decisao, "texto": texto or None}, me)
        except _RECUSAS as exc:
            falhas.append({"id": tema_id, "titulo": tema["titulo"], "motivo": str(exc)})
            continue
        decididos.append({"id": tema_id, "decisao": decisao})
        if decisao == ENVIAR_AO_CADASTRO:
            cadastro.append(tema_id)
    return {"decididos": decididos, "falhas": falhas, "cadastro": cadastro}
