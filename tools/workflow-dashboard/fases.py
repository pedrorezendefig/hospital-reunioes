"""Fases do Hospital OS: em que pé está cada issue e cada PR (ADR 0062, decisões 4 a 7).

Função pura: issues, PRs, deploys do history.json e branches remotas (no shape
do collect.py) entram; fase por issue, fase por PR, timeline, ondas por PRD e
contagens do funil saem. Nada aqui consulta rede ou disco.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# Régua da issue na ordem do funil (ADR 0062, decisão 4); a precedência fica em _fase_issue.
FASES_ISSUE = ("triagem", "fila", "bloqueada", "em_andamento", "pr_aberto", "mergeada", "em_producao",
               "humana", "encerrada_sem_pr")
# Mesmo valor do SEM_RESP do app.js: o filtro "ninguém assumiu" da aba Issues.
SEM_RESPONSAVEL = "(sem)"
MARCADOR_AUTOMACAO = "<!-- automacao -->"
# Última linha do comentário dos agentes hr-revisor e hr-revisor-seguranca.
_VEREDITO = re.compile(r"(?m)^VEREDITO( SEGURANCA)?:\s*(LIMPO|MUST-FIX)\b")
# Conclusões de check que deixam o CI vermelho (CheckRun e StatusContext).
_FALHAS = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def montar_fases(issues: list[dict], prs: list[dict], deploys: list[dict], branches: list[str],
                 timelines: dict | None = None, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    abertas = {i["number"] for i in issues if i["state"] == "OPEN"}
    producao = _Producao(deploys)
    fases_pr = {p["number"]: _fase_pr(p, producao, agora) for p in prs}
    prs_por_issue: dict[int, list[dict]] = {}
    for p in prs:
        for n in p["closes"]:
            prs_por_issue.setdefault(n, []).append(p)
    fases_issue = {i["number"]: _fase_issue(i, prs_por_issue.get(i["number"], []), abertas, producao,
                                            branches, fases_pr)
                   for i in issues}
    por_numero = {i["number"]: i for i in issues}
    return {
        "issues": fases_issue,
        "prs": fases_pr,
        "timelines": {n: _timeline(por_numero[n], linha, producao, branches)
                      for n, linha in (timelines or {}).items() if n in por_numero},
        "ondas": {i["number"]: _ondas(i, por_numero, abertas) for i in issues if i.get("children")},
        "funil": _funil(issues, fases_issue),
    }


def timeline_da_issue(issue: dict, linha: dict, deploys: list[dict], branches: list[str] = ()) -> list[dict]:
    """Linha do tempo de uma issue (a das fechadas sai sob demanda, uma por vez)."""
    return _timeline(issue, linha, _Producao(deploys), list(branches))


def _timeline(issue: dict, linha: dict, producao: _Producao, branches: list[str]) -> list[dict]:
    """Eventos da issue em ordem (ADR 0062, decisão 6).

    `linha` vem do coletor: eventos da própria issue (designada, fechada,
    reaberta) e os PRs que a fecham, com quantos commits ficaram de CI vermelho
    e os vereditos dos revisores. No empate de horário o PR vem antes da issue
    (o merge é que fecha a issue).
    """
    eventos = [{"tipo": "criada", "em": issue.get("created_at")}]
    prs = _por_data(linha.get("prs") or [])
    houve_tentativa = False
    for p in prs:
        n = p["number"]
        eventos.append({"tipo": "novo_pr" if houve_tentativa else "pr_aberto", "em": p.get("created_at"), "pr": n})
        if p.get("ci_vermelho"):
            eventos.append({"tipo": "ci_vermelho", "em": p.get("ci_vermelho_em"), "pr": n, "vezes": p["ci_vermelho"]})
        for v in p.get("vereditos") or []:
            eventos.append({"tipo": "revisor_comentou", "em": v.get("em"), "pr": n, "lente": v["tipo"],
                            "veredito": v["valor"]})
        if p["state"] == "MERGED":
            eventos.append({"tipo": "mergeado", "em": p.get("merged_at"), "pr": n})
            _, deploy = producao.do_pr({**p, "closes": [issue["number"]]})
            if deploy:
                eventos.append({"tipo": "em_producao", "em": deploy["at"], "pr": n,
                                "versao": deploy.get("app_version")})
        elif p["state"] == "CLOSED":
            eventos.append({"tipo": "pr_fechado", "em": p.get("closed_at"), "pr": n})
            houve_tentativa = True
    eventos += [dict(e) for e in linha.get("eventos") or []]
    datados = sorted((e for e in eventos if _dt(e.get("em"))), key=lambda e: _dt(e["em"]))
    sem_data = [e for e in eventos if not _dt(e.get("em"))]
    branch = _branch_sem_pr(issue["number"], prs, branches)
    if branch:
        sem_data.append({"tipo": "branch", "em": None, "branch": branch})
    return datados + sem_data


def _ondas(prd: dict, por_numero: dict[int, dict], abertas: set[int]) -> list[list[int]]:
    """Colunas do desenho do PRD: fatia vai uma coluna depois da bloqueadora aberta do mesmo PRD.

    Bloqueadora fechada não bloqueia; bloqueio de fora do PRD não cria coluna (a
    fatia fica Bloqueada na régua, mas o desenho só sequencia o próprio PRD).
    """
    fatias = {n for n in prd["children"] if n in por_numero}
    pendentes = dict.fromkeys(sorted(fatias))
    colunas: list[list[int]] = []
    while pendentes:
        coluna = [n for n in pendentes
                  if not any(b in pendentes and b in abertas for b in por_numero[n]["blocked_by"])]
        coluna = coluna or list(pendentes)  # ciclo: o que sobrou vira uma coluna, nada some
        colunas.append(coluna)
        for n in coluna:
            del pendentes[n]
    return colunas


def _funil(issues: list[dict], fases_issue: dict[int, dict]) -> dict:
    """Contagem por fase, no total e por responsável.

    Responsável segue a aba Issues: quem assumiu; sem assignee, quem criou
    (emenda de 05/10 da ADR 0061). SEM_RESPONSAVEL junta as sem assignee.
    """
    total = dict.fromkeys(FASES_ISSUE, 0)
    por_responsavel: dict[str, dict[str, int]] = {}
    for i in issues:
        fase = fases_issue[i["number"]]["fase"]
        total[fase] += 1
        pessoas = list(i["assignees"]) or ([i["author"]] if i.get("author") else [])
        if not i["assignees"]:
            pessoas.append(SEM_RESPONSAVEL)
        for p in pessoas:
            por_responsavel.setdefault(p, dict.fromkeys(FASES_ISSUE, 0))[fase] += 1
    return {"total": total, "por_responsavel": por_responsavel}


def vereditos_dos_comentarios(comentarios: list[dict]) -> list[dict]:
    """Vereditos dos agentes revisores, só de comentário com o marcador de automação."""
    out = []
    for c in comentarios:
        corpo = (c.get("body") or "").lstrip()
        achados = _VEREDITO.findall(corpo) if corpo.startswith(MARCADOR_AUTOMACAO) else []
        if achados:
            seguranca, valor = achados[-1]
            out.append({"tipo": "seguranca" if seguranca else "revisao",
                        "valor": "limpo" if valor == "LIMPO" else "must_fix",
                        "em": c.get("created_at")})
    return out


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class _Producao:
    """Em que deploy do history.json cada PR subiu.

    O rabo escreve os PRs no texto do deploy ("PR #896", "PRs #874 #875 #876");
    número de issue e de PR não colidem no GitHub, então basta o PR ser citado.
    """

    def __init__(self, deploys: list[dict]):
        self.deploys = []
        for d in deploys:
            at = _dt(d.get("at"))
            if d.get("result", "healthy") != "healthy" or not at:
                continue
            texto = " ".join(str(d.get(k) or "") for k in ("subject", "raw_subject", "notes"))
            citados = {int(n) for n in re.findall(r"#(\d+)", texto)} | set(d.get("pr_numbers") or [])
            build = at - timedelta(seconds=d.get("duration_seconds") or 0)  # o build sobe a main deste instante
            self.deploys.append((at, build, d, citados))
        self.deploys.sort(key=lambda t: t[0])

    def do_pr(self, pr: dict) -> tuple[bool, dict | None]:
        """(em produção?, deploy) do PR mergeado, nesta ordem:

        1. o primeiro deploy que cita o PR (ou a issue dele, se o deploy é depois do merge);
        2. merge anterior ao build mais antigo do history.json: está no ar, versão
           desconhecida (o history.json guardou só os 50 últimos deploys até a ADR 0062);
        3. o primeiro deploy cujo build começou depois do merge: PR só de docs e PR de
           registro do rabo não ganham deploy próprio, e todo deploy sobe a main inteira.
        """
        if pr["state"] != "MERGED":
            return False, None
        merge = _dt(pr.get("merged_at"))
        issues = set(pr.get("closes") or [])
        for at, _, d, citados in self.deploys:
            # O /ship antigo citava só a issue ("Objetivos (#820)"); aí o deploy tem que ser depois do merge.
            if pr["number"] in citados or (issues & citados and merge and at >= merge):
                return True, d
        if not merge or not self.deploys:
            return False, None
        if merge < self.deploys[0][1]:
            return True, None
        return next(((True, d) for _, build, d, _ in self.deploys if build > merge), (False, None))


def _estado_ci(checks: list[dict]) -> str:
    if not checks:
        return "sem_ci"
    if any(c.get("status") == "COMPLETED" and c.get("conclusao") in _FALHAS for c in checks):
        return "vermelho"
    if any(c.get("status") != "COMPLETED" for c in checks):
        return "pendente"
    return "verde"


def _veredito(pr: dict) -> tuple[str | None, str | None]:
    """(veredito, quando) da revisão: o último de cada lente vale.

    Review do GitHub conta como a lente de revisão (APPROVED = limpo,
    CHANGES_REQUESTED = must-fix). Must-fix em qualquer lente segura o merge;
    limpo exige a lente de revisão.
    """
    vereditos = list(pr.get("vereditos") or [])
    for r in pr.get("reviews") or []:
        if r.get("estado") in ("APPROVED", "CHANGES_REQUESTED"):
            vereditos.append({"tipo": "revisao", "em": r.get("em"),
                              "valor": "limpo" if r["estado"] == "APPROVED" else "must_fix"})
    ultimo: dict[str, dict] = {}
    for v in sorted(vereditos, key=lambda v: _dt(v.get("em")) or datetime.min.replace(tzinfo=timezone.utc)):
        ultimo[v["tipo"]] = v
    if not ultimo:
        return None, None
    quando = max((v["em"] for v in ultimo.values() if v.get("em")), key=_dt, default=None)
    if any(v["valor"] == "must_fix" for v in ultimo.values()):
        return "must_fix", quando
    if "revisao" in ultimo:
        return "limpo", quando
    return None, None


def _mais_recente(*datas: str | None) -> str | None:
    validas = [d for d in datas if _dt(d)]
    return max(validas, key=_dt) if validas else None


def _mais_antiga(*datas: str | None) -> str | None:
    validas = [d for d in datas if _dt(d)]
    return min(validas, key=_dt) if validas else None


def _fase_pr(pr: dict, producao: _Producao, agora: datetime) -> dict:
    """Coluna do PR no quadro (ADR 0062, decisão 7) e desde quando ele está nela."""
    checks = pr.get("checks") or []
    ci = _estado_ci(checks) if pr["state"] == "OPEN" else None
    veredito, quando = _veredito(pr)
    versao = None
    if pr["state"] == "MERGED":
        no_ar, deploy = producao.do_pr(pr)
        if no_ar:
            fase, desde = "em_producao", deploy["at"] if deploy else None
            versao = deploy.get("app_version") if deploy else None
        else:
            fase, desde = "mergeado_sem_deploy", pr.get("merged_at")
    elif pr["state"] != "OPEN":
        fase, desde = "fechado_sem_merge", pr.get("closed_at")
    elif ci == "vermelho":
        fase = "ci_vermelho"
        desde = _mais_antiga(*(c.get("fim") for c in checks if c.get("conclusao") in _FALHAS))
    elif ci in ("sem_ci", "pendente"):
        fase, desde = "aberto_sem_ci", _mais_antiga(*(c.get("inicio") for c in checks)) or pr.get("created_at")
    else:
        fim_ci = _mais_recente(*(c.get("fim") for c in checks))
        fase = "verde_esperando_merge" if veredito == "limpo" else "esperando_revisor"
        desde = _mais_recente(fim_ci, quando)
    inicio = _dt(desde)
    return {
        "fase": fase,
        "desde": desde,
        "dias_na_coluna": max(0, (agora - inicio).days) if inicio else None,
        "ci": ci,
        "veredito": veredito,
        "conflito": pr.get("merge_state") == "DIRTY",
        "versao": versao,
    }


def _por_data(prs: list[dict]) -> list[dict]:
    return sorted(prs, key=lambda p: (p.get("created_at") or "", p["number"]))


def _branch_sem_pr(numero: int, prs: list[dict], branches: list[str]) -> str | None:
    """Branch remota da issue (convenção `<type>/<slug>-<N>`) que ainda não virou PR."""
    com_pr = {p.get("head_ref") for p in prs}
    sufixo = re.compile(rf"-{numero}$")
    return next((b for b in branches if sufixo.search(b) and b not in com_pr), None)


def _fase_issue(issue: dict, prs: list[dict], abertas: set[int], producao: _Producao,
                branches: list[str], fases_pr: dict[int, dict]) -> dict:
    """Régua da issue, na precedência da ADR 0062: a primeira regra que vale decide."""
    labels = set(issue["labels"])
    prs = _por_data(prs)
    mergeados = [p for p in prs if p["state"] == "MERGED"]
    abertos = [p for p in prs if p["state"] == "OPEN"]
    tentativas = [p["number"] for p in prs if p["state"] == "CLOSED"]
    out = {"fase": None, "sub": None, "branch": None, "pr": None, "sinal": None,
           "tentativas": tentativas, "versao": None, "em_producao_em": None}
    if "ready-for-human" in labels:
        out["fase"] = "humana"
    elif issue["state"] != "OPEN" and not mergeados:
        out["fase"] = "encerrada_sem_pr"
    elif mergeados:
        out["pr"] = mergeados[-1]["number"]
        no_ar = [producao.do_pr(p) for p in mergeados]
        deploys = [d for _, d in no_ar if d]
        if deploys:
            primeiro = min(deploys, key=lambda d: _dt(d["at"]))
            out.update(fase="em_producao", versao=primeiro.get("app_version"), em_producao_em=primeiro["at"])
        else:
            out["fase"] = "em_producao" if any(ok for ok, _ in no_ar) else "mergeada"
    elif abertos:
        pr = abertos[-1]
        do_pr = fases_pr[pr["number"]]
        out.update(fase="pr_aberto", pr=pr["number"], sinal={
            "ci": do_pr["ci"], "veredito": do_pr["veredito"], "conflito": do_pr["conflito"],
            "tentativa_anterior": any(t < pr["number"] for t in tentativas)})
    elif "blocked" in labels or any(b in abertas for b in issue["blocked_by"]):
        out["fase"] = "bloqueada"
    elif "in-progress" in labels or issue["assignees"]:
        out["fase"] = "em_andamento"
        out["branch"] = _branch_sem_pr(issue["number"], prs, branches)
        out["sub"] = "branch_criada" if out["branch"] else None
    elif "ready-for-agent" in labels:
        out["fase"] = "fila"
    else:
        out["fase"] = "triagem"
    return out
