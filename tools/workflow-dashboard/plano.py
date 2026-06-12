"""Plano vivo — transforma a coleção de issues no plano de execução do painel.

Função pura: issues (no shape do collect.py) entram, estrutura do Plano sai.
Uma "leva" por PRD aberto: ondas topológicas do "Bloqueada por", estado por
fatia, tempo típico medido do histórico e caminho crítico.
"""

from __future__ import annotations

import re
from datetime import datetime
from statistics import median

TAMANHOS = ("P", "M", "G")
MIN_AMOSTRAS_BUCKET = 3


def montar_plano(issues: list[dict]) -> dict:
    por_numero = {i["number"]: i for i in issues}
    tempos = _tempos_tipicos(issues)
    levas = []
    prds = [i for i in issues if i.get("is_prd") and i["state"] == "OPEN"]
    for prd in sorted(prds, key=lambda p: -p["number"]):
        fatias = [por_numero[n] for n in prd.get("children", []) if n in por_numero]
        levas.append(_montar_leva(prd, fatias, tempos))
    return {"levas": levas, "tempos_tipicos": tempos}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _lead_horas(f: dict) -> float | None:
    """Lead time em horas: claim → fechamento; sem claim identificável, abertura → fechamento."""
    fim = _parse_dt(f.get("closed_at"))
    inicio = _parse_dt(f.get("claimed_at")) or _parse_dt(f.get("created_at"))
    if not fim or not inicio or fim <= inicio:
        return None
    return (fim - inicio).total_seconds() / 3600


def bloqueios_do_corpo(body: str) -> list[int]:
    """Números das issues bloqueadoras declaradas no corpo.

    Cobre os dois formatos do pipeline: a seção "## Bloqueada por" com bullets
    nas linhas seguintes e a forma inline "Bloqueada por: #X".
    """
    nums: set[int] = set()
    m = re.search(r"(?ims)^#+\s*Bloqueada por\s*$(.*?)(?=^#|\Z)", body or "")
    if m:
        nums |= {int(n) for n in re.findall(r"#(\d+)", m.group(1))}
    for line in (body or "").splitlines():
        if re.search(r"[Bb]loqueada por\b[^\n]*#", line):
            nums |= {int(n) for n in re.findall(r"#(\d+)", line)}
    return sorted(nums)


def _explicacao(f: dict) -> str | None:
    """1 linha não-técnica do card: o "O que muda:" do bloco Para o diretor."""
    m = re.search(r"\*\*O que muda:\*\*\s*(.+)", f.get("body") or "")
    return m.group(1).strip() if m else None


def _tamanho(f: dict) -> str | None:
    for label in f.get("labels", []):
        if label.startswith("fatia:") and label[6:] in TAMANHOS:
            return label[6:]
    return None


def _tempos_tipicos(issues: list[dict]) -> dict:
    """Medianas de lead time real — por bucket fatia:P/M/G e geral (fatias fechadas)."""
    fechadas = [i for i in issues if i["state"] != "OPEN" and not i.get("is_prd")]
    geral = sorted(filter(None, (_lead_horas(f) for f in fechadas)))
    tempos: dict = {"geral": {"horas": round(median(geral), 1), "amostras": len(geral)} if geral else None}
    for t in TAMANHOS:
        leads = sorted(filter(None, (_lead_horas(f) for f in fechadas if _tamanho(f) == t)))
        tempos[t] = {"horas": round(median(leads), 1), "amostras": len(leads)} if leads else None
    return tempos


def _tempo_tipico(f: dict, tempos: dict) -> dict | None:
    """Tempo típico da fatia: bucket do tamanho com amostra suficiente, senão mediana geral."""
    bucket = tempos.get(_tamanho(f) or "")
    if bucket and bucket["amostras"] >= MIN_AMOSTRAS_BUCKET:
        return {"horas": bucket["horas"], "fonte": "bucket", "amostras": bucket["amostras"]}
    if tempos.get("geral"):
        return {"horas": tempos["geral"]["horas"], "fonte": "geral", "amostras": tempos["geral"]["amostras"]}
    return None


def _montar_leva(prd: dict, fatias: list[dict], tempos: dict) -> dict:
    abertas = {f["number"]: f for f in fatias if f["state"] == "OPEN"}
    ondas, alocadas, avisos = [], set(), []
    while len(alocadas) < len(abertas):
        camada = [
            f
            for n, f in sorted(abertas.items())
            if n not in alocadas and all(b in alocadas or b not in abertas for b in f["blocked_by"])
        ]
        if not camada:
            # Ciclo de "Bloqueada por": ninguém destrava ninguém. Degrada para
            # uma camada residual com tudo que sobrou — o painel nunca esconde fatia.
            residuo = [f for n, f in sorted(abertas.items()) if n not in alocadas]
            nums = ", ".join(f"#{f['number']}" for f in residuo)
            avisos.append(f"Ciclo de dependência entre {nums} — ondas a partir daqui são aproximadas.")
            camada = residuo
        ondas.append([_fatia_resumo(f, abertas, tempos) for f in camada])
        alocadas |= {f["number"] for f in camada}
    concluidas = [_fatia_resumo(f, abertas, tempos) for f in fatias if f["state"] != "OPEN"]
    return {
        "prd": {"number": prd["number"], "title": prd["title"], "url": prd["url"]},
        "ondas": ondas,
        "concluidas": concluidas,
        "avisos": avisos,
        "caminho_critico_horas": _caminho_critico(abertas, tempos),
    }


def _caminho_critico(abertas: dict, tempos: dict) -> float | None:
    """Maior soma de tempo típico ao longo do DAG de "Bloqueada por" das abertas."""
    memo: dict[int, float | None] = {}

    def custo(n: int, trilha: frozenset = frozenset()) -> float | None:
        if n in trilha:  # ciclo — esse caminho não soma
            return None
        if n not in memo:
            t = _tempo_tipico(abertas[n], tempos)
            if t is None:
                memo[n] = None
            else:
                antecessores = [custo(b, trilha | {n}) for b in abertas[n]["blocked_by"] if b in abertas]
                if any(c is None for c in antecessores):
                    memo[n] = None
                else:
                    memo[n] = t["horas"] + max(antecessores, default=0.0)
        return memo[n]

    custos = [custo(n) for n in abertas]
    if not custos or any(c is None for c in custos):
        return None
    return round(max(custos), 1)


def _fatia_resumo(f: dict, abertas: dict, tempos: dict) -> dict:
    bloqueada_por = [b for b in f["blocked_by"] if b in abertas]
    if f["state"] != "OPEN":
        estado = "concluida"
    elif "in-progress" in f["labels"] or f["assignees"]:
        estado = "em_andamento"
    elif bloqueada_por:
        estado = "bloqueada"
    else:
        estado = "pronta"
    return {
        "number": f["number"],
        "title": f["title"],
        "url": f["url"],
        "estado": estado,
        "bloqueada_por": bloqueada_por,
        "tamanho": _tamanho(f),
        "tempo_tipico": _tempo_tipico(f, tempos),
        "explicacao": _explicacao(f),
    }
