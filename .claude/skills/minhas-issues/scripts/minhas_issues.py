"""Check de um minuto das issues abertas de quem pede, o `/minhas-issues` (issue #956).

Só leitura: consulta gh, git e a status page do GitHub e imprime 4 blocos
(semáforo, em andamento, na fila, plano). Toda ação sai como comando pronto;
nada é executado aqui.

Uso:
  python3 minhas_issues.py            login do `gh api user`, tela visual
  python3 minhas_issues.py @login     fila de outra pessoa
  python3 minhas_issues.py --curto    a tela compacta, sem fluxograma nem Tecnologia
  python3 minhas_issues.py --json     a mesma visão em JSON, para o painel do mod hr-issues

A tela visual soma ao compacto: o caminho das issues em Mermaid, a árvore de
cada PRD com os bloqueios nativos, os selos Humana e Diretor e a seção do que
chegou pela aba Tecnologia (marcador `demanda-vitta` no corpo da issue).

"Minha" segue a regra do filtro de responsável do PedroOS (issue #1039):
atribuída à pessoa; sem ninguém atribuído, quem criou.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "onda-enxuta" / "scripts"))
import fluxo as config_do_fluxo  # noqa: E402

STATUS_PAGE = "https://www.githubstatus.com/api/v2/components.json"
SEM_RUNNER = "not acquired by Runner"
JANELA_DIAS = 45
SUBIDA = "python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py"
TRIAGEM = ("ready-for-agent", "ready-for-human", "needs-triage", "needs-info")

# O PRD do leitor (`prd_do_leitor` no .claude/fluxo.json):
# uma needs-triage criada fora do repo com a metade de negócio do PRD, sem label própria.
# O que a distingue é o marcador do Projeto mais a seção "Ficou em aberto"; com
# "Decisões de implementação" no corpo, o /to-prd já passou. Sem a chave, nada muda.
FICOU_EM_ABERTO = re.compile(r"^## Ficou em aberto\s*$", re.M)
DECISOES_TECNICAS = re.compile(r"^## Decisões de implementação\s*$", re.M)


def _marcador_do_prd_do_leitor() -> re.Pattern | None:
    try:
        cfg = config_do_fluxo.carregar(Path(__file__).resolve().parents[4])
    except config_do_fluxo.Erro:
        return None
    padrao = (cfg.get("prd_do_leitor") or {}).get("marcador")
    return re.compile(padrao) if padrao else None


MARCADOR_DO_PRD_DO_LEITOR = _marcador_do_prd_do_leitor()

# A aba Tecnologia grava este marcador no corpo de toda issue que o diretor cria
# (tecnologia_vinculo.py). Fechadas entram por JANELA_TECNOLOGIA_DIAS.
MARCADOR_DIRETOR = re.compile(r'<!--\s*demanda-vitta id="')
JANELA_TECNOLOGIA_DIAS = 14
MAX_POR_CAIXA = 6
MAX_FATIAS_NA_ARVORE = 15

VEREDITO = {
    "verde": "dá pra desenvolver: sim",
    "amarelo": "dá pra desenvolver: só até o PR (a subida espera)",
    "vermelho": "dá pra desenvolver: só código local (não abra onda)",
}


# Miolo puro


def minhas(issues: list[dict], login: str) -> list[dict]:
    return [
        i for i in issues
        if login in i["assignees"] or (not i["assignees"] and i["author"] == login)
    ]


def grill_tecnico_pendente(i: dict) -> bool:
    """needs-triage com PRD do leitor que ainda não ganhou as seções técnicas."""
    corpo = i.get("body") or ""
    return (
        MARCADOR_DO_PRD_DO_LEITOR is not None
        and "needs-triage" in i["labels"]
        and bool(MARCADOR_DO_PRD_DO_LEITOR.search(corpo))
        and bool(FICOU_EM_ABERTO.search(corpo))
        and not DECISOES_TECNICAS.search(corpo)
    )


def do_diretor(i: dict) -> bool:
    return bool(MARCADOR_DIRETOR.search(i.get("body") or ""))


def selos(i: dict, sem_diretor: bool = False) -> list[str]:
    s = []
    if "ready-for-human" in i["labels"]:
        s.append("Humana")
    if do_diretor(i) and not sem_diretor:
        s.append("Diretor")
    return s


def com_selos(i: dict, visual: bool, sem_diretor: bool = False) -> str:
    if not visual:
        return str(i["number"])
    return str(i["number"]) + "".join(f" [{x}]" for x in selos(i, sem_diretor))


def cancelados_por_runner(runs: list[dict]) -> int:
    """Jobs cancelados porque o runner não pegou. O run costuma sair failure, não cancelled."""
    return sum(
        1
        for r in runs if r["conclusion"] not in ("success", "skipped")
        for j in r["jobs"] if j["conclusion"] == "cancelled" and any(SEM_RUNNER in a for a in j["anotacoes"])
    )


def semaforo(actions: dict) -> tuple[str, str]:
    comp, cancelados = actions["componente"], actions["cancelados_por_runner"]
    if comp in ("partial_outage", "major_outage"):
        cor = "vermelho"
    elif comp != "operational" or cancelados or cancelados is None:
        cor = "amarelo"
    else:
        cor = "verde"
    partes = [f"Actions {comp or 'sem resposta da status page'}"]
    if cancelados is None:
        partes.append("sem leitura dos runs")
    elif cancelados:
        partes.append(f"{cancelados} job{'s' if cancelados > 1 else ''} cancelado{'s' if cancelados > 1 else ''} por falta de runner")
    return cor, " · ".join(partes)


def _must_fix_aberto(veredito: str) -> bool:
    final = re.search(r"VEREDITO:\s*(\S+)", veredito)
    if final:
        return final.group(1).upper().startswith("MUST-FIX")
    achado = re.search(r"\*\*must-fix\*\*(.*?)(?=\n\s*\*\*|\Z)", veredito, re.S)
    if not achado:
        return False
    corpo = re.sub(r"^\s*(\([^)]*\))?\s*:?", "", achado.group(1))
    palavras = re.sub(r"(?m)^\s*(?:[-*]|\d+\.)\s*", "", corpo).split()
    return bool(palavras) and not palavras[0].lower().startswith("nenhum")


def estado_pr(pr: dict) -> dict:
    conclusoes = [c["conclusion"] for c in pr["checks"]]
    if any(c in ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR") for c in conclusoes):
        motivo = "CI vermelho"
    elif "CANCELLED" in conclusoes:
        motivo = "CI cancelado"
    elif any(c is None for c in conclusoes):
        motivo = "CI rodando"
    elif pr["mergeStateStatus"] in ("DIRTY", "BEHIND"):
        motivo = "conflito com a main"
    elif pr["vereditos"] and _must_fix_aberto(pr["vereditos"][-1]):
        motivo = "must-fix aberto"
    elif pr["mergeStateStatus"] == "CLEAN":
        return {"nivel": 1, "motivo": "verde, esperando a subida"}
    else:
        motivo = "sem revisão" if not pr["vereditos"] else f"merge {pr['mergeStateStatus']}"
    return {"nivel": 3, "motivo": motivo}


def _comando_pr(pr: dict, motivo: str) -> list[str]:
    runs = sorted({c["run_id"] for c in pr["checks"] if c["conclusion"] in ("CANCELLED", "FAILURE", "TIMED_OUT", "ERROR") and c["run_id"]})
    if motivo == "CI cancelado":
        return [f"`gh run rerun {r} --failed`" for r in runs] or ["rodar o CI de novo"]
    if motivo == "CI vermelho":
        return [f"`gh run view {r} --log-failed`" for r in runs] or ["ver o CI"]
    return [{
        "CI rodando": "esperar o CI",
        "conflito com a main": "`/resolver-conflitos`",
        "must-fix aberto": f"corrigir o must-fix do PR #{pr['number']}",
        "sem revisão": f"`/code-review {pr['number']}`",
    }.get(motivo, f"ver o PR #{pr['number']}")]


def medianas(mergeados: list[dict]) -> dict:
    por: dict[str, list[float]] = {}
    for m in mergeados:
        por.setdefault("todas", []).append(m["horas"])
        for f in m["fatias"]:
            por.setdefault(f, []).append(m["horas"])
    return {k: statistics.median(v) for k, v in por.items()}


def _horas(h: float) -> str:
    return f"~{h:.1f} h".replace(".", ",")


def _quando(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _fatia(i: dict) -> str | None:
    return next((l for l in i["labels"] if l.startswith("fatia:")), None)


def _curto(s: str, n: int = 38) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def montar(d: dict, visual: bool = False) -> str:
    cor, detalhe = semaforo(d["actions"])
    agora = _quando(d["agora"])
    mias = minhas(d["issues"], d["login"])
    numeros = {i["number"] for i in mias}
    pr_de = {n: p for p in d["prs"] for n in p["closes"] if n in numeros}
    wt_de = {}
    for w in d["worktrees"]:
        achado = re.search(r"-(\d+)$", w["branch"] or "")
        if achado and int(achado.group(1)) in numeros:
            wt_de[int(achado.group(1))] = w
    mediana = lambda i: d["medianas"].get(_fatia(i) or "todas", d["medianas"].get("todas", 0))  # noqa: E731

    andamento, fila = [], []
    for i in sorted(mias, key=lambda i: -i["number"]):
        if i["number"] in pr_de or i["number"] in wt_de or "in-progress" in i["labels"]:
            andamento.append(i)
        else:
            fila.append(i)

    # passos: (nivel, texto, comando, horas ou None)
    passos: dict[int, list] = {}
    linhas_and = []
    for i in andamento:
        n, pr, wt = i["number"], pr_de.get(i["number"]), wt_de.get(i["number"])
        onde, prox = [], []
        if pr:
            e = estado_pr(pr)
            onde.append(e["motivo"])
            if e["nivel"] == 1:
                prox = [f"`{SUBIDA} --prs {pr['number']} --dry-run`"]
            else:
                prox = _comando_pr(pr, e["motivo"])
            passos.setdefault(e["nivel"], []).append((f"#{pr['number']}", prox))
        if wt and wt["nao_pushados"]:
            k = wt["nao_pushados"]
            onde.insert(0, f"{k} commit{'s' if k > 1 else ''} só local, sem push")
            prox = [f"`git -C {wt['path']} push -u origin {wt['branch']}`"]
            passos.setdefault(2, []).append((f"#{n}", prox))
        elif wt and not pr and wt["ahead"]:
            onde.append("branch no remoto, sem PR")
            prox = ["`/ship`"]
            passos.setdefault(3, []).append((f"#{n}", prox))
        elif wt and not pr:
            onde.append("worktree aberto, sem commit novo")
            prox = [f"seguir no worktree `{wt['path']}`"]
        if wt and wt["locked"]:
            onde.append("worktree travado")
        if not onde:
            onde.append("claim sem PR nem worktree nesta máquina")
            prox = ["retomar (`/tdd`) ou devolver ao pool"]
            passos.setdefault(3, []).append((f"#{n}", prox))
        pr_txt = f"#{pr['number']} {pr['mergeStateStatus']}" if pr else "sem PR"
        linhas_and.append(f"| {com_selos(i, visual)} | {_curto(i['title'])} | {pr_txt} | {'; '.join(onde)} | {' ; '.join(prox)} |")

    triagem = [i for i in fila if "needs-triage" in i["labels"] or "needs-info" in i["labels"]]
    grupos: dict[str, list[dict]] = {}
    for i in fila:
        if i in triagem:
            continue
        if i["parent"]:
            chave = f"PRD #{i['parent']['number']} {_curto(i['parent']['title'], 30)}"
        elif i["title"].startswith("PRD"):
            chave = f"PRD #{i['number']} {_curto(i['title'], 30)}"
        else:
            estado = next((l for l in i["labels"] if l in TRIAGEM), "sem label")
            chave = f"avulsa · {estado}"
        grupos.setdefault(chave, []).append(i)
    linhas_fila = []
    for chave, its in sorted(grupos.items()):
        labels = {}
        for i in its:
            l = next((x for x in i["labels"] if x in TRIAGEM), "sem label")
            labels[l] = labels.get(l, 0) + 1
        dias = min((agora - _quando(i["updatedAt"])).days for i in its)
        nums = ", ".join(com_selos(i, visual) for i in sorted(its, key=lambda i: i["number"]))
        lab = " · ".join(f"{k} {v}" for k, v in labels.items())
        linhas_fila.append(f"| {chave} | {nums} | {lab} | parada há {dias} dia{'s' if dias != 1 else ''} |")

    # níveis 4 a 6, a partir da fila
    agente = [i for i in fila if "ready-for-agent" in i["labels"] and i not in triagem and not i["title"].startswith("PRD")]
    for i in [i for i in agente if "priority:high" in i["labels"]]:
        passos.setdefault(4, []).append((f"#{i['number']}", [f"`/pegar-issue {i['number']}` ({_horas(mediana(i))})"], mediana(i)))
    for i in [i for i in fila if "ready-for-human" in i["labels"]]:
        passos.setdefault(5, []).append((f"#{i['number']}", [f"tarefa sua: {_curto(i['title'], 50)}"]))
    resto = [i for i in agente if "priority:high" not in i["labels"]]
    if resto:
        andando = sorted({i["parent"]["number"] for i in andamento if i["parent"]})
        recorte = "".join(f" --exceto #{p}" for p in andando)
        horas = sum(mediana(i) for i in resto)
        passos.setdefault(6, []).append(
            (f"{len(resto)} na fila de agente", [f"`/montar-ondas-enxutas{recorte}` ({_horas(horas)} de PR somados)"], horas)
        )

    titulos = {
        1: "Fechar o que está verde",
        2: "Salvar trabalho que pode se perder",
        3: "Destravar PR parado",
        4: "Prioridade alta na fila",
        5: "Tarefa humana",
        6: "Fila de agente em ondas",
    }
    plano, estimativas = [], []
    for nivel in sorted(passos)[:3]:
        itens = passos[nivel]
        alvo = ", ".join(x[0] for x in itens)
        cmds = [c for x in itens for c in x[1]]
        precisa_ci = any("gh run" in c or "fechar_onda" in c for c in cmds)
        extra = " (espera o Actions)" if precisa_ci and cor != "verde" else ""
        estimativas.append(0.0 if nivel <= 3 else None if nivel == 5 else sum(x[2] for x in itens))
        plano.append(f"{len(estimativas)}. {titulos[nivel]} {alvo}{extra}:")
        plano += [f"   - {c}" for c in cmds]

    saida = [
        f"**Semáforo:** {cor} · {detalhe} · {VEREDITO[cor]}",
        "",
        f"**{d['login']}**: {len(mias)} abertas ({len(andamento)} em andamento, {len(fila)} na fila)",
        "",
    ]
    if visual:
        saida += caminho(d, andamento, fila, pr_de, agora) + arvores(mias, andamento, pr_de)
    saida += [
        "**1. Em andamento**",
        "",
    ]
    if linhas_and:
        saida += ["| # | tema | PR | onde parou | próximo passo |", "|---|---|---|---|---|", *linhas_and]
    else:
        saida.append("nada em andamento")
    saida += ["", "**2. Na fila**", ""]
    if linhas_fila:
        saida += ["| grupo | issues | label | parada |", "|---|---|---|---|", *linhas_fila]
    grill = [i for i in triagem if grill_tecnico_pendente(i)]
    for i in grill:
        saida.append(f"grill técnico pendente: #{i['number']} (`/grill-with-docs #{i['number']}`)")
    for rotulo in ("needs-triage", "needs-info"):
        dessa = [i for i in triagem if rotulo in i["labels"] and i not in grill]
        if dessa:
            saida.append(f"{rotulo}: {', '.join('#' + str(i['number']) for i in dessa)} (`/triage`)")
    if visual:
        saida += ["", *secao_tecnologia(d, pr_de_todas(d["prs"]), agora)]
    saida += ["", "**3. Plano**", ""]
    saida += plano or ["nada a fazer"]
    validas = [(h, k) for k, h in enumerate(estimativas) if h is not None]
    if validas:
        rapido = min(validas)[1] + 1
        saida.append("")
        saida.append(
            "O passo 1 é o melhor e o mais rápido." if rapido == 1
            else f"Melhor: passo 1. Mais rápido: passo {rapido}."
        )
    return "\n".join(saida)


# Visual (Mermaid e Tecnologia)


def pr_de_todas(prs: list[dict]) -> dict:
    return {n: p for p in prs for n in p["closes"]}


def _eh_prd(i: dict) -> bool:
    return i["title"].startswith("PRD")


def fase(i: dict, pr_de: dict, em_andamento: bool = False) -> str:
    if i.get("state") == "CLOSED":
        if i.get("stateReason") == "NOT_PLANNED":
            return "não vai ser feita"
        return f"entregue {_quando(i['closedAt']).strftime('%d/%m')}" if i.get("closedAt") else "entregue"
    if i["number"] in pr_de:
        return f"PR #{pr_de[i['number']]['number']}"
    if em_andamento or "in-progress" in i["labels"]:
        return "em andamento"
    for label, nome in (
        ("ready-for-human", "humana"),
        ("ready-for-agent", "fila de agente"),
        ("needs-triage", "triagem"),
        ("needs-info", "triagem"),
    ):
        if label in i["labels"]:
            return nome
    return "sem label"


def _txt(s: str) -> str:
    """Texto seguro dentro de um rótulo Mermaid entre aspas."""
    return s.replace('"', "'").replace("<", "").replace(">", "")


def _caixa(nome: str, its: list[dict]) -> str:
    linhas = [f"{nome} ({len(its)})", *(f"#{_txt(com_selos(i, True))}" for i in its[:MAX_POR_CAIXA])]
    if len(its) > MAX_POR_CAIXA:
        linhas.append(f"+{len(its) - MAX_POR_CAIXA}")
    return "<br/>".join(linhas)


def caminho(d: dict, andamento: list[dict], fila: list[dict], pr_de: dict, agora: datetime) -> list[str]:
    """O caminho da issue, da triagem à entrega, com as minhas em cada caixa."""
    caixas: dict[str, list[dict]] = {k: [] for k in ("T", "A", "H", "E", "P", "F")}
    for i in fila:
        if _eh_prd(i):
            continue
        f = fase(i, pr_de)
        caixas["H" if f == "humana" else "A" if f == "fila de agente" else "T"].append(i)
    for i in andamento:
        caixas["P" if i["number"] in pr_de else "E"].append(i)
    desde = agora - timedelta(days=JANELA_TECNOLOGIA_DIAS)
    caixas["F"] = [
        i for i in minhas(d.get("fechadas", []), d["login"])
        if i.get("closedAt") and _quando(i["closedAt"]) >= desde
        and i.get("stateReason") != "NOT_PLANNED" and not _eh_prd(i)
    ]
    nomes = {
        "T": "Triagem", "A": "Fila de agente", "H": "Humana",
        "E": "Em andamento", "P": "PR aberto", "F": f"Entregue em {JANELA_TECNOLOGIA_DIAS} dias",
    }
    linhas = ["```mermaid", "flowchart LR"]
    linhas += [f'  {k}["{_caixa(nomes[k], caixas[k])}"]' for k in caixas]
    return linhas + ["  T --> A --> E --> P --> F", "  T --> H --> F", "```", ""]


def arvores(mias: list[dict], andamento: list[dict], pr_de: dict) -> list[str]:
    """Um fluxograma por PRD com fatia minha aberta: PRD, fatias e os bloqueios nativos."""
    por_prd: dict[int, tuple[str, list[dict]]] = {}
    for i in mias:
        if i["parent"]:
            por_prd.setdefault(i["parent"]["number"], (i["parent"]["title"], []))[1].append(i)
    saida = []
    for prd, (titulo, fatias) in sorted(por_prd.items()):
        fatias = sorted(fatias, key=lambda i: i["number"])[:MAX_FATIAS_NA_ARVORE]
        nos = {i["number"] for i in fatias}
        linhas = ["```mermaid", "flowchart TD", f'  P{prd}["PRD #{prd}<br/>{_txt(_curto(titulo, 40))}"]']
        travadas = set()
        for i in fatias:
            f = fase(i, pr_de, i in andamento)
            linhas.append(f'  I{i["number"]}["#{_txt(com_selos(i, True))} · {f}<br/>{_txt(_curto(i["title"], 40))}"]')
        for i in fatias:
            for b in i.get("blockedBy", []):
                if b in nos:
                    linhas.append(f"  I{b} -. trava .-> I{i['number']}")
                    travadas.add(i["number"])
        linhas += [f"  P{prd} --> I{i['number']}" for i in fatias if i["number"] not in travadas]
        saida += linhas + ["```", ""]
    return saida


def secao_tecnologia(d: dict, pr_de: dict, agora: datetime) -> list[str]:
    """O que o diretor pediu pela aba Tecnologia: abertas e fechadas na janela, de qualquer responsável."""
    desde = agora - timedelta(days=JANELA_TECNOLOGIA_DIAS)
    vistos, its = set(), []
    for i in d.get("tecnologia", []):
        recente = i.get("state") != "CLOSED" or (i.get("closedAt") and _quando(i["closedAt"]) >= desde)
        if do_diretor(i) and recente and i["number"] not in vistos:
            vistos.add(i["number"])
            its.append(i)
    saida = [f"**Chegou da Tecnologia** (abertas e fechadas nos últimos {JANELA_TECNOLOGIA_DIAS} dias)", ""]
    if not its:
        return saida + ["nada pela aba Tecnologia nessa janela"]
    for tipo in ("Bug", "Melhoria"):
        dessas = [i for i in its if ("Bug" if {"type:fix", "type:bug"} & set(i["labels"]) else "Melhoria") == tipo]
        if not dessas:
            continue
        saida += [f"{tipo} ({len(dessas)})", "", "| # | tema | fase | com quem |", "|---|---|---|---|"]
        for i in sorted(dessas, key=lambda i: (i.get("state") == "CLOSED", -i["number"])):
            quem = ", ".join(i["assignees"]) or "sem responsável"
            saida.append(f"| {com_selos(i, True, sem_diretor=True)} | {_curto(i['title'])} | {fase(i, pr_de)} | {quem} |")
        saida.append("")
    return saida[:-1]


# JSON para o painel (mod hr-issues)


def _item(i: dict, pr_de: dict, em_andamento: bool = False) -> dict:
    return {
        "n": i["number"],
        "titulo": i["title"],
        "fase": fase(i, pr_de, em_andamento),
        "selos": selos(i),
        "quem": i["assignees"],
        "fechada": i.get("state") == "CLOSED",
    }


def visao(d: dict) -> dict:
    """O que a tela visual mostra, em dados: o painel desenha, não recalcula."""
    cor, detalhe = semaforo(d["actions"])
    agora = _quando(d["agora"])
    mias = minhas(d["issues"], d["login"])
    pr_de = {n: p for p in d["prs"] for n in p["closes"] if n in {i["number"] for i in mias}}
    andamento = [
        i for i in mias
        if i["number"] in pr_de or "in-progress" in i["labels"]
        or any(w["branch"] and w["branch"].endswith(f"-{i['number']}") for w in d["worktrees"])
    ]
    fila = [i for i in mias if i not in andamento]
    caixas: dict[str, list[dict]] = {k: [] for k in ("triagem", "fila", "humana", "andamento", "pr", "entregue")}
    for i in sorted(fila, key=lambda i: -i["number"]):
        if _eh_prd(i):
            continue
        f = fase(i, pr_de)
        caixas["humana" if f == "humana" else "fila" if f == "fila de agente" else "triagem"].append(_item(i, pr_de))
    for i in sorted(andamento, key=lambda i: -i["number"]):
        caixas["pr" if i["number"] in pr_de else "andamento"].append(_item(i, pr_de, True))
    desde = agora - timedelta(days=JANELA_TECNOLOGIA_DIAS)
    caixas["entregue"] = [
        _item(i, pr_de)
        for i in sorted(minhas(d.get("fechadas", []), d["login"]), key=lambda i: i.get("closedAt") or "", reverse=True)
        if i.get("closedAt") and _quando(i["closedAt"]) >= desde
        and i.get("stateReason") != "NOT_PLANNED" and not _eh_prd(i)
    ]
    prds: dict[int, dict] = {}
    for i in sorted(mias, key=lambda i: i["number"]):
        if i["parent"]:
            prd = prds.setdefault(i["parent"]["number"], {"n": i["parent"]["number"], "titulo": i["parent"]["title"], "fatias": []})
            prd["fatias"].append({**_item(i, pr_de, i in andamento), "travadaPor": list(i.get("blockedBy", []))})
    pr_todas = pr_de_todas(d["prs"])
    vistos, tec = set(), {"bug": [], "melhoria": []}
    for i in sorted(d.get("tecnologia", []), key=lambda i: (i.get("state") == "CLOSED", -i["number"])):
        recente = i.get("state") != "CLOSED" or (i.get("closedAt") and _quando(i["closedAt"]) >= desde)
        if not do_diretor(i) or not recente or i["number"] in vistos:
            continue
        vistos.add(i["number"])
        tipo = "bug" if {"type:fix", "type:bug"} & set(i["labels"]) else "melhoria"
        tec[tipo].append(_item(i, pr_todas))
    texto = montar(d)
    return {
        "login": d["login"],
        "repo": d.get("repo"),
        "agora": d["agora"],
        "semaforo": {"cor": cor, "detalhe": detalhe},
        "abertas": len(mias),
        "caminho": caixas,
        "prds": list(prds.values()),
        "tecnologia": tec,
        "janelaDias": JANELA_TECNOLOGIA_DIAS,
        "plano": texto.split("**3. Plano**", 1)[1].strip().splitlines() if "**3. Plano**" in texto else [],
    }


# Coleta (só leitura)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


CONSULTA_ISSUES = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    nodes { ... on Issue {
      number title body createdAt updatedAt closedAt state stateReason author { login }
      assignees(first: 10) { nodes { login } }
      labels(first: 20) { nodes { name } }
      parent { number title }
      blockedBy(first: 10) { nodes { number state } }
    } }
  }
}
"""

