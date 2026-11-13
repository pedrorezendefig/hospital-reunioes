"""Avaliação do QR da Ouvidoria (issue #1622, ADR 0086).

O cartaz abre uma nota de 1 a 5, com os motivos e um comentário opcionais. A
avaliação é dado de gestão, não caso: não tem protocolo, prazo nem fila, e não
guarda nada de quem avaliou (sem IP, sem aparelho, sem contato). Quem pede
retorno segue para a Manifestação guiada, e o caso fica ligado à avaliação,
menos quando a pessoa escolhe o anonimato (decisão 3).
"""

from __future__ import annotations

import datetime as dt
import logging

from postgrest.exceptions import APIError

from app.services import ouvidoria_pontos
from app.services.ouvidoria_taxonomia import CATEGORIA_PENDENTE, SETOR_PENDENTE, nasce_sigilosa
from app.services.paginacao import ler_tudo
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

TABELA = "ouvidoria_avaliacoes"

# Os oito motivos da tela N2 (seção 4.1 da especificação da Diretoria), na
# ordem da tela. A lista vive aqui e no CHECK da migration 140, e um teste
# confere que as duas batem.
MOTIVOS: tuple[str, ...] = (
    "atencao_equipe",
    "tempo_espera",
    "informacao_recebida",
    "limpeza",
    "conforto",
    "atendimento_medico",
    "atendimento_enfermagem",
    "recepcao",
)

TAMANHO_DO_COMENTARIO = 500

# A nota que pergunta se a pessoa quer retorno (tela N3): de 1 a 3. A 4 e a 5
# oferecem o elogio, que não é pedido de retorno.
NOTA_QUE_PERGUNTA_RETORNO = 3


def gravar(
    supabase,
    ponto: dict,
    nota: int,
    motivos: list[str],
    comentario: str | None,
    *,
    convite_google: bool = False,
) -> dict | None:
    """Grava a avaliação de um cartaz ativo e devolve a linha, ou None se o
    banco recusou. Só o ponto, a nota, os motivos, o comentário e se o convite
    ao Google foi mostrado (issue #1625): nada que identifique quem avaliou
    entra aqui, nem por engano de quem chama."""
    linha = {
        "ponto_id": ponto["id"],
        "canal": "qr",
        "nota": nota,
        "motivos": motivos,
        "comentario": comentario,
        "convite_google_exibido": convite_google,
    }
    result = supabase.table(TABELA).insert(linha).execute()
    return result.data[0] if result.data else None


def para_ligar(supabase, avaliacao_id: str | None, cartaz: dict | None) -> dict | None:
    """A avaliação que o caso novo pode carregar, ou None.

    Só a nota do mesmo cartaz, e só enquanto nenhum caso a carrega: o id solto
    vindo da página não pendura o caso na avaliação de outro lugar, nem liga
    dois casos à mesma nota. Quem chama já descartou o anônimo (ADR 0086,
    decisão 3). Falha de leitura vira None: perder a ligação é ruim, perder a
    manifestação é pior."""
    if not avaliacao_id or not cartaz:
        return None
    try:
        achadas = supabase.table(TABELA).select("id, ponto_id, nota").eq("id", avaliacao_id).execute().data or []
        if not achadas or achadas[0].get("ponto_id") != cartaz.get("id"):
            return None
        ja_ligada = supabase.table("ouvidoria_protocolos").select("id").eq("avaliacao_id", avaliacao_id).execute().data
    except Exception:
        logger.warning("[Ouvidoria] Falha ao conferir a avaliação do caso; o caso entra sem a ligação")
        return None
    return None if ja_ligada else achadas[0]


def marcar_retorno(supabase, avaliacao: dict) -> None:
    """Marca o pedido de retorno na nota de 1 a 3 que virou caso. A 4 e a 5
    seguem para o elogio, que não é pedido de retorno. Falha aqui não desfaz o
    caso, que já tem protocolo."""
    if avaliacao.get("nota", 0) > NOTA_QUE_PERGUNTA_RETORNO:
        return
    try:
        supabase.table(TABELA).update({"pediu_retorno": True}).eq("id", avaliacao["id"]).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao marcar o pedido de retorno da avaliação")


