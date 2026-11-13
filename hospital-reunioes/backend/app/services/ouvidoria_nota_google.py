"""A nota do Google buscada toda semana (issue #1619, PRD #1527, ADR 0089).

Um job sem IA lê a nota (`rating`) e o total de avaliações (`userRatingCount`)
do perfil do hospital pela Places API (New) e grava no diário de Nota externa
(`ouvidoria_nota_externa.py`), com a marca `origem = automatica`. O Place ID
mora na configuração da Ouvidoria; a chave da API é segredo de ambiente
(`GOOGLE_PLACES_API_KEY`, na tela do Coolify). Sem a chave, o job não chama
nada e a Central diz que a nota não está sendo medida.

Daqui sai também o resumo do mês que a Central mostra: a nota, as avaliações
novas do mês e a tendência. A API não entrega a avaliação de cada mês, então
"avaliações novas do mês" é a diferença do total entre a primeira e a última
leitura do mês, e a tela diz isso (ADR 0089, decisão 3).
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from app.services.ouvidoria_nota_externa import ESCALA, TABELA

logger = logging.getLogger(__name__)

URL_DA_PLACES_API = "https://places.googleapis.com/v1/places/{place_id}"
CAMPOS_DA_PLACES_API = "rating,userRatingCount"

# O job roda todo dia e só busca se a última leitura automática tem mais de uma
# semana: o jobstore do agendador é em memória, e um disparo semanal perdido num
# deploy de segunda-feira esperaria outra semana inteira.
INTERVALO_ENTRE_LEITURAS = dt.timedelta(days=7)


def buscar_e_gravar(supabase, agora: dt.datetime, *, chave: str, cliente: httpx.Client | None = None) -> dict | None:
    """Lê a nota do Google e grava uma linha nova no diário. Devolve a linha
    gravada, ou `None` quando não buscou (sem chave, leitura recente, sem Place
    ID ou o Google falhou). Nunca levanta pela falha do Google: o job registra
    no log e tenta de novo no dia seguinte."""
    if not chave:
        logger.warning("[Ouvidoria] GOOGLE_PLACES_API_KEY ausente: a nota do Google não está sendo medida.")
        return None
    if _leitura_recente(supabase, agora):
        return None
    place_id = _place_id(supabase)
    if not place_id:
        logger.warning("[Ouvidoria] Configuração da Ouvidoria sem Place ID do Google: nota não buscada.")
        return None
    try:
        dados = _ler_do_google(place_id, chave, cliente)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[Ouvidoria] A Places API falhou ao ler a nota do Google (%s).", type(exc).__name__)
        return None
    linha = {
        "fonte": "google",
        "nota": dados["nota"],
        "total_avaliacoes": dados["total"],
        "origem": "automatica",
        "registrada_em": agora.isoformat(),
        "registrada_por": None,
        "registrada_por_nome": "",
    }
    supabase.table(TABELA).insert(linha).execute()
    return linha


def resumo_do_mes(supabase, hoje: dt.date, *, medida: bool) -> dict:
    """O que a Central mostra do Google no mês de `hoje`.

    - `medida`: a chave da API está configurada. Sem ela, nenhum número sai, e
      a tela diz que a nota não está sendo medida.
    - `nota` e `total`: a última leitura (o total só da automática).
    - `avaliacoes_do_mes`: o total da última leitura do mês menos o da primeira.
      Com menos de duas leituras automáticas no mês, nada: a diferença seria
      zero e leria como "ninguém avaliou".
    - `tendencia`: a última nota do mês contra a última do mês anterior, que
      pode ser digitada (o histórico digitado fica, ADR 0089, decisão 2).
    - `leituras_do_mes` e `leituras_mes_anterior`: cada leitura, em ordem, com
      a nota e o total acumulado (nulo na digitada), para o gráfico do mês
      (issue #1699)."""
    vazio = {
        "medida": medida,
        "nota": None,
        "escala": ESCALA["google"],
        "total": None,
        "lida_em": None,
        "avaliacoes_do_mes": None,
        "nota_mes_anterior": None,
        "tendencia": None,
        "leituras_do_mes": [],
        "leituras_mes_anterior": [],
    }
    if not medida:
        return vazio
    inicio_do_mes = hoje.replace(day=1)
    inicio_do_anterior = (inicio_do_mes - dt.timedelta(days=1)).replace(day=1)
    resultado = (
        supabase.table(TABELA)
        .select("nota, total_avaliacoes, origem, registrada_em")
        .eq("fonte", "google")
        .gte("registrada_em", inicio_do_anterior.isoformat())
        .order("registrada_em", desc=False)
        .execute()
    )
    leituras = resultado.data or []
    if not leituras:
        return vazio
    do_mes = [li for li in leituras if str(li["registrada_em"]) >= inicio_do_mes.isoformat()]
    do_anterior = [li for li in leituras if str(li["registrada_em"]) < inicio_do_mes.isoformat()]
    ultima = leituras[-1]
    totais_do_mes = [li["total_avaliacoes"] for li in do_mes if li.get("total_avaliacoes") is not None]
    totais = [li["total_avaliacoes"] for li in leituras if li.get("total_avaliacoes") is not None]
    nota_do_mes = float(do_mes[-1]["nota"]) if do_mes else None
    nota_anterior = float(do_anterior[-1]["nota"]) if do_anterior else None
    return {
        **vazio,
        "nota": float(ultima["nota"]),
        "total": totais[-1] if totais else None,
        "lida_em": ultima["registrada_em"],
        "avaliacoes_do_mes": totais_do_mes[-1] - totais_do_mes[0] if len(totais_do_mes) >= 2 else None,
        "nota_mes_anterior": nota_anterior,
        "tendencia": _tendencia(nota_do_mes, nota_anterior),
        "leituras_do_mes": [_ponto_do_grafico(li) for li in do_mes],
        "leituras_mes_anterior": [_ponto_do_grafico(li) for li in do_anterior],
    }


def _ponto_do_grafico(leitura: dict) -> dict:
    return {
        "lida_em": leitura["registrada_em"],
        "nota": float(leitura["nota"]),
        "total": leitura.get("total_avaliacoes"),
    }


def _tendencia(nota_do_mes: float | None, nota_anterior: float | None) -> str | None:
    if nota_do_mes is None or nota_anterior is None:
        return None
    if nota_do_mes > nota_anterior:
        return "melhorou"
    if nota_do_mes < nota_anterior:
        return "piorou"
    return "igual"


def _leitura_recente(supabase, agora: dt.datetime) -> bool:
    resultado = (
        supabase.table(TABELA)
        .select("registrada_em")
        .eq("fonte", "google")
        .eq("origem", "automatica")
        .gte("registrada_em", (agora - INTERVALO_ENTRE_LEITURAS + dt.timedelta(hours=1)).isoformat())
        .limit(1)
        .execute()
    )
    return bool(resultado.data)


def _place_id(supabase) -> str:
    resultado = supabase.table("ouvidoria_config").select("google_place_id").eq("id", True).limit(1).execute()
    linhas = resultado.data or []
    return str(linhas[0].get("google_place_id") or "") if linhas else ""


def _ler_do_google(place_id: str, chave: str, cliente: httpx.Client | None) -> dict:
    http = cliente or httpx.Client(timeout=15.0)
    with http:
        resposta = http.get(
            URL_DA_PLACES_API.format(place_id=place_id),
            headers={"X-Goog-Api-Key": chave, "X-Goog-FieldMask": CAMPOS_DA_PLACES_API},
        )
    resposta.raise_for_status()
    corpo = resposta.json()
    nota = corpo.get("rating")
    total = corpo.get("userRatingCount")
    if not isinstance(nota, int | float) or not isinstance(total, int):
        raise ValueError("resposta da Places API sem rating ou userRatingCount")
    return {"nota": float(nota), "total": total}