CONSULTA_MERGEADOS = """
query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      createdAt mergedAt
      closingIssuesReferences(first: 5) { nodes { labels(first: 20) { nodes { name } } } }
    } }
  }
}
"""


def _jsons(texto: str) -> list:
    """O `gh api --paginate` emite um JSON por página, colados."""
    dec, i, saida = json.JSONDecoder(), 0, []
    while i < len(texto):
        while i < len(texto) and texto[i].isspace():
            i += 1
        if i < len(texto):
            obj, i = dec.raw_decode(texto, i)
            saida.append(obj)
    return saida


def _issues(repo: str, filtro: str) -> list[dict]:
    resp = json.loads(gh("api", "graphql", "-f", f"query={CONSULTA_ISSUES}", "-f", f"q=repo:{repo} is:issue {filtro}"))
    return [
        {
            "number": n["number"],
            "title": n["title"],
            "body": n["body"],
            "labels": [l["name"] for l in n["labels"]["nodes"]],
            "assignees": [a["login"] for a in n["assignees"]["nodes"]],
            "author": (n["author"] or {}).get("login"),
            "createdAt": n["createdAt"],
            "updatedAt": n["updatedAt"],
            "parent": n["parent"],
            "state": n["state"],
            "closedAt": n["closedAt"],
            "stateReason": n["stateReason"],
            "blockedBy": [b["number"] for b in n["blockedBy"]["nodes"] if b["state"] == "OPEN"],
        }
        for n in resp["data"]["search"]["nodes"]
    ]