# ---------------------------------------------------------------------------
# A aba Avaliações (issue #1626, seção 4.5 da especificação da Diretoria)
# ---------------------------------------------------------------------------

# Os filtros de período da aba, em dias inteiros até hoje (no fuso do
# hospital). "tudo" não tem começo: é o que o contador Para revisar do Painel
# abre, porque uma marca antiga sem desfecho continua esperando alguém.
PERIODOS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "365d": 365, "tudo": None}
PERIODO_PADRAO = "30d"

# Os turnos pela hora local da avaliação. Os mesmos quatro nomes do período da
# Manifestação guiada; a hora de corte é desta aba.
TURNOS: tuple[tuple[str, str, int, int], ...] = (
    ("manha", "Manhã", 6, 12),
    ("tarde", "Tarde", 12, 18),
    ("noite", "Noite", 18, 24),
    ("madrugada", "Madrugada", 0, 6),
)

DIAS_DA_SEMANA: tuple[tuple[str, str], ...] = (
    ("seg", "Segunda"),
    ("ter", "Terça"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sábado"),
    ("dom", "Domingo"),
)

# O cartaz apagado do cadastro (a FK solta o ponto). Ponto se aposenta e não
# se apaga (ADR 0036), então isto é quase só defesa.
NOME_SEM_CARTAZ = "Cartaz removido"


def intervalo(periodo: str, hoje: dt.date) -> tuple[dt.date | None, dt.date]:
    """O primeiro e o último dia do período, inclusive. Sem começo em "tudo"."""
    dias = PERIODOS[periodo]
    return (None if dias is None else hoje - dt.timedelta(days=dias - 1)), hoje


def _instante(valor) -> dt.datetime:
    return valor if isinstance(valor, dt.datetime) else dt.datetime.fromisoformat(str(valor))


def _limites_utc(inicio: dt.date | None, fim: dt.date, fuso: dt.tzinfo) -> tuple[str | None, str]:
    """Os dias inteiros no fuso do hospital, como instantes UTC: o começo do
    primeiro dia e o começo do dia seguinte ao último (exclusivo)."""
    comeco = None if inicio is None else dt.datetime.combine(inicio, dt.time.min, tzinfo=fuso)
    depois = dt.datetime.combine(fim + dt.timedelta(days=1), dt.time.min, tzinfo=fuso)
    return (comeco.astimezone(dt.UTC).isoformat() if comeco else None), depois.astimezone(dt.UTC).isoformat()


def _media(notas: list[int]) -> float | None:
    return round(sum(notas) / len(notas), 2) if notas else None


def _fracao(parte: int, total: int) -> float | None:
    return round(parte / total, 4) if total else None


def _turno(hora: int) -> str:
    return next(chave for chave, _r, de, ate in TURNOS if de <= hora < ate)


def numeros(linhas: list[dict], pontos: list[dict], inicio: dt.date | None, fim: dt.date, fuso: dt.tzinfo) -> dict:
    """Os indicadores e os gráficos da aba sobre as avaliações do período.

    `linhas` já vêm recortadas no período. A semana começa na segunda, e a
    evolução semanal mostra também as semanas sem nota, para o buraco aparecer
    no gráfico em vez de sumir."""
    notas = [int(linha["nota"]) for linha in linhas]
    volume = len(notas)
    indicadores = {
        "volume": volume,
        "nota_media": _media(notas),
        "pct_4_e_5": _fracao(sum(1 for nota in notas if nota >= 4), volume),
        "pct_pediu_retorno": _fracao(sum(1 for linha in linhas if linha.get("pediu_retorno")), volume),
    }

    nome_do_ponto = {ponto["id"]: ouvidoria_pontos.nome_exibido(ponto) for ponto in pontos}
    por_ponto: dict[str | None, list[int]] = {}
    por_turno: dict[str, list[int]] = {chave: [] for chave, *_ in TURNOS}
    por_dia: dict[int, list[int]] = {i: [] for i in range(7)}
    por_semana: dict[dt.date, list[int]] = {}
    for linha in linhas:
        nota = int(linha["nota"])
        local = _instante(linha["criada_em"]).astimezone(fuso)
        por_ponto.setdefault(linha.get("ponto_id"), []).append(nota)
        por_turno[_turno(local.hour)].append(nota)
        por_dia[local.weekday()].append(nota)
        por_semana.setdefault(local.date() - dt.timedelta(days=local.weekday()), []).append(nota)

    semanas: list[dt.date] = []
    if inicio is not None or por_semana:
        primeira = inicio - dt.timedelta(days=inicio.weekday()) if inicio else min(por_semana)
        ultima = fim - dt.timedelta(days=fim.weekday())
        semana = primeira
        while semana <= ultima:
            semanas.append(semana)
            semana += dt.timedelta(days=7)

    return {
        "indicadores": indicadores,
        "por_ponto": sorted(
            (
                {
                    "ponto_id": ponto_id,
                    "nome": nome_do_ponto.get(ponto_id, NOME_SEM_CARTAZ),
                    "nota_media": _media(lista),
                    "volume": len(lista),
                }
                for ponto_id, lista in por_ponto.items()
            ),
            key=lambda p: p["nome"],
        ),
        "por_turno": [
            {"turno": chave, "rotulo": rotulo, "nota_media": _media(por_turno[chave]), "volume": len(por_turno[chave])}
            for chave, rotulo, *_ in TURNOS
        ],
        "por_dia_da_semana": [
            {"dia": chave, "rotulo": rotulo, "nota_media": _media(por_dia[i]), "volume": len(por_dia[i])}
            for i, (chave, rotulo) in enumerate(DIAS_DA_SEMANA)
        ],
        "por_semana": [
            {
                "semana": semana.isoformat(),
                "nota_media": _media(por_semana.get(semana, [])),
                "volume": len(por_semana.get(semana, [])),
            }
            for semana in semanas
        ],
    }


def ler_numeros(supabase, periodo: str, hoje: dt.date, fuso: dt.tzinfo) -> dict:
    """Lê as avaliações do período e devolve os números da aba."""
    inicio, fim = intervalo(periodo, hoje)
    desde, ate = _limites_utc(inicio, fim, fuso)

    def consulta():
        query = supabase.table(TABELA).select("id, ponto_id, nota, pediu_retorno, criada_em")
        if desde:
            query = query.gte("criada_em", desde)
        return query.lt("criada_em", ate).order("criada_em").order("id")

    linhas = ler_tudo(consulta, rotulo="números da aba Avaliações")
    return {
        "periodo": periodo,
        "intervalo": {"inicio": inicio.isoformat() if inicio else None, "fim": fim.isoformat()},
        **numeros(linhas, ouvidoria_pontos.listar(supabase), inicio, fim, fuso),
    }


# A lista da aba, em páginas: a mais nova primeiro.
POR_PAGINA = 20

_CAMPOS_DA_LISTA = (
    "id, ponto_id, nota, motivos, comentario, criada_em, pediu_retorno, revisar, revisar_motivo, "
    "revisao_desfecho, revisao_motivo, revisada_em"
)


def para_revisar(linha: dict) -> bool:
    """A marca Para revisar ainda de pé: o agente marcou e ninguém deu
    desfecho. Converter ou arquivar tira a marca; a marca do agente fica como
    histórico."""
    return bool(linha.get("revisar")) and not linha.get("revisao_desfecho")


def contar_para_revisar(supabase) -> int:
    """Quantas avaliações esperam revisão, de qualquer data. É o número do
    filtro da aba e do contador do Painel."""
    result = (
        supabase.table(TABELA)
        .select("id", count="exact")
        .eq("revisar", True)
        .is_("revisao_desfecho", "null")
        .limit(1)
        .execute()
    )
    return int(result.count or 0)


def listar(
    supabase,
    *,
    periodo: str,
    hoje: dt.date,
    fuso: dt.tzinfo,
    ponto_id: str | None = None,
    nota: int | None = None,
    com_comentario: bool = False,
    so_para_revisar: bool = False,
    pagina: int = 1,
) -> dict:
    """Uma página da lista da aba, com os filtros da seção 4.5: ponto, nota,
    período, só com comentário e Para revisar."""
    inicio, fim = intervalo(periodo, hoje)
    desde, ate = _limites_utc(inicio, fim, fuso)
    query = supabase.table(TABELA).select(_CAMPOS_DA_LISTA, count="exact")
    if desde:
        query = query.gte("criada_em", desde)
    query = query.lt("criada_em", ate)
    if ponto_id:
        query = query.eq("ponto_id", ponto_id)
    if nota is not None:
        query = query.eq("nota", nota)
    if com_comentario:
        query = query.not_.is_("comentario", "null")
    if so_para_revisar:
        query = query.eq("revisar", True).is_("revisao_desfecho", "null")
    primeira = (pagina - 1) * POR_PAGINA
    result = (
        query.order("criada_em", desc=True).order("id", desc=True).range(primeira, primeira + POR_PAGINA - 1).execute()
    )
    linhas = result.data or []

    nome_do_ponto = {ponto["id"]: ouvidoria_pontos.nome_exibido(ponto) for ponto in ouvidoria_pontos.listar(supabase)}
    casos: dict[str, dict] = {}
    if linhas:
        ligados = (
            supabase.table("ouvidoria_protocolos")
            .select("id, protocolo, avaliacao_id")
            .in_("avaliacao_id", [linha["id"] for linha in linhas])
            .execute()
            .data
            or []
        )
        casos = {caso["avaliacao_id"]: {"id": caso["id"], "protocolo": caso.get("protocolo")} for caso in ligados}

    return {
        "itens": [
            {
                **linha,
                "ponto_nome": nome_do_ponto.get(linha.get("ponto_id"), NOME_SEM_CARTAZ),
                "para_revisar": para_revisar(linha),
                "caso": casos.get(linha["id"]),
            }
            for linha in linhas
        ],
        "total": int(result.count or 0),
        "pagina": pagina,
        "por_pagina": POR_PAGINA,
        "para_revisar_total": contar_para_revisar(supabase),
    }


class AvaliacaoNaoEncontradaError(LookupError):
    """A avaliação não existe (ou o id nem tem forma de id)."""


class AvaliacaoRecusadaError(ValueError):
    """O ato não vale para esta avaliação; a mensagem diz por quê."""


def _carregar(supabase, avaliacao_id: str) -> dict:
    try:
        achadas = supabase.table(TABELA).select("*").eq("id", avaliacao_id).execute().data or []
    except APIError as exc:
        if getattr(exc, "code", None) == "22P02":
            raise AvaliacaoNaoEncontradaError(avaliacao_id) from None
        raise
    if not achadas:
        raise AvaliacaoNaoEncontradaError(avaliacao_id)
    return achadas[0]


# O resumo do caso é vitrine (a fila mostra o assunto do agente, e o resumo
# quando ele falta). O mesmo teto do canal aberto.
_LIMITE_DO_RESUMO = 200

JA_VIROU_CASO = "Esta avaliação já virou caso."
SEM_COMENTARIO = "Avaliação sem comentário não vira caso: não há relato para apurar."
NAO_ESTA_PARA_REVISAR = "Esta avaliação não está marcada para revisar."

# A anotação do caso que nasce de uma avaliação: a nota não guarda contato, e
# o ouvidor que abre o caso precisa saber por que não há a quem responder.
ANOTACAO_DA_CONVERSAO = (
    "Caso aberto pela Ouvidoria a partir de uma avaliação do QR (nota {nota} de 5). "
    "Quem avaliou não deixou contato: o caso não tem manifestante para retorno."
)


def _resumir(texto: str) -> str:
    if len(texto) <= _LIMITE_DO_RESUMO:
        return texto
    corte = texto[: _LIMITE_DO_RESUMO - 3]
    espaco = corte.rfind(" ")
    return f"{corte[:espaco] if espaco > 0 else corte}..."


def converter(supabase, avaliacao_id: str, me: dict, agora: dt.datetime, fuso: dt.tzinfo) -> dict:
    """Converte a avaliação em caso (ADR 0086, decisão 4) e devolve a linha do
    caso.

    O caso nasce com canal `qr`, o setor e o ponto do cartaz, a ligação com a
    avaliação, o comentário como relato, tipo vazio (logo sigiloso até a
    classificação) e T0 igual à hora da avaliação. A avaliação não guarda
    contato, então o caso nasce sem manifestante para retorno, e a abertura
    da trilha diz isso. A avaliação ganha o desfecho `convertida`."""
    avaliacao = _carregar(supabase, avaliacao_id)
    comentario = sanitizar_travessao(avaliacao.get("comentario") or "").strip()
    if not comentario:
        raise AvaliacaoRecusadaError(SEM_COMENTARIO)
    if avaliacao.get("revisao_desfecho") == "convertida":
        raise AvaliacaoRecusadaError(JA_VIROU_CASO)
    if supabase.table("ouvidoria_protocolos").select("id").eq("avaliacao_id", avaliacao["id"]).execute().data:
        raise AvaliacaoRecusadaError(JA_VIROU_CASO)

    cartaz = ouvidoria_pontos.por_id(supabase, avaliacao["ponto_id"]) if avaliacao.get("ponto_id") else None
    t0 = _instante(avaliacao["criada_em"])
    linha = {
        "categoria": CATEGORIA_PENDENTE,
        "setor": SETOR_PENDENTE,
        "resumo": _resumir(comentario),
        "relato_integral": comentario,
        "sigilo_reforcado": nasce_sigilosa(None),
        "anonimo": False,
        # Nada a completar: a avaliação nunca teve contato.
        "dados_incompletos": False,
        "canal": "qr",
        "canal_setor": cartaz["setor"] if cartaz else None,
        "canal_ponto": cartaz["ponto"] if cartaz else None,
        "avaliacao_id": avaliacao["id"],
        "contato_em": t0.isoformat(),
        "data_abertura": t0.astimezone(fuso).date().isoformat(),
        "registrado_por": me["id"],
    }
    try:
        caso = supabase.table("ouvidoria_protocolos").insert(linha).execute().data[0]
    except APIError as exc:
        # O índice único da ligação: outro clique converteu primeiro.
        if getattr(exc, "code", None) == "23505":
            raise AvaliacaoRecusadaError(JA_VIROU_CASO) from None
        raise

    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": caso["id"],
                "estado_anterior": None,
                "estado_novo": caso.get("status") or "em_classificacao",
                "autor_id": me["id"],
                "autor_nome": me.get("nome_completo") or me["id"],
                "observacao": ANOTACAO_DA_CONVERSAO.format(nota=avaliacao["nota"]),
            }
        ).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao abrir a trilha do caso %s convertido da avaliação", caso.get("id"))
    try:
        supabase.table(TABELA).update(
            {"revisao_desfecho": "convertida", "revisada_por": me["id"], "revisada_em": agora.isoformat()}
        ).eq("id", avaliacao["id"]).execute()
    except Exception:
        # O caso já existe e carrega a ligação, que a lista mostra; perder o
        # desfecho deixa a marca de pé até alguém arquivar.
        logger.error("[Ouvidoria] Falha ao gravar o desfecho da avaliação convertida no caso %s", caso.get("id"))
    return caso


def arquivar_revisao(supabase, avaliacao_id: str, motivo: str, me: dict, agora: dt.datetime) -> dict:
    """Tira a marca Para revisar com um motivo curto, sem abrir caso."""
    avaliacao = _carregar(supabase, avaliacao_id)
    if not para_revisar(avaliacao):
        raise AvaliacaoRecusadaError(NAO_ESTA_PARA_REVISAR)
    desfecho = {
        "revisao_desfecho": "arquivada",
        "revisao_motivo": motivo,
        "revisada_por": me["id"],
        "revisada_em": agora.isoformat(),
    }
    # O filtro do desfecho vazio segura dois cliques: o segundo não reescreve
    # o motivo do primeiro.
    feitas = (
        supabase.table(TABELA).update(desfecho).eq("id", avaliacao["id"]).is_("revisao_desfecho", "null").execute().data
    )
    if not feitas:
        raise AvaliacaoRecusadaError(NAO_ESTA_PARA_REVISAR)
    return {"id": avaliacao["id"], **desfecho, "para_revisar": False}
