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

A recomendação só sai quando alguém pede, pelo botão da tela (ADR 0082,
issue #1523): o pedido mostra antes quantos Temas e quanto deve custar, e roda
em segundo plano, porque a prova refaz até dez Contas e não cabe no tempo de
uma requisição. Um pedido por vez. A Prova e o Auditor rodam no modelo da
Validação (`CM_IA_MODELO_VALIDACAO`), não no do passo B.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.prova_da_regra import _ultimas_concluidas, provar_pendente
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

__all__ = [
    "aprovar_lote",
    "liberar",
    "pedido_de_recomendacao",
    "recomendar_abertos",
    "recomendar_e_liberar",
    "reservar",
]

logger = logging.getLogger(__name__)

# O custo estimado que o botão mostra antes do clique, no Sonnet: a Prova por
# Conta concluída que ela refaz e a recomendação por Tema. Medido em produção
# em novembro de 2026 (Prova US$ 0,59 e Auditor US$ 0,08 por chamada no Opus,
# que custa o dobro).
CUSTO_POR_CONTA_DA_PROVA_USD = 0.30
CUSTO_POR_RECOMENDACAO_USD = 0.04

# Um pedido por vez: o segundo clique, enquanto o primeiro roda, não dispara
# outra rodada sobre os mesmos Temas.
_em_andamento = threading.Lock()

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


def _sem_recomendacao(supabase) -> list[dict[str, Any]]:
    return ler_tudo(
        lambda: (
            supabase.table("cm_validacao_tema")
            .select("id, tipo, operadora_id, regra_codigo")
            .eq("estado", ABERTO)
            .is_("recomendado_em", "null")
            .order("id")
        ),
        rotulo="temas sem recomendação",
    )


def _tem_prova(tema: dict[str, Any]) -> bool:
    return tema["tipo"] == REGRA_PENDENTE and bool(tema.get("operadora_id")) and bool(tema.get("regra_codigo"))


def reservar() -> bool:
    """Reserva o pedido; falso quando outro já está rodando."""
    return _em_andamento.acquire(blocking=False)


def liberar() -> None:
    _em_andamento.release()


def pedido_de_recomendacao(supabase) -> dict[str, Any]:
    """O que o botão mostra antes do clique: os Temas abertos sem
    recomendação, quantos levam a Prova da regra, o custo estimado e se já há
    um pedido rodando. Não chama a IA."""
    temas = _sem_recomendacao(supabase)
    provas = [t for t in temas if _tem_prova(t)]
    contas: dict[str, int] = {}
    for tema in provas:
        if tema["operadora_id"] not in contas:
            contas[tema["operadora_id"]] = len(_ultimas_concluidas(supabase, tema["operadora_id"]))
    custo = (
        sum(contas[t["operadora_id"]] for t in provas) * CUSTO_POR_CONTA_DA_PROVA_USD
        + len(temas) * CUSTO_POR_RECOMENDACAO_USD
    )
    return {
        "temas": len(temas),
        "provas": len(provas),
        "custo_estimado_usd": round(custo, 2),
        "em_andamento": _em_andamento.locked(),
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


def _recomendar(supabase, cartao: dict[str, Any], tema: dict[str, Any], modelo: str) -> bool:
    operadora_id = tema.get("operadora_id")
    prova = None
    if _tem_prova(tema):
        prova = provar_pendente(supabase, operadora_id, tema["regra_codigo"], modelo=modelo)
    memoria = gerar_texto_memoria(supabase, operadora_id) if operadora_id else "(o tema não é de uma operadora só)"
    resposta = ia.recomendar_tema(memoria, _texto_do_tema(cartao, prova), supabase=supabase, modelo=modelo)
    cabe = _cabe(tema, resposta)
    if not cabe:
        # Fica sem recomendação, e marcado: a pessoa decide pelo cartão, e o
        # próximo pedido não pergunta de novo.
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


def recomendar_abertos(supabase) -> int:
    """O Auditor decide todos os Temas abertos ainda sem recomendação, no
    modelo da Validação. Devolve quantos ganharam recomendação. O Tema que
    falhar (IA fora, prova sem memória) fica para o próximo pedido."""
    modelo = settings.cm_ia_modelo_validacao
    cartoes = fila_de_validacao(supabase)["temas"]
    sem = {t["id"] for t in _sem_recomendacao(supabase)}
    a_fazer = [c for c in cartoes if c["id"] in sem]
    temas = {t["id"]: t for t in _em_lotes(supabase, "cm_validacao_tema", "id", [c["id"] for c in a_fazer], "temas")}
    recomendados = 0
    for cartao in a_fazer:
        try:
            recomendados += _recomendar(supabase, cartao, temas[cartao["id"]], modelo)
        except Exception as erro:
            logger.error("[ContasMedicas] Auditor não recomendou o tema %s: %s", cartao["id"], type(erro).__name__)
    return recomendados


def recomendar_e_liberar(supabase) -> None:
    """O pedido do botão, em segundo plano: recomenda e solta a reserva, dê
    certo ou não. Na falha, só o tipo do erro no log."""
    try:
        recomendados = recomendar_abertos(supabase)
        logger.info("[ContasMedicas] Auditor recomendou %s tema(s) a pedido", recomendados)
    except Exception as erro:
        logger.error("[ContasMedicas] Pedido de recomendação falhou: %s", type(erro).__name__)
    finally:
        liberar()


_RECUSAS = (
    DecisaoRecusadaError,
    TemaNaoEncontradoError,
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)


# A recomendação gravada não é mais a que a tela mostrou: uma observação nova
# apagou a antiga e um pedido novo gravou outra. Ninguém viu esta, então o lote não
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