def _prs() -> list[dict]:
    brutos = json.loads(gh(
        "pr", "list", "--state", "open", "--limit", "100", "--json",
        "number,headRefName,mergeStateStatus,statusCheckRollup,closingIssuesReferences,comments",
    ))
    prs = []
    for p in brutos:
        checks = []
        for c in p["statusCheckRollup"]:
            run = re.search(r"/runs/(\d+)", c.get("detailsUrl") or "")
            checks.append({
                "name": c.get("name") or c.get("context"),
                "conclusion": c.get("conclusion") or (c.get("state") if c.get("state") not in ("PENDING", "EXPECTED") else None) or None,
                "run_id": int(run.group(1)) if run else None,
            })
        prs.append({
            "number": p["number"],
            "headRefName": p["headRefName"],
            "mergeStateStatus": p["mergeStateStatus"],
            "closes": [r["number"] for r in p["closingIssuesReferences"]],
            "checks": checks,
            "vereditos": [c["body"] for c in p["comments"] if "Veredito da revisão" in c["body"]],
        })
    return prs


def _actions(repo: str) -> dict:
    try:
        with urllib.request.urlopen(STATUS_PAGE, timeout=5) as r:
            comps = json.load(r)["components"]
        componente = next((c["status"] for c in comps if c["name"] == "Actions"), None)
    except Exception:
        componente = None
    try:
        runs = json.loads(gh("run", "list", "--limit", "10", "--json", "databaseId,conclusion"))
        for run in runs:
            run["jobs"] = []
            if run["conclusion"] in ("success", "skipped", "", None):
                continue
            for job in json.loads(gh("run", "view", str(run["databaseId"]), "--json", "jobs"))["jobs"]:
                notas = []
                if job["conclusion"] == "cancelled":
                    resp = gh("api", f"repos/{repo}/check-runs/{job['databaseId']}/annotations")
                    notas = [n.get("message") or "" for n in json.loads(resp)]
                run["jobs"].append({"conclusion": job["conclusion"], "anotacoes": notas})
        cancelados = cancelados_por_runner(runs)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        cancelados = None  # sem leitura dos runs: o semáforo fica amarelo
    return {"componente": componente, "cancelados_por_runner": cancelados}


