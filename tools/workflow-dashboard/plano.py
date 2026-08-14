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
LABELS_DESCARTE = {"wontfix", "duplicate", "invalid"}
# Fila humana (aba Pendências): não é fatia de agente, fica fora das ondas.
LABEL_PENDENCIA_HUMANA = "ready-for-human"


def montar_plano(issues: list[dict]) -> dict:
    # A fila humana fica TODA fora do Plano (ondas, entregues e medianas de
    # lead time): pendência espera o humano por dias e envenenaria o tempo
    # típico das fatias de agente. A casa dela é a aba Pendências.
    issues = [i for i in issues if LABEL_PENDENCIA_HUMANA not in i["labels"]]
    por_numero = {i["number"]: i for i in issues}
    abertas_global = {i["number"] for i in issues if i["state"] == "OPEN"}
    tempos = _tempos_tipicos(issues)
    levas, em_levas = [], set()
    prds = [i for i in issues if i.get("is_prd") and i["state"] == "OPEN"]
    for prd in sorted(prds, key=lambda p: -p["number"]):
        fatias = [por_numero[n] for n in prd.get("children", []) if n in por_numero]
        em_levas |= {f["number"] for f in fatias}
        levas.append(_montar_leva(prd, fatias, tempos, abertas_global))
    # Avulsas: abertas fora de qualquer leva (sem PRD aberto) — também são plano.
    soltas = {
        i["number"]: i
        for i in issues
        if i["state"] == "OPEN" and not i.get("is_prd") and i["number"] not in em_levas
    }
    ondas_avulsas, avisos_avulsas = _ondas(soltas, tempos, abertas_global)
    return {
        "levas": levas,
        "avulsas": {"ondas": ondas_avulsas, "avisos": avisos_avulsas},
        "tempos_tipicos": tempos,
    }


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
    m = re.search(r"(?ims)^#+\s*Bloqueada por:?\s*$(.*?)(?=^#|\Z)", body or "")
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
    fechadas = [
        i
        for i in issues
        if i["state"] != "OPEN" and not i.get("is_prd") and not (set(i["labels"]) & LABELS_DESCARTE)
    ]
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


def _ondas(abertas: dict, tempos: dict, abertas_global: set[int]) -> tuple[list, list]:
    """Ondas topológicas de um conjunto de abertas (fatias de uma leva ou avulsas).

    A topologia usa só as issues do conjunto; bloqueio externo aberto não
    sequencia a onda, mas mantém a issue "bloqueada" (ver _fatia_resumo).
    """
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
        resumos = [_fatia_resumo(f, abertas_global, tempos) for f in camada]
        for r in resumos:
            r["copiaveis"] = _copiaveis(r["number"], serial=len(camada) == 1)
        ondas.append(resumos)
        alocadas |= {f["number"] for f in camada}
    return ondas, avisos


def _montar_leva(prd: dict, fatias: list[dict], tempos: dict, abertas_global: set[int]) -> dict:
    abertas = {f["number"]: f for f in fatias if f["state"] == "OPEN"}
    ondas, avisos = _ondas(abertas, tempos, abertas_global)
    concluidas = [_fatia_resumo(f, abertas_global, tempos) for f in fatias if f["state"] != "OPEN"]
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


def _copiaveis(n: int, serial: bool) -> dict:
    """Comandos prontos do card — o front só copia, nunca monta.

    Onda com várias fatias pede 1 worktree por issue (sessões em paralelo);
    onda serial trabalha na árvore principal mesmo.
    """
    slash = f"/pegar-issue {n}"
    if serial:
        terminal = f'claude "{slash}"'
    else:
        # cp do .env: o worktree nasce sem ele (gitignored) e o pytest quebra sem isso.
        terminal = (
            f"git worktree add ../hospital-issue-{n}\n"
            f"cp hospital-reunioes/.env ../hospital-issue-{n}/hospital-reunioes/.env\n"
            f"cd ../hospital-issue-{n}\n"
            f'claude "{slash}"'
        )
    return {"terminal": terminal, "slash": slash}


def _fatia_resumo(f: dict, abertas_global: set[int], tempos: dict) -> dict:
    bloqueada_por = [b for b in f["blocked_by"] if b in abertas_global]
    if f["state"] != "OPEN":
        estado = "concluida"
    elif "in-progress" in f["labels"] or f["assignees"]:
        estado = "em_andamento"
    elif bloqueada_por:
        estado = "bloqueada"
    elif "ready-for-agent" in f["labels"]:
        estado = "pronta"
    else:
        # Destravada mas fora da fila: o claim do /pegar-issue exige a label
        # ready-for-agent — sem ela o prompt copiado seria recusado.
        estado = "aguardando_triage"
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