def _mergeados(repo: str, agora: datetime) -> list[dict]:
    desde = (agora - timedelta(days=JANELA_DIAS)).date().isoformat()
    paginas = _jsons(gh(
        "api", "graphql", "--paginate", "-f", f"query={CONSULTA_MERGEADOS}",
        "-f", f"q=repo:{repo} is:pr is:merged merged:>={desde}",
    ))
    saida = []
    for pag in paginas:
        for n in pag["data"]["search"]["nodes"]:
            fatias = [l["name"] for ref in n["closingIssuesReferences"]["nodes"] for l in ref["labels"]["nodes"] if l["name"].startswith("fatia:")]
            if not n["closingIssuesReferences"]["nodes"]:
                continue  # PR de registro de deploy (histórico, não existe mais desde a Action pós-merge), sem issue
            horas = (_quando(n["mergedAt"]) - _quando(n["createdAt"])).total_seconds() / 3600
            saida.append({"horas": horas, "fatias": fatias})
    return saida


def _worktrees() -> list[dict]:
    remotas = {l.split("refs/heads/", 1)[1] for l in git("ls-remote", "--heads", "origin").splitlines() if "refs/heads/" in l}
    saida, atual = [], {}
    for linha in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if linha.startswith("worktree "):
            atual = {"path": linha.split(" ", 1)[1], "branch": None, "locked": False}
        elif linha.startswith("branch "):
            atual["branch"] = linha.split("refs/heads/", 1)[-1]
        elif linha.startswith("locked"):
            atual["locked"] = True
        elif not linha and atual:
            if atual["branch"]:
                sem_remoto = atual["branch"] not in remotas
                base = "origin/main" if sem_remoto else f"origin/{atual['branch']}"
                try:
                    ahead = int(git("-C", atual["path"], "rev-list", "--count", "origin/main..HEAD").strip())
                    nao_pushados = int(git("-C", atual["path"], "rev-list", "--count", f"{base}..HEAD").strip())
                except subprocess.CalledProcessError:
                    ahead = nao_pushados = 0
                saida.append({**atual, "ahead": ahead, "sem_remoto": sem_remoto, "nao_pushados": nao_pushados})
            atual = {}
    return saida


def coletar(login: str | None, visual: bool = True) -> dict:
    login = login or gh("api", "user", "-q", ".login").strip()
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    agora = datetime.now(timezone.utc)
    vistas, issues = set(), []
    for filtro in (f"is:open assignee:{login}", f"is:open author:{login} no:assignee"):
        for i in _issues(repo, filtro):
            if i["number"] not in vistas:
                vistas.add(i["number"])
                issues.append(i)
    extra = {}
    if visual:
        desde = (agora - timedelta(days=JANELA_TECNOLOGIA_DIAS)).date().isoformat()
        extra["fechadas"] = _issues(repo, f"is:closed closed:>={desde} involves:{login}")
        extra["tecnologia"] = [
            *_issues(repo, "is:open demanda-vitta in:body"),
            *_issues(repo, f"is:closed closed:>={desde} demanda-vitta in:body"),
        ]
    return {
        **extra,
        "repo": repo,
        "login": login,
        "agora": agora.isoformat(),
        "issues": issues,
        "prs": _prs(),
        "worktrees": _worktrees(),
        "actions": _actions(repo),
        "medianas": medianas(_mergeados(repo, agora)),
    }


if __name__ == "__main__":
    for fluxo in (sys.stdout, sys.stderr):  # Windows: o pipe sai em cp1252
        fluxo.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    visual = "--curto" not in args
    alvo = next((a.lstrip("@") for a in args if not a.startswith("--")), None)
    try:
        if "--json" in args:
            print(json.dumps(visao(coletar(alvo, True)), ensure_ascii=False))
        else:
            print(montar(coletar(alvo, visual), visual))
    except subprocess.CalledProcessError as erro:
        motivo = (erro.stderr or "").strip().splitlines()
        sys.exit(f"falha ao consultar o GitHub ({' '.join(erro.cmd[:3])}): {motivo[0] if motivo else erro}")
